"""Streamlit interface for the verified Lab 18 SEC EDGAR report."""

from contextlib import redirect_stdout
from decimal import Decimal
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re

import altair as alt
import pandas as pd
import streamlit as st


def load_edgar_module():
    relative_path = Path(".agents/skills/buffett-analysis/edgar_financials.py")
    roots = (*Path(__file__).resolve().parents, Path.cwd(), *Path.cwd().parents)
    for root in roots:
        script = root / relative_path
        if script.is_file():
            spec = importlib.util.spec_from_file_location("edgar_financials", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError("Launch from the course root to locate edgar_financials.py.")


@st.cache_data(ttl=3600, show_spinner=False)
def retrieve(ticker, user_agent):
    tickers = edgar.fetch_json(edgar.SEC_TICKERS, user_agent)
    company = next((item for item in tickers.values() if item["ticker"] == ticker), None)
    if company is None:
        raise ValueError(f"{ticker} was not found in SEC EDGAR.")

    cik = f"CIK{company['cik_str']:010d}"
    submissions = edgar.fetch_json(f"{edgar.SEC_DATA}/submissions/{cik}.json", user_agent)
    ends = edgar.fiscal_year_ends(submissions, user_agent)
    if not ends:
        raise ValueError(f"No 10-K fiscal year ends were found for {ticker}.")

    facts = edgar.fetch_json(f"{edgar.SEC_DATA}/api/xbrl/companyfacts/{cik}.json", user_agent)
    rows = edgar.analyze(facts["facts"].get("us-gaap", {}), ends)
    return company["title"], rows


def in_millions(value):
    if value is None:
        return "not found"
    return f"{Decimal(value).scaleb(-6):,.6f}".rstrip("0").rstrip(".")


def show_financials(rows):
    financials = {}
    sources = {}
    labels = [metric[0] for metric in edgar.METRICS] + ["ROE", "Owner earnings"]
    for end, facts, roe, owner_earnings in rows:
        equity = facts[4][0]
        roe_display = "not known" if equity is not None and equity <= 0 else "not found"
        financials[end] = [
            *(in_millions(value) for value, _ in facts),
            f"{roe:.2%}" if roe is not None else roe_display,
            in_millions(owner_earnings),
        ]
        tags = [f"us-gaap:{tag}" if tag else "not found" for _, tag in facts]
        sources[end] = [
            *tags,
            f"{tags[1]} ÷ {tags[4]}" if roe is not None else roe_display,
            f"{tags[2]} − {tags[3]}" if owner_earnings is not None else "not found",
        ]

    st.subheader("Annual financials")
    st.caption("Fiscal year ends are shown by date. Financial amounts are in USD millions and ROE is a percentage.")
    st.dataframe(pd.DataFrame(financials, index=labels), width="stretch")
    with st.expander("XBRL source tags"):
        st.dataframe(pd.DataFrame(sources, index=labels), width="stretch")


def show_chart(rows):
    points = pd.DataFrame(
        [
            {"Fiscal year end": end, "Metric": label, "USD millions": value / 1e6 if value is not None else None}
            for end, facts, _, owner_earnings in rows
            for label, value in (("Owner earnings", owner_earnings), ("Net income", facts[1][0]))
        ]
    )
    chart = (
        alt.Chart(points)
        .mark_line(point=True, invalid="break-paths-show-domains")
        .encode(
            x=alt.X("Fiscal year end:O", sort=[row[0] for row in rows], axis=alt.Axis(labelAngle=0)),
            y="USD millions:Q",
            color="Metric:N",
            tooltip=["Fiscal year end:O", "Metric:N", alt.Tooltip("USD millions:Q", format=",.2f")],
        )
    )
    st.subheader("Owner earnings and net income")
    st.altair_chart(chart, width="stretch")
    if any(value is None for _, facts, _, owner_earnings in rows for value in (facts[1][0], owner_earnings)):
        st.caption("Missing observations appear as gaps or an absent series.")


def default_memo(checks):
    results = [result for _, result in checks]
    if "fail" in results:
        recommendation = "Pass"
    elif "not known" in results:
        recommendation = "Watch it"
    else:
        recommendation = "Own the business"

    comments = (
        {
            "pass": "Returns on equity cleared the screen throughout the period.",
            "fail": "Returns on equity fell short of the screen in at least one fiscal year.",
            "not known": "The available returns on equity leave profitability incompletely assessed.",
        },
        {
            "pass": "Owner earnings stayed positive across the period.",
            "fail": "Owner earnings were inconsistent, with at least one year at or below break-even.",
            "not known": "The available financials leave the consistency of owner earnings unresolved.",
        },
        {
            "pass": "The business ended the period with higher owner earnings than it began with.",
            "fail": "Owner earnings ended the period at or below their starting level.",
            "not known": "The available owner earnings leave the change over the full period unresolved.",
        },
    )
    assessment = " ".join(comment[result] for comment, result in zip(comments, results))
    return f"### {recommendation}\n\n{assessment}"


DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(
    r"(?<!\w)(?P<sign>[+−-]?)\s*(?P<currency>\$|USD\s+)?\s*"
    r"(?P<value>(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:e[+-]?\d{1,3})?)"
    r"(?:\s*(?P<unit>%|percent\b|basis\s+points?\b|bps?\b|[x×](?!\w)|billion\b|million\b|thousand\b|bn\b|[bmk]\b))?(?!\w)",
    re.IGNORECASE,
)
SCALES = {
    "billion": 9, "bn": 9, "b": 9,
    "million": 6, "m": 6,
    "thousand": 3, "k": 3,
}
SCREENING_THRESHOLD = re.compile(
    r"\b(?:"
    r"(?:ROE|return on equity)\s+(?:is\s+)?(?:at least|>=|≥)\s*(?P<minimum>15)\s*(?:%|percent\b)"
    r"|clearing the\s+(?P<hurdle>15)\s*(?:%|percent\b)\s+hurdle\b"
    r"|(?P<screen>15)\s*(?:%|percent\b)\s+(?:Buffett\s+)?ROE\s+(?:screen(?:ing)?\s+threshold|threshold|hurdle)\b"
    r")",
    re.IGNORECASE,
)
LAB_REFERENCE = re.compile(r"\bLab\s+(?P<lab>18)\s+known answers\b", re.IGNORECASE)


def unsupported_claims(memo, report):
    """Compare numeric tokens with the verified script's printed annual table."""
    table = report.split("Annual financials", 1)[1].split("Source XBRL tags", 1)[0]
    dates = set(DATE.findall(table))
    fiscal_years = {Decimal(end[:4]) for end in dates}
    amounts, percentages = set(), set()
    table_values = DATE.sub("", table.split("\n\n", 1)[1])
    for match in NUMBER.finditer(table_values):
        value = numeric_value(match)
        if match["unit"] == "%":
            percentages.add(value)
        else:
            amounts.add(value)

    prose = re.sub(r"!?(\[[^\]]*\])\([^\n)]*\)", r"\1", memo)
    prose = re.sub(r"^\s{0,3}\d+[.)][ \t]+", "", prose, flags=re.MULTILINE)
    prose = re.sub(r"[*_\x60]", "", prose)
    unsupported = [match.group() for match in DATE.finditer(prose) if match.group() not in dates]
    prose = DATE.sub(" ", prose)
    contextual_numbers = {
        match.span(group)
        for pattern in (SCREENING_THRESHOLD, LAB_REFERENCE)
        for match in pattern.finditer(prose)
        for group, value in match.groupdict().items()
        if value is not None
    }
    for match in NUMBER.finditer(prose):
        if match.span("value") in contextual_numbers:
            continue
        value = numeric_value(match)
        unit = (match["unit"] or "").lower()
        if unit in {"%", "percent"}:
            supported = value in percentages
        elif unit.startswith("basis") or unit in {"bp", "bps"}:
            supported = value.scaleb(-2) in percentages
        elif unit in SCALES:
            supported = value.scaleb(SCALES[unit]) in amounts
        elif unit:
            supported = False
        else:
            supported = value in amounts or (not match["currency"] and value in fiscal_years)
        if not supported:
            unsupported.append(match.group().strip())
    return list(dict.fromkeys(unsupported))


def numeric_value(match):
    sign = "-" if match["sign"] in ("-", "−") else ""
    return Decimal(sign + match["value"].replace(",", ""))


def show_memo(ticker, company, rows, checks):
    st.subheader("Investment memo")
    st.caption("Edit the draft below. To use an existing Markdown memo, upload it or paste its text.")
    memo_key = f"memo:{ticker}"
    uploaded = st.file_uploader("Load a Markdown memo", type=["md", "markdown"], key=f"file:{ticker}")
    if uploaded is not None and st.button("Use uploaded memo"):
        try:
            st.session_state[memo_key] = uploaded.getvalue().decode("utf-8-sig")
        except UnicodeDecodeError:
            st.error("Save the Markdown file as UTF-8 and upload it again.")
    if memo_key not in st.session_state:
        st.session_state[memo_key] = default_memo(checks)
    memo = st.text_area("Memo Markdown", key=memo_key, height=200)

    output = StringIO()
    with redirect_stdout(output):
        edgar.print_report(ticker, company, rows)
    claims = unsupported_claims(memo, output.getvalue())
    if claims:
        st.warning("Unsupported numerical claims: " + ", ".join(claims))
    st.caption("The checker compares values and units with the annual report. It does not verify which company, year, or metric a matching value describes.")
    st.markdown(memo)


def main():
    st.set_page_config(page_title="Buffett Business Analysis", layout="wide")
    st.title("Buffett Business Analysis")
    st.caption("Data from SEC EDGAR. Built with AI help as a learning demonstration, not investment advice.")

    with st.form("company_lookup"):
        ticker = st.text_input("Stock ticker", value="COST").strip().upper()
        user_agent = st.text_input(
            "SEC contact (name and email)",
            value=os.environ.get("SEC_USER_AGENT", ""),
            help="SEC EDGAR requires a contact name and email for automated requests.",
        ).strip()
        st.form_submit_button("Analyze business")

    if not ticker:
        st.info("Enter a stock ticker.")
        return
    if not re.fullmatch(r"[^\r\n]+[ \t]+[^\s@]+@[^\s@]+\.[^\s@]+", user_agent):
        st.info("Enter your name and email in the SEC contact field, then select Analyze business.")
        return
    try:
        with st.spinner(f"Loading SEC EDGAR filings for {ticker}…"):
            company, rows = retrieve(ticker, user_agent)
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Could not retrieve SEC EDGAR financials for {ticker}. {error}")
        return

    st.header(f"{company} ({ticker})")
    if len(rows) < edgar.YEAR_COUNT:
        st.info(f"SEC EDGAR returned {len(rows)} fiscal years with 10-K report dates.")
    show_financials(rows)
    show_chart(rows)
    checks = edgar.buffett_checks(rows)
    st.subheader("Buffett’s three checks")
    for label, result in checks:
        st.markdown(f"- **{result.capitalize()}** · {label}")
    show_memo(ticker, company, rows, checks)


if __name__ == "__main__":
    edgar = load_edgar_module()
    main()
