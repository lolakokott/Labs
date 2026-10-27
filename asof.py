"""Build an as-of price panel and compare it with a hindsight signal."""

# Editable inputs. Row identifies a source record; it is not a data field
# when deciding whether two records are exact duplicates.
DECISION_DATE = "2026-03-31"
TRAINING_TABLE = """Row,Ticker,Month measured,Published on,Price
1,AAA,2026-01,2026-02-10,101.0
2,AAA,2026-02,2026-03-10,104.0
3,AAA,2026-03,2026-04-10,109.0
4,AAA,2026-02,2026-03-25,103.0
5,BBB,2026-01,2026-02-10,98.0
6,BBB,2026-02,2026-03-10,97.0
7,BBB,2026-02,2026-03-10,97.0
8,BBB,2026-03,2026-04-10,92.0
9,CCC,2026-01,2026-02-10,110.0
10,CCC,2026-02,2026-04-05,112.0
11,,2026-02,2026-03-10,99.0
12,CCC,2026-02,2026-03-10,111.0
"""

import csv
import sys
from datetime import date
from decimal import Decimal
from io import StringIO


def read_rows(table):
    rows = []
    for record in csv.DictReader(StringIO(table.strip())):
        rows.append({
            "row": int(record["Row"]),
            "ticker": record["Ticker"].strip(),
            "month": date.fromisoformat(record["Month measured"].strip() + "-01"),
            "published": date.fromisoformat(record["Published on"].strip()),
            "price": Decimal(record["Price"].strip()),
        })
    return rows


def latest_publications(rows):
    """Keep the latest publication per ticker/month; first input wins ties."""
    latest = {}
    for row in rows:
        key = (row["ticker"], row["month"])
        if key not in latest or row["published"] > latest[key]["published"]:
            latest[key] = row
    return list(latest.values())


def report_rule(number, label, before, after):
    kept = {id(row) for row in after}
    removed = [row["row"] for row in before if id(row) not in kept]
    print(f"{number}. {label}: removed {len(removed)}; "
          f"row numbers {removed}; remaining {len(after)}")


def print_signals(label, panel, tickers):
    print(f"\n{label}")
    for ticker in tickers:
        history = sorted((row for row in panel if row["ticker"] == ticker),
                         key=lambda row: row["month"])
        if not history:
            print(f"{ticker}: unavailable (no months available)")
            continue
        latest = history[-1]
        month = latest["month"]
        previous_month = date(month.year - 1, 12, 1) if month.month == 1 else date(
            month.year, month.month - 1, 1)
        previous = next((row for row in history if row["month"] == previous_month), None)
        prefix = f"{ticker}: latest month {month:%Y-%m}"
        if previous is None:
            print(f"{prefix}; unavailable (missing previous month {previous_month:%Y-%m})")
        elif previous["price"] == 0:
            print(f"{prefix}; unavailable (previous month's price is zero)")
        else:
            change = (latest["price"] / previous["price"] - 1) * 100
            print(f"{prefix}; {previous_month:%Y-%m} -> {month:%Y-%m}: "
                  f"{previous['price']} -> {latest['price']}; {change:+.2f}%")


def main():
    decision_date = date.fromisoformat(DECISION_DATE)
    rows = read_rows(TRAINING_TABLE)
    print(f"Decision date: {decision_date}\nStarting rows: {len(rows)}")

    valid = [row for row in rows if row["ticker"]]
    report_rule(1, "Quarantine missing tickers", rows, valid)

    seen = set()
    unique = []
    for row in valid:
        key = (row["ticker"], row["month"], row["published"], row["price"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    report_rule(2, "Remove exact duplicates (excluding Row)", valid, unique)

    available = [row for row in unique if row["published"] <= decision_date]
    report_rule(3, "Remove publications after decision date", unique, available)

    panel = latest_publications(available)
    report_rule(4, "Keep latest publication per ticker/month", available, panel)

    print("\nRemaining as-of panel")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["Row", "Ticker", "Month measured", "Published on", "Price"])
    for row in sorted(panel, key=lambda row: (row["ticker"], row["month"])):
        writer.writerow([row["row"], row["ticker"], row["month"].strftime("%Y-%m"),
                         row["published"], row["price"]])

    tickers = sorted({row["ticker"] for row in valid})
    print_signals("As-of signals", panel, tickers)
    naive_panel = latest_publications(unique)
    print_signals("Naive signals (latest publications, ignoring decision date)",
                  naive_panel, tickers)


if __name__ == "__main__":
    main()
