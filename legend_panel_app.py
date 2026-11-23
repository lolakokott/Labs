"""Streamlit panel for three educational analysis lenses on one EDGAR report."""

from functools import partial
import importlib.util
import os
from pathlib import Path
import re
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import legend_financials as financials


def load_lab18():
    default_dir = Path(__file__).resolve().parents[1] / "lab18"
    source = Path(os.environ.get("LAB18_DIR", default_dir)) / "buffett_app.py"
    if not source.is_file():
        raise FileNotFoundError(f"Lab 18 app missing at {source}. Set LAB18_DIR to its folder.")
    spec = importlib.util.spec_from_file_location("legend_lab18", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    edgar = module.load_edgar_module()
    # The dedicated Lab 18 module instance keeps its existing lookup pipeline.
    # Only its analyzer is adapted, so the original EDGAR module stays intact.
    module.edgar = SimpleNamespace(**{**vars(edgar), "analyze": partial(financials.analyze, edgar)})
    return module, edgar


@st.cache_data(ttl=3600, show_spinner=False)
def retrieve(ticker, user_agent, _lab18):
    return _lab18.retrieve.__wrapped__(ticker, user_agent)


def derived(value, pattern):
    return "not found" if value is None else format(value, pattern)


def tables(edgar, rows, amount_format):
    labels = [label for label, _, _ in (*edgar.METRICS, *financials.EXTRA_METRICS)]
    labels += ["ROE", "Owner earnings", "R&D / revenue", "Liabilities / equity"]
    values, sources = {}, {}
    for end, facts, roe, earnings in rows:
        rd_ratio, leverage = financials.annual_ratios(facts)
        values[end] = [
            *(amount_format(value) for value, _ in facts),
            "not known" if roe is None and facts[4][0] is not None and facts[4][0] <= 0
            else derived(roe, ".2%"),
            amount_format(earnings), derived(rd_ratio, ".2%"), derived(leverage, ".2f"),
        ]
        if leverage is not None:
            values[end][-1] += "×"
        tags = [f"us-gaap:{tag}" if tag else "not found" for _, tag in facts]
        sources[end] = [
            *tags,
            f"{tags[1]} ÷ {tags[4]}" if roe is not None else values[end][7],
            f"{tags[2]} − {tags[3]}" if earnings is not None else "not found",
            f"{tags[6]} ÷ {tags[0]}" if rd_ratio is not None else "not found",
            f"{tags[5]} ÷ {tags[4]}" if leverage is not None else "not found",
        ]
    return pd.DataFrame(values, index=labels), pd.DataFrame(sources, index=labels)


def numeric_report(edgar, rows, growth):
    values, _ = tables(edgar, rows, lambda v: derived(v, ","))
    lines = ["Annual financials (USD)", "", "Fiscal year end " + "  ".join(values.columns)]
    lines.extend(f"{label}  " + "  ".join(series) for label, series in values.iterrows())
    lines.append(f"Revenue CAGR  {derived(growth, '.2%')}")
    return "\n".join([*lines, "", "Source XBRL tags"])


def unsupported_numbers(lab18, memo, report):
    """Reuse Lab 18 amount and percent validation, adding tagged ratio multiples."""
    allowed = {
        lab18.numeric_value(match) for match in lab18.NUMBER.finditer(report)
        if match["unit"] in ("×", "x")
    }
    amounts_and_percentages = lab18.NUMBER.sub(
        lambda match: " " if match["unit"] in ("×", "x") else match.group(), report
    )
    prose = re.sub(r"\bFY(?=\d{4}\b)", "", memo, flags=re.IGNORECASE)
    rejected = lab18.unsupported_claims(prose, amounts_and_percentages)
    return [
        token for token in rejected
        if not ((match := lab18.NUMBER.fullmatch(token))
                and (match["unit"] or "").lower() in ("×", "x")
                and lab18.numeric_value(match) in allowed)
    ]


VERDICTS = {
    "Warren Buffett": ("Own the business", "Watch it", "Pass"),
    "Cathie Wood": ("Fits the growth screen", "Growth case unresolved", "Falls short of the growth screen"),
    "Michael Burry": ("Passes the forensic screen", "Forensic case unresolved", "Flags a forensic concern"),
}


def verdict(investor, checks):
    statuses = {status for _, status in checks}
    return VERDICTS[investor][2 if "fail" in statuses else 1 if "not known" in statuses else 0]


def draft_memo(lab18, investor, checks, growth, rd_ratio, leverage):
    if investor == "Warren Buffett":
        return lab18.default_memo(checks)
    title = verdict(investor, checks)
    if investor == "Cathie Wood":
        evidence = (
            f"Revenue CAGR was {derived(growth, '.2%')} and the growth check was **{checks[0][1]}**. "
            f"Latest reported R&D intensity was {derived(rd_ratio, '.2%')} and the check was **{checks[1][1]}**."
        )
        question = "What would show that adoption can accelerate and sustain growth? Reported R&D captures only separately tagged spending."
    else:
        ratio = "not found" if leverage is None else f"{leverage:.2f}×"
        evidence = (
            f"The annual cash conversion check was **{checks[0][1]}**. "
            f"Latest liabilities / equity was {ratio} and the leverage check was **{checks[1][1]}**."
        )
        question = "How much of operating cash flow depends on working-capital timing, and which liabilities could pressure liquidity?"
    return f"### {title}\n\n{evidence}\n\n{question}"


def main():
    st.set_page_config(page_title="Legend Panel", layout="wide")
    st.title("Legend Panel")
    st.caption("SEC EDGAR 10-K data. Investor-inspired classroom screens and editable, simulated memos for education. No investor endorsement or investment advice.")

    with st.form("company_lookup"):
        ticker = st.text_input("Stock ticker", "COST").strip().upper()
        user_agent = st.text_input("SEC User-Agent (name and email)", os.environ.get("SEC_USER_AGENT", "")).strip()
        st.form_submit_button("Analyze company")
    threshold = st.number_input(
        "Cathie Wood revenue CAGR threshold (%)", max_value=10000.0, min_value=-100.0,
        value=financials.DEFAULT_GROWTH_THRESHOLD * 100, step=1.0,
    ) / 100
    if not ticker or not re.fullmatch(r"[^\r\n]+[ \t]+[^\s@]+@[^\s@]+\.[^\s@]+", user_agent):
        st.info("Enter a ticker and a User-Agent with your name and email, then select Analyze company.")
        return
    try:
        lab18, edgar = load_lab18()
        with st.spinner(f"Loading SEC EDGAR filings for {ticker}…"):
            company, rows = retrieve(ticker, user_agent, lab18)
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Could not load {ticker}. {error}")
        return

    growth = financials.revenue_cagr(rows, edgar.YEAR_COUNT)
    research, leverage = financials.annual_ratios(rows[-1][1])
    values, tags = tables(edgar, rows, lab18.in_millions)
    checks = financials.panel_checks(edgar, rows, threshold)
    st.header(f"{company} ({ticker})")
    st.subheader("Shared annual financials")
    st.caption("Fiscal year ends from SEC 10-K filings. Dollar amounts are in USD millions.")
    if len(rows) < edgar.YEAR_COUNT:
        st.info(f"SEC EDGAR returned {len(rows)} fiscal years with 10-K report dates.")
    st.dataframe(values, width="stretch")
    st.metric("First-to-last revenue CAGR", derived(growth, ".2%"))
    with st.expander("XBRL source tags"):
        st.dataframe(tags, width="stretch")
        st.caption("CAGR uses the revenue tags from the first and last columns over four fiscal intervals.")

    report = numeric_report(edgar, rows, growth)
    evidence = (
        f"# {company} ({ticker})\n\n"
        f"```text\n{report}\n{tags.to_string()}\n```\n\n"
    ) + "\n\n".join(
        f"{investor} · {verdict(investor, rules)}\n"
        + "\n".join(f"- {label} — {result}" for label, result in rules)
        for investor, rules in checks.items()
    )
    st.download_button("Download evidence for Codex memos", evidence, f"{ticker}-panel-evidence.md")

    st.subheader("Investor checks and memos")
    st.caption("Number flags compare values and units against the shared report. Verify each matching value’s metric and fiscal year separately.")
    for column, (investor, rules) in zip(st.columns(3), checks.items()):
        with column:
            st.markdown(f"#### {investor}")
            st.markdown(f"**{verdict(investor, rules)}**")
            for label, result in rules:
                st.markdown(f"- **{result.capitalize()}** · {label}")
            draft = draft_memo(lab18, investor, rules, growth, research, leverage)
            memo_key = f"memo:{ticker}:{investor}"
            draft_key = f"draft:{ticker}:{investor}"
            if st.session_state.get(memo_key) == st.session_state.get(draft_key):
                st.session_state[memo_key] = draft
            st.session_state[draft_key] = draft
            memo = st.text_area("Memo Markdown", height=225, key=memo_key)
            claims = unsupported_numbers(lab18, memo, report)
            if claims:
                st.warning("Unsupported numerical claims: " + ", ".join(claims))
            st.markdown(memo)


if __name__ == "__main__":
    main()
