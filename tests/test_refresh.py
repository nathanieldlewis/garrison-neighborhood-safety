"""Offline unit tests. All incident rows here are SYNTHETIC, never public data."""
import importlib.util
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refresh", ROOT / "src" / "refresh.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def millis(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def row(identifier="SYNTHETIC-001", code="240", reported="2026-09-20T16:00:00Z", status="Open", oid=1):
    return {
        "OBJECTID": oid, "INCIDENT_REPORT_ID": identifier, "DATE_REPORTED": millis(reported),
        "HIGHEST_NIBRS_CODE": code, "HIGHEST_NIBRS_DESCRIPTION": "SYNTHETIC TEST RECORD",
        "CLEARANCE_STATUS": status, "CLEARANCE_DETAIL_STATUS": "",
    }


def bounds(first="2017-01-01T05:00:00Z", latest="2026-10-12T22:00:00Z"):
    return {"first_report": millis(first), "latest_report": millis(latest), "source_rows": 1000}


def metadata():
    return {"fields": [{"name": name} for name in m.FIELDS],
            "dateFieldsTimeReference": {"timeZone": "Eastern Standard Time", "respectsDaylightSaving": True},
            "datesInUnknownTimezone": False,
            "advancedQueryCapabilities": {"supportsQueryWithDistance": True}}


class PeriodTests(unittest.TestCase):
    def test_midnight_is_eastern_not_utc(self):
        self.assertEqual(m.to_local_date(millis("2026-10-13T02:00:00Z")), date(2026, 10, 12))

    def test_daylight_saving_is_respected(self):
        self.assertEqual(m.to_local_date(millis("2026-07-10T04:30:00Z")), date(2026, 7, 10))
        self.assertEqual(m.to_local_date(millis("2026-01-10T04:30:00Z")), date(2026, 1, 9))

    def test_invalid_date_is_not_silently_dropped(self):
        for bad in [None, "2026-01-01", float("nan"), True]:
            with self.assertRaises(m.DataError):
                m.to_local_date(bad)

    def test_equal_length_comparisons_in_leap_year(self):
        for end in [date(2024, 2, 29), date(2024, 12, 31), date(2025, 3, 1), date(2026, 10, 13)]:
            for start, finish, cstart, cfinish in m.periods_for(end).values():
                self.assertEqual(finish - start, cfinish - cstart)

    def test_previous_year_leap_day(self):
        self.assertEqual(m.previous_year(date(2024, 2, 29)), date(2023, 2, 28))

    def test_ytd_january_first_is_not_false_zero(self):
        snapshot = m.build_snapshot([], bounds(latest="2025-12-31T20:00:00Z"), date(2026, 1, 1), "2026-01-01T12:00:00Z")
        self.assertFalse(snapshot["periods"]["ytd"]["current_available"])

    def test_month_shift_across_year(self):
        self.assertEqual(m.month_start_shift(date(2026, 1, 15), -2), date(2025, 11, 1))

    def test_source_timezone_change_fails_closed(self):
        md = metadata(); md["dateFieldsTimeReference"]["timeZone"] = "UTC"
        with self.assertRaises(m.DataError): m.check_layer(md)

    def test_source_fields_change_fails_closed(self):
        md = metadata(); md["fields"] = md["fields"][:-1]
        with self.assertRaises(m.DataError): m.check_layer(md)

    def test_radius_parameters_match_project(self):
        p = m.spatial_params(date(2025, 1, 1), date(2026, 1, 1))
        self.assertEqual(p["geometry"], "-80.84027,35.23579")
        self.assertEqual(p["distance"], "1000")
        self.assertEqual(p["units"], "esriSRUnit_Foot")
        self.assertIn("DATE_REPORTED <", p["where"])


class ClassificationTests(unittest.TestCase):
    def test_default_crime_excludes_noncriminal(self):
        self.assertEqual(m.bucket_for(row(code="800")), "noncriminal")

    def test_unfounded_priority_prevents_double_exclusion(self):
        self.assertEqual(m.bucket_for(row(code="800", status="Closed / Unfounded")), "unfounded")

    def test_clearance_detail_also_excludes_unfounded(self):
        r = row(); r["CLEARANCE_DETAIL_STATUS"] = "UNFOUNDED"
        self.assertEqual(m.bucket_for(r), "unfounded")

    def test_drug_equipment_is_explicitly_included(self):
        self.assertEqual(m.bucket_for(row(code="35B")), "drugs")

    def test_weapon_law_is_not_assumed_to_be_a_gun_offense(self):
        self.assertEqual(m.bucket_for(row(code="520")), "other")

    def test_unknown_code_is_visible_and_excluded(self):
        self.assertEqual(m.bucket_for(row(code="ZZZZ")), "unclassified")

    def test_no_weapon_detail_inferred_from_description(self):
        r=row(code="520");r["HIGHEST_NIBRS_DESCRIPTION"]="Gun test text"
        self.assertEqual(m.bucket_for(r), "other")

    def test_violent_group_omits_archive_fondling(self):
        self.assertEqual(m.bucket_for(row(code="11D")), "other")
        self.assertEqual(m.bucket_for(row(code="11C")), "violent")

    def test_theft_from_vehicle_is_not_counted_as_other_theft(self):
        self.assertEqual(m.bucket_for(row(code="23F")), "vehicle")
        self.assertEqual(m.bucket_for(row(code="23G")), "vehicle")
        self.assertEqual(m.bucket_for(row(code="23C")), "theft_fraud")


class SnapshotTests(unittest.TestCase):
    def test_exact_duplicate_is_counted_once(self):
        a = row(); b = dict(a, OBJECTID=2)
        unique, removed = m.deduplicate([a, b])
        self.assertEqual((len(unique), removed), (1, 1))

    def test_conflicting_duplicates_stop_publication(self):
        with self.assertRaises(m.DataError): m.deduplicate([row(), row(code="13A", oid=2)])

    def test_missing_id_stops_publication(self):
        with self.assertRaises(m.DataError): m.deduplicate([row(identifier="")])

    def test_reconciliation_and_no_personal_rows(self):
        rows = [row("SYNTHETIC-"+str(i), code=code, oid=i) for i,code in enumerate(["240","13A","35B","800","XX"])]
        rows.append(row("SYNTHETIC-UNFOUNDED", "800", status="unfounded", oid=9))
        s = m.build_snapshot(rows, bounds(), date(2026,10,13), "2026-10-13T12:00:00Z")
        c = s["periods"]["30"]["current"]
        self.assertEqual(c["criminal"], 3)
        self.assertEqual(c["all_reports"], 6)
        self.assertEqual(c["excluded"], {"unfounded":1,"noncriminal":1,"unclassified":1})
        public = json.dumps(s)
        self.assertNotIn("SYNTHETIC-", public)
        self.assertNotIn("INCIDENT_REPORT_ID", public)
        self.assertNotIn("HIGHEST_NIBRS_DESCRIPTION", public)
        self.assertIsNone(s["source_completeness_cutoff"])

    def test_true_empty_result_can_be_zero_after_validation(self):
        s = m.build_snapshot([], bounds(), date(2026,10,13), "2026-10-13T12:00:00Z")
        self.assertTrue(s["periods"]["30"]["current_available"])
        self.assertEqual(s["periods"]["30"]["current"]["criminal"], 0)

    def test_recent_source_start_disables_comparison(self):
        s = m.build_snapshot([], bounds(first="2026-01-01T05:00:00Z"), date(2026,10,13), "2026-10-13T12:00:00Z")
        self.assertFalse(s["periods"]["30"]["comparison_available"])
        self.assertTrue(s["periods"]["30"]["current_available"])
        self.assertFalse(s["periods"]["365"]["current_available"])

    def test_recent_source_activity_gap_is_flagged(self):
        s=m.build_snapshot([],bounds(latest="2026-10-01T22:00:00Z"),date(2026,10,13),"2026-10-13T12:00:00Z")
        self.assertTrue(s["source_activity_warning"])

    def test_out_of_window_report_is_not_silently_counted(self):
        with self.assertRaises(m.DataError): m.build_snapshot([row(reported="2026-10-14T12:00:00Z")],bounds(),date(2026,10,13),"2026-10-13T12:00:00Z")

    def test_failed_fetch_retains_last_good_file(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); previous={"mode":"published","sentinel":"unchanged"}
            m.atomic_json(p/"latest.json",previous)
            with patch.object(m,"get_json",side_effect=m.DataError("test network failure")):
                with self.assertRaises(m.DataError):m.run(p)
            self.assertEqual(json.loads((p/"latest.json").read_text()),previous)
            self.assertEqual(json.loads((p/"status.json").read_text())["state"],"error")

    def test_large_history_reduction_requires_review(self):
        old=m.build_snapshot([row("SYNTHETIC-"+str(i),oid=i) for i in range(25)],bounds(),date(2026,10,13),"2026-10-13T12:00:00Z")
        new=m.build_snapshot([],bounds(),date(2026,10,13),"2026-10-13T12:00:00Z")
        with self.assertRaises(m.DataError):m.history_change_guard(old,new)

    def test_raw_field_guard(self):
        s=m.build_snapshot([],bounds(),date(2026,10,13),"2026-10-13T12:00:00Z")
        s["victim"]="must not publish"
        with self.assertRaises(m.DataError):m.validate_snapshot(s)

    def test_history_totals_and_gun_direction(self):
        h=json.loads((ROOT/"public/data/history.json").read_text())
        self.assertEqual(len(h["rows"]),55)
        self.assertEqual(sum(r["prior"] for r in h["rows"]),870)
        self.assertEqual(sum(r["current"] for r in h["rows"]),893)
        guns=[r for r in h["rows"] if r["category"] in {"Aggravated Assault Gun","Weapon Law Violations Gun"}]
        self.assertEqual(sum(r["prior"] for r in guns),21)
        self.assertEqual(sum(r["current"] for r in guns),20)
        self.assertTrue(all(r["current"]-r["prior"]==r["change"] for r in h["rows"]))


class PaginationTests(unittest.TestCase):
    def test_all_ids_are_fetched_beyond_single_batch(self):
        ids=list(range(901)); sizes=[]
        def query(params):
            if params.get("returnIdsOnly")=="true":return {"objectIds":ids}
            if params.get("returnCountOnly")=="true":return {"count":len(ids)}
            batch=[int(i) for i in params["objectIds"].split(",")];sizes.append(len(batch))
            return {"features":[{"attributes":row("SYNTHETIC-"+str(i),oid=i)} for i in batch]}
        rows=m.fetch_rows(date(2026,9,1),date(2026,10,13),query)
        self.assertEqual(len(rows),901)
        self.assertEqual(sum(sizes), len(ids))
        self.assertLessEqual(max(sizes), 100)

    def test_truncated_id_response_fails(self):
        with self.assertRaises(m.DataError):m.fetch_rows(date(2026,9,1),date(2026,10,13),lambda p:{"objectIds":[1],"exceededTransferLimit":True})

    def test_missing_batch_record_fails(self):
        def query(p):
            if p.get("returnIdsOnly"):return {"objectIds":[1,2]}
            if p.get("returnCountOnly"):return {"count":2}
            return {"features":[{"attributes":row()}]}
        with self.assertRaises(m.DataError):m.fetch_rows(date(2026,9,1),date(2026,10,13),query)

    def test_zero_local_reports_are_valid_if_consistent(self):
        def query(p):return {"objectIds":[]} if p.get("returnIdsOnly") else {"count":0}
        self.assertEqual(m.fetch_rows(date(2026,9,1),date(2026,10,13),query),[])


if __name__=="__main__":unittest.main()
