"""Lab 19 calculations layered on the verified Lab 18 EDGAR module."""

DEFAULT_GROWTH_THRESHOLD = 0.15
RD_THRESHOLD = 0.05
LIABILITIES_LIMIT = 2
EXTRA_METRICS = (
    ("Total liabilities", ("Liabilities",), False),
    ("R&D expense", ("ResearchAndDevelopmentExpense",), True),
)


def analyze(edgar, concepts, ends):
    """Extend the existing rows using the same annual fact selector."""
    return [
        (end, [*facts, *(edgar.select_fact(concepts, tags, end, flow)
                         for _, tags, flow in EXTRA_METRICS)], roe, earnings)
        for end, facts, roe, earnings in edgar.analyze(concepts, ends)
    ]


def annual_ratios(facts):
    revenue, _, _, _, equity, liabilities, research = (value for value, _ in facts)
    return safe_ratio(research, revenue), safe_ratio(liabilities, equity)


def safe_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def revenue_cagr(rows, year_count):
    if len(rows) != year_count:
        return None
    first, last = (row[1][0][0] for row in (rows[0], rows[-1]))
    if first is None or last is None or first <= 0 or last < 0:
        return None
    return (last / first) ** (1 / (len(rows) - 1)) - 1


def check(value, predicate):
    if value is None:
        return "not known"
    return "pass" if predicate(value) else "fail"


def panel_checks(edgar, rows, growth_threshold=DEFAULT_GROWTH_THRESHOLD):
    growth = revenue_cagr(rows, edgar.YEAR_COUNT)
    research, leverage = annual_ratios(rows[-1][1]) if rows else (None, None)
    cash_income = [(facts[2][0], facts[1][0]) for _, facts, _, _ in rows]
    comparable = len(rows) == edgar.YEAR_COUNT and all(
        cash is not None and income is not None for cash, income in cash_income
    )
    return {
        "Warren Buffett": edgar.buffett_checks(rows),
        "Cathie Wood": (
            (f"Revenue CAGR ≥ {growth_threshold * 100:g}%", check(growth, lambda v: v >= growth_threshold)),
            (f"Latest R&D / revenue ≥ {RD_THRESHOLD:.0%}", check(research, lambda v: v >= RD_THRESHOLD)),
        ),
        "Michael Burry": (
            ("Operating cash flow ≥ net income in every fiscal year",
             check(cash_income if comparable else None,
                   lambda pairs: all(cash >= income for cash, income in pairs))),
            (f"Latest liabilities / equity ≤ {LIABILITIES_LIMIT}×",
             check(leverage, lambda v: v <= LIABILITIES_LIMIT)),
        ),
    }
