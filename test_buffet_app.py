from pathlib import Path
import unittest

from buffett_app import unsupported_claims


# Relevant rows from the user-verified Costco report, in the script's USD format.
COST_REPORT = """Annual financials (USD; fiscal years end on the dates shown)

Fiscal year end  2022-08-28  2023-09-03  2024-09-01  2025-08-31  2026-08-30
ROE                  28.31%      25.11%      31.19%      27.77%      25.77%
Owner earnings  3,501,000,000  6,745,000,000  6,629,000,000  7,837,000,000  9,382,000,000

Source XBRL tags (us-gaap)
"""
COST_MEMO = Path(__file__).with_name("buffett_memo_cost.md").read_text(encoding="utf-8")


class UnsupportedClaimsTests(unittest.TestCase):
    def test_valid_costco_memo(self):
        self.assertEqual(unsupported_claims(COST_MEMO, COST_REPORT), [])

    def test_false_costco_roe_is_flagged_in_valid_memo(self):
        memo = COST_MEMO + "\nCOST ROE was 40.0%.\n"
        self.assertEqual(unsupported_claims(memo, COST_REPORT), ["40.0%"])

    def test_exemptions_do_not_apply_to_company_figures(self):
        memo = COST_MEMO + "\nCOST ROE was 15%. Net income was $18 million.\n"
        self.assertEqual(unsupported_claims(memo, COST_REPORT), ["15%", "$18 million"])

    def test_reported_roe_and_usd_millions_are_accepted(self):
        memo = "COST ROE was 25.77% and owner earnings were USD 9,382 million."
        self.assertEqual(unsupported_claims(memo, COST_REPORT), [])

    def test_screening_threshold_is_accepted_in_criterion(self):
        memo = "The Buffett check requires ROE to clear the 15% Buffett ROE threshold."
        self.assertEqual(unsupported_claims(memo, COST_REPORT), [])
