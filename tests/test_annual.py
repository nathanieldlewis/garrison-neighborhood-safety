"""Synthetic test records only. No test data is copied into the public snapshot."""
import copy
from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("annual_refresh_test", ROOT / "src/refresh.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def record(identifier, day, code="240", status="Open"):
    return {"OBJECTID": identifier, "INCIDENT_REPORT_ID": f"SYNTHETIC-{identifier}",
            "DATE_REPORTED": int(datetime.fromisoformat(day + "T16:00:00+00:00").timestamp() * 1000),
            "HIGHEST_NIBRS_CODE": code, "HIGHEST_NIBRS_DESCRIPTION": "SYNTHETIC",
            "CLEARANCE_STATUS": status, "CLEARANCE_DETAIL_STATUS": ""}


def snapshot(rows=None, end=date(2026, 10, 19), first="2017-01-01", lag=1):
    latest = (end - timedelta(days=lag)).isoformat()
    bounds = {"first_report": record(0,first)["DATE_REPORTED"],
              "latest_report": record(0,latest)["DATE_REPORTED"], "source_rows": 10000}
    return m.build_snapshot(rows or [], bounds, end, "2026-10-19T14:00:00Z")


class AnnualReportingTests(unittest.TestCase):
    def test_three_completed_years_and_ytd(self):
        s = snapshot()
        self.assertEqual([a["year"] for a in s["annual"]], [2023,2024,2025,2026])
        self.assertEqual([a["is_partial"] for a in s["annual"]], [False,False,False,True])
        self.assertEqual(s["query_start"], "2023-01-01")

    def test_nonoverlapping_actual_years(self):
        rows = [record(1,"2023-12-31"), record(2,"2024-01-01"), record(3,"2024-12-31"), record(4,"2025-01-01"), record(5,"2026-01-01")]
        s = snapshot(rows)
        self.assertEqual([a["criminal"] for a in s["annual"]],[1,2,1,1])
        self.assertEqual(sum(a["all_reports"] for a in s["annual"]),5)

    def test_full_leap_year_contains_366_days(self):
        self.assertEqual(snapshot()["annual"][1]["days"],366)
        self.assertIsNone(snapshot()["annual"][1]["annualized"])

    def test_current_annualization_uses_elapsed_days(self):
        ytd = snapshot([record(1,"2026-01-01"),record(2,"2026-10-18")])["annual"][3]
        self.assertEqual(ytd["days"],291)
        self.assertEqual(ytd["criminal"],2)
        self.assertEqual(ytd["annualized"]["criminal"],round(2*365/291,1))

    def test_leap_year_run_rate_uses_366(self):
        ytd = snapshot([record(1,"2024-01-10")],end=date(2024,3,1))["annual"][3]
        self.assertEqual(ytd["days"],60)
        self.assertEqual(ytd["annualized"]["criminal"],6.1)

    def test_january_first_is_not_a_zero_ytd(self):
        ytd = snapshot(end=date(2026,1,1))["annual"][3]
        self.assertEqual(ytd["days"],0)
        self.assertFalse(ytd["available"])
        self.assertIsNone(ytd["annualized"])

    def test_short_ytd_withholds_estimate(self):
        self.assertIsNone(snapshot(end=date(2026,1,30))["annual"][3]["annualized"])
        self.assertIsNotNone(snapshot(end=date(2026,1,31))["annual"][3]["annualized"])

    def test_source_activity_gap_withholds_estimate(self):
        s = snapshot([record(1,"2026-01-01")],lag=5)
        self.assertTrue(s["source_activity_warning"])
        self.assertIsNone(s["annual"][3]["annualized"])
        self.assertEqual(s["annual"][3]["criminal"],1)

    def test_incomplete_annual_coverage_is_flagged(self):
        s = snapshot(first="2024-05-01")
        self.assertEqual([a["available"] for a in s["annual"]],[False,False,True,True])

    def test_incomplete_ytd_withholds_estimate(self):
        ytd = snapshot(first="2026-05-01")["annual"][3]
        self.assertFalse(ytd["available"])
        self.assertIsNone(ytd["annualized"])

    def test_same_exclusions_and_category_mapping(self):
        rows = [record(1,"2023-06-01","240"),record(2,"2023-06-01","800"),record(3,"2023-06-01","13A","Unfounded"),record(4,"2023-06-01","MISSING")]
        a = snapshot(rows)["annual"][0]
        self.assertEqual(a["criminal"],1)
        self.assertEqual(a["categories"]["vehicle"],1)
        self.assertEqual(a["all_reports"],4)
        self.assertEqual(a["excluded"],{"unfounded":1,"noncriminal":1,"unclassified":1})

    def test_duplicate_reports_count_once_across_annual_series(self):
        row=record(1,"2023-01-01")
        self.assertEqual(snapshot([row,copy.deepcopy(row)])["annual"][0]["criminal"],1)

    def test_wrong_annual_year_is_rejected(self):
        s=snapshot();s["annual"][0]["year"]=2022
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_wrong_annual_actual_is_rejected(self):
        s=snapshot();s["annual"][0]["criminal"]=9
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_estimate_cannot_be_published_as_a_completed_year(self):
        s=snapshot();s["annual"][0]["annualized"]={"criminal":0,"categories":{k:0 for k in m.CATEGORY_LABELS}}
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_wrong_annualized_formula_is_rejected(self):
        s=snapshot();s["annual"][3]["annualized"]["criminal"]=900
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_annual_chart_does_not_publish_personal_fields(self):
        s=snapshot();s["annual"][0]["report_id"]="SYNTHETIC"
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_expanded_history_guard_checks_older_shared_years(self):
        rows=[record(i,"2023-06-01") for i in range(30)]
        old=snapshot(rows);new=snapshot([])
        with self.assertRaises(m.DataError):m.history_change_guard(old,new)

    def test_transition_from_shorter_snapshot_uses_only_shared_dates(self):
        old=snapshot([record(1,"2026-09-20")]);old.pop("query_start")
        new=snapshot([record(1,"2026-09-20"),record(2,"2023-01-01")])
        m.history_change_guard(old,new)


if __name__ == "__main__":
    unittest.main()
