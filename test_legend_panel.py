"""Offline regression using Costco filing amounts and mocked Company Facts envelopes."""

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import legend_financials as financials
import legend_panel_app as panel


# USD millions transcribed from the consolidated 10-K statements.
# https://www.sec.gov/Archives/edgar/data/909832/000090983222000021/cost-20220828.htm
# https://www.sec.gov/Archives/edgar/data/909832/000090983224000049/cost-20240901.htm
# https://www.sec.gov/Archives/edgar/data/909832/000090983226000093/cost-20260830.htm
COST_FACTS = {
    "2022-08-28": (226954, 5844, 7392, 3891, 20642, 43519),
    "2023-09-03": (242290, 6292, 11068, 4323, 25058, 43936),
    "2024-09-01": (254453, 7367, 11339, 4710, 23622, 46209),
    "2025-08-31": (275235, 8099, 13335, 5498, 29164, 47935),
    "2026-08-30": (303154, 9226, 15817, 6435, 35803, 53242),
}


def offline_edgar(lab18, edgar):
    concepts = {}
    previous = date(2021, 8, 29)
    for end, amounts in COST_FACTS.items():
        for (_, tags, flow), amount in zip((*edgar.METRICS, *financials.EXTRA_METRICS), amounts):
            tag = "Revenues" if tags == edgar.METRICS[0][1] else tags[0]
            entry = {"end": end, "val": amount * 10**6, "form": "10-K", "filed": end, "accn": end}
            if flow:
                entry["start"] = (previous + timedelta(days=1)).isoformat()
            concepts.setdefault(tag, {"units": {"USD": []}})["units"]["USD"].append(entry)
        previous = date.fromisoformat(end)
    cik = "CIK0000909832"
    payloads = {
        edgar.SEC_TICKERS: {"0": {"ticker": "COST", "cik_str": 909832, "title": "Costco"}},
        f"{edgar.SEC_DATA}/submissions/{cik}.json": {
            "filings": {"recent": {"form": ["10-K"] * 5 + ["10-Q"],
                                   "reportDate": [*COST_FACTS, "2026-11-15"]}, "files": []}
        },
        f"{edgar.SEC_DATA}/api/xbrl/companyfacts/{cik}.json": {"facts": {"us-gaap": concepts}},
    }
    lab18.edgar.fetch_json = lambda url, user_agent: payloads[url]
    return concepts


class LegendPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab18, cls.edgar = panel.load_lab18()

    def setUp(self):
        self.concepts = offline_edgar(self.lab18, self.edgar)
        panel.retrieve.clear()
        _, self.rows = panel.retrieve("COST", "Lab Test test@example.test", self.lab18)

    def test_costco_checks_and_historical_leverage(self):
        self.assertEqual([row[0] for row in self.rows], list(COST_FACTS))
        checks = financials.panel_checks(self.edgar, self.rows)
        self.assertEqual({name: [result for _, result in rules] for name, rules in checks.items()}, {
            "Warren Buffett": ["pass", "pass", "pass"],
            "Cathie Wood": ["fail", "not known"],
            "Michael Burry": ["pass", "pass"],
        })
        self.assertEqual(f"{financials.revenue_cagr(self.rows, self.edgar.YEAR_COUNT):.2%}", "7.51%")
        self.assertEqual(
            [f"{financials.annual_ratios(row[1])[1]:.2f}" for row in self.rows],
            ["2.11", "1.75", "1.96", "1.64", "1.49"],
        )

    def test_rd_requires_annual_10k_and_uses_latest_eligible_filing(self):
        start = "2025-09-01"
        end = "2026-08-30"
        values = [
            ("10-K", start, "2026-09-01", 1),
            ("10-K", start, "2026-09-02", 20_000_000_000),
            ("10-Q", start, "2026-09-03", 2),
            ("10-K", "2026-06-01", "2026-09-04", 3),
        ]
        self.concepts["ResearchAndDevelopmentExpense"] = {"units": {"USD": [
            dict(form=form, start=begin, end=end, filed=filed, accn=filed, val=val)
            for form, begin, filed, val in values
        ]}}
        rows = financials.analyze(self.edgar, self.concepts, list(COST_FACTS))
        self.assertEqual(rows[-1][1][-1], (20_000_000_000, "ResearchAndDevelopmentExpense"))
        self.assertEqual(financials.panel_checks(self.edgar, rows)["Cathie Wood"][1][1], "pass")
        self.assertEqual(financials.panel_checks(self.edgar, rows[1:])["Michael Burry"][0][1], "not known")

    def test_streamlit_threshold_and_all_memo_flags(self):
        with patch.object(panel, "load_lab18", return_value=(self.lab18, self.edgar)), patch.dict(
            "os.environ", {"SEC_USER_AGENT": "Lab Test test@example.test"}
        ):
            app = AppTest.from_string(
                "from legend_panel_app import main\nmain()",
                default_timeout=15,
            ).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.text_area), 3)
            self.assertEqual(len(app.warning), 0)
            self.assertEqual(app.metric[0].value, "7.51%")
            self.assertTrue(any("Fail** · Revenue CAGR ≥ 15%" in item.value for item in app.markdown))
            for editor in app.text_area:
                editor.set_value(editor.value + "\n\nCOST ROE was 40.0%.")
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual([warning.value for warning in app.warning],
                             ["Unsupported numerical claims: 40.0%"] * 3)
            app.number_input[0].set_value(5.0).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Pass** · Revenue CAGR ≥ 5%" in item.value for item in app.markdown))
            self.assertTrue(any("Not known** · Latest R&D" in item.value for item in app.markdown))
            self.assertEqual(len(app.warning), 3)


if __name__ == "__main__":
    unittest.main()
