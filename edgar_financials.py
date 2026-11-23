"""Report five fiscal years of SEC EDGAR financials and Buffett checks."""

import argparse
from datetime import date
import json
import os
import re
import sys
from urllib.request import Request, urlopen


SEC_DATA = "https://data.sec.gov"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
YEAR_COUNT = 5
METRICS = (
    ("Revenue", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"), True),
    ("Net income", ("NetIncomeLoss",), True),
    ("Operating cash flow", ("NetCashProvidedByUsedInOperatingActivities",), True),
    ("Capital expenditures", ("PaymentsToAcquirePropertyPlantAndEquipment",
                              "PaymentsToAcquireProductiveAssets"), True),
    ("Stockholders' equity", ("StockholdersEquity",), False),
)


def fetch_json(url, user_agent):
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fiscal_year_ends(submissions, user_agent):
    def report_dates(filings):
        return {
            end for form, end in zip(filings["form"], filings["reportDate"])
            if form == "10-K" and end
        }

    filings = submissions["filings"]
    ends = report_dates(filings["recent"])
    for archive in sorted(filings["files"], key=lambda item: item["filingTo"], reverse=True):
        if len(ends) >= YEAR_COUNT and archive["filingTo"] < sorted(ends)[-YEAR_COUNT]:
            break
        older = fetch_json(f"{SEC_DATA}/submissions/{archive['name']}", user_agent)
        ends.update(report_dates(older))
    return sorted(ends)[-YEAR_COUNT:]


def select_fact(concepts, tags, end, is_flow):
    for tag in tags:
        facts = concepts.get(tag, {}).get("units", {}).get("USD", [])
        candidates = []
        for fact in facts:
            if fact.get("form") != "10-K" or fact.get("end") != end:
                continue
            if fact.get("val") is None:
                continue
            start = fact.get("start")
            if is_flow:
                if not start:
                    continue
                # Include calendar years and 52/53-week fiscal years.
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
                if not 350 <= days <= 380:
                    continue
            elif start:
                continue
            candidates.append(fact)
        if candidates:
            latest = max(candidates, key=lambda fact: (fact["filed"], fact["accn"]))
            return latest["val"], tag
    return None, None


def analyze(concepts, ends):
    rows = []
    for end in ends:
        facts = [select_fact(concepts, tags, end, flow) for _, tags, flow in METRICS]
        _, income, cash_flow, capex, equity = (value for value, _ in facts)
        roe = income / equity if income is not None and equity is not None and equity > 0 else None
        owner_earnings = cash_flow - capex if cash_flow is not None and capex is not None else None
        rows.append((end, facts, roe, owner_earnings))
    return rows


def buffett_checks(rows):
    roe_values = [row[2] for row in rows]
    earnings = [row[3] for row in rows]

    def check(required, predicate):
        if len(rows) < YEAR_COUNT or any(value is None for value in required):
            return "not known"
        return "pass" if predicate(required) else "fail"

    return (
        ("ROE is at least 15% in every fiscal year",
         check(roe_values, lambda values: all(value >= 0.15 for value in values))),
        ("Owner earnings are positive in every fiscal year",
         check(earnings, lambda values: all(value > 0 for value in values))),
        ("Owner earnings increased from the first fiscal year to the last",
         check(earnings[:1] + earnings[-1:], lambda values: values[1] > values[0])),
    )


def format_usd_millions(value):
    return f"{value / 1_000_000:,.0f}" if value is not None else "not found"


def print_report(ticker, company, rows):
    print(f"{ticker} | {company}")
    print("Annual financials (USD millions, rounded to nearest million; ROE in %)\n")
    table = [("Fiscal year end", *(row[0] for row in rows))]
    for index, (label, _, _) in enumerate(METRICS):
        entries = [row[1][index] for row in rows]
        table.append((label, *(format_usd_millions(value) for value, _ in entries)))
    table.append(("ROE", *(f"{roe:.2%}" if roe is not None else
                           ("not known" if facts[4][0] is not None and facts[4][0] <= 0
                            else "not found") for _, facts, roe, _ in rows)))
    table.append(("Owner earnings", *(format_usd_millions(earnings) for _, _, _, earnings in rows)))
    widths = [max(map(len, column)) for column in zip(*table)]
    for label, *values in table:
        columns = [value.rjust(width) for value, width in zip(values, widths[1:])]
        print("  ".join([label.ljust(widths[0]), *columns]))

    print("\nSource XBRL tags (us-gaap)")
    for end, facts, _, _ in rows:
        print(f"  {end}")
        for (label, _, _), (_, tag) in zip(METRICS, facts):
            print(f"    {label}: {tag or 'not found'}")
    print("\nBuffett checks")
    for label, result in buffett_checks(rows):
        print(f"  {label}: {result}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", help="SEC ticker, such as COST or JPM")
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"),
                        help="Your name and contact email (defaults to SEC_USER_AGENT)")
    args = parser.parse_args()
    user_agent = (args.user_agent or "").strip()
    if ("\n" in user_agent or "\r" in user_agent
            or not re.fullmatch(r".+\s+[^\s@]+@[^\s@]+\.[^\s@]+", user_agent)):
        parser.error("provide your name and email via --user-agent or SEC_USER_AGENT")

    ticker = args.ticker.strip().upper()
    try:
        tickers = fetch_json(SEC_TICKERS, user_agent)
        company = next((entry for entry in tickers.values() if entry["ticker"] == ticker), None)
        if company is None:
            parser.error(f"ticker {ticker!r} was not found in SEC EDGAR")
        cik = f"CIK{company['cik_str']:010d}"
        submissions = fetch_json(f"{SEC_DATA}/submissions/{cik}.json", user_agent)
        ends = fiscal_year_ends(submissions, user_agent)
        if not ends:
            parser.error(f"no 10-K fiscal year ends found for {ticker}")
        company_facts = fetch_json(f"{SEC_DATA}/api/xbrl/companyfacts/{cik}.json", user_agent)
    except (OSError, ValueError) as error:
        print(f"Could not retrieve SEC EDGAR data: {error}", file=sys.stderr)
        return 1

    concepts = company_facts["facts"].get("us-gaap", {})
    print_report(ticker, company["title"], analyze(concepts, ends))
    return 0


if __name__ == "__main__":
    sys.exit(main())
