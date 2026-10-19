#!/usr/bin/env python3
"""Fetch CMPD's public radius data; publish aggregates, never report-level records.

Requires Python 3.11+. No third-party packages. Report dates are grouped in
America/New_York. A failed fetch leaves the last good snapshot unchanged.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
from datetime import date, datetime, time as dt_time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"
LAYER = "https://gis.charlottenc.gov/arcgis/rest/services/CMPD/CMPDIncidents/MapServer/0"
SOURCE_PAGE = "https://data.charlottenc.gov/datasets/charlotte::cmpd-incidents-1"
ET = ZoneInfo("America/New_York")
LAT, LON, RADIUS_FT = 35.23579, -80.84027, 1000
VERSION = 1
FIELDS = (
    "OBJECTID", "INCIDENT_REPORT_ID", "DATE_REPORTED",
    "HIGHEST_NIBRS_CODE", "HIGHEST_NIBRS_DESCRIPTION",
    "CLEARANCE_STATUS", "CLEARANCE_DETAIL_STATUS",
)
# The source's field definitions, not its original narrative, drive this mapping.
VIOLENT = {"09A", "11A", "11B", "11C", "120", "13A"}
VEHICLE = {"240", "23F", "23G"}
DRUGS = {"35A", "35B"}
KNOWN = {
    "09A", "09B", "09C", "100", "11A", "11B", "11C", "11D", "120",
    "13A", "13B", "13C", "200", "210", "220", "240", "250", "270", "280",
    "290", "35A", "35B", "36A", "36B", "370", "40A", "40B", "510", "520",
    "64A", "64B", "720", "90A", "90B", "90C", "90D", "90E", "90F", "90G",
    "90H", "90I", "90J", "90K", "90L", "90M", "90Z",
} | {f"23{x}" for x in "ABCDEFGH"} | {f"26{x}" for x in "ABCDEFG"} | {f"39{x}" for x in "ABCD"}
CATEGORY_LABELS = {
    "violent": "Violent crime",
    "vehicle": "Vehicle crime",
    "drugs": "Drugs and equipment",
    "burglary": "Burglary / breaking and entering",
    "vandalism": "Vandalism",
    "theft_fraud": "Other theft and fraud",
    "other": "Other criminal reports",
}
EXCLUSIONS = ("unfounded", "noncriminal", "unclassified")


class DataError(RuntimeError):
    """The source response is incomplete or cannot be safely interpreted."""


def utc_iso(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def get_json(url: str, params: dict[str, Any], attempts: int = 4) -> dict:
    query = urlencode({k: str(v) for k, v in params.items()})
    request = Request(f"{url}?{query}", headers={
        "User-Agent": "GarrisonNeighborhoodSafety/1.0 (public aggregate reporting)",
        "Accept": "application/json",
    })
    failure: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise DataError("Source returned a non-object response.")
            if "error" in payload:
                # Avoid exposing raw records or reflecting remote messages into the site.
                raise DataError(f"ArcGIS query error (code {payload['error'].get('code', 'unknown')}).")
            return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, DataError) as exc:
            failure = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** (attempt + 1), 16))
    raise DataError("Source request failed after retries.") from failure


def api(params: dict[str, Any]) -> dict:
    return get_json(LAYER + "/query", {"f": "json", **params})


def to_local_date(milliseconds: Any) -> date:
    if not isinstance(milliseconds, (int, float)) or isinstance(milliseconds, bool) or not math.isfinite(milliseconds):
        raise DataError("A report has no usable report date.")
    try:
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).astimezone(ET).date()
    except (ValueError, OverflowError, OSError) as exc:
        raise DataError("A report date is out of range.") from exc


def to_iso_timestamp(milliseconds: Any) -> str | None:
    if milliseconds is None:
        return None
    to_local_date(milliseconds)  # validates input
    return utc_iso(datetime.fromtimestamp(milliseconds / 1000, timezone.utc))


def previous_year(day: date) -> date:
    return day.replace(year=day.year - 1, day=min(day.day, calendar.monthrange(day.year - 1, day.month)[1]))


def periods_for(end: date) -> dict[str, tuple[date, date, date, date]]:
    result = {}
    prior_end = previous_year(end)
    for label in ("30", "90", "365"):
        days = int(label)
        result[label] = (end - timedelta(days=days), end, prior_end - timedelta(days=days), prior_end)
    start = date(end.year, 1, 1)
    # Equal-duration YTD comparator; its start can differ by one day in leap years.
    days = (end - start).days
    result["ytd"] = (start, end, prior_end - timedelta(days=days), prior_end)
    return result


def month_start_shift(day: date, offset: int) -> date:
    ordinal = day.year * 12 + day.month - 1 + offset
    return date(ordinal // 12, ordinal % 12 + 1, 1)


def source_bounds() -> dict:
    statistics = [
        {"statisticType": "min", "onStatisticField": "DATE_REPORTED", "outStatisticFieldName": "first_report"},
        {"statisticType": "max", "onStatisticField": "DATE_REPORTED", "outStatisticFieldName": "latest_report"},
        {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "source_rows"},
    ]
    data = api({"where": "1=1", "outStatistics": json.dumps(statistics), "returnGeometry": "false"})
    features = data.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise DataError("Citywide source coverage could not be checked.")
    values = {k.lower(): v for k, v in features[0].get("attributes", {}).items()}
    if not isinstance(values.get("source_rows"), int) or values["source_rows"] <= 0:
        raise DataError("Citywide source is empty; zero local crime must not be inferred.")
    for field in ("first_report", "latest_report"):
        to_local_date(values.get(field))
    return values


def spatial_params(start: date, end: date) -> dict:
    # ArcGIS DATE literals are interpreted in the layer's declared Eastern time zone.
    return {
        "where": f"DATE_REPORTED >= DATE '{start.isoformat()} 00:00:00' AND DATE_REPORTED < DATE '{end.isoformat()} 00:00:00'",
        "geometry": f"{LON},{LAT}", "geometryType": "esriGeometryPoint",
        "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        "distance": str(RADIUS_FT), "units": "esriSRUnit_Foot",
    }


def check_layer(metadata: dict) -> None:
    available = {field.get("name") for field in metadata.get("fields", [])}
    if not set(FIELDS).issubset(available):
        raise DataError("Required CMPD fields have changed; review the schema before publishing.")
    reference = metadata.get("dateFieldsTimeReference", {})
    if metadata.get("datesInUnknownTimezone") or reference.get("timeZone") not in {"Eastern Standard Time", "America/New_York"} or not reference.get("respectsDaylightSaving"):
        raise DataError("The source time-zone definition changed; date logic needs review.")
    if not metadata.get("advancedQueryCapabilities", {}).get("supportsQueryWithDistance"):
        raise DataError("The source no longer supports the required radius query.")


def fetch_rows(start: date, end: date, query: Callable[[dict], dict] = api) -> list[dict]:
    params = spatial_params(start, end)
    for pass_number in range(2):
        result = query({**params, "returnIdsOnly": "true", "returnGeometry": "false"})
        identifiers = result.get("objectIds")
        if not isinstance(identifiers, list) or result.get("exceededTransferLimit"):
            raise DataError("No complete source ID list was returned.")
        if len(identifiers) != len(set(identifiers)) or any(not isinstance(i, int) for i in identifiers):
            raise DataError("Source object IDs are invalid or duplicated.")
        count = query({**params, "returnCountOnly": "true"}).get("count")
        if count != len(identifiers):
            if pass_number == 0:
                continue
            raise DataError("Radius count changed during the fetch.")
        if len(identifiers) > 100000:
            raise DataError("Unexpected radius volume; check the source query.")
        rows: list[dict] = []
        # Keep GET URLs below the source server query-string limit.
        for offset in range(0, len(identifiers), 100):
            batch = sorted(identifiers)[offset:offset + 100]
            part = query({
                "objectIds": ",".join(str(i) for i in batch),
                "outFields": ",".join(FIELDS), "returnGeometry": "false",
            })
            features = part.get("features")
            if not isinstance(features, list) or part.get("exceededTransferLimit"):
                raise DataError("Source returned a truncated report batch.")
            attributes = [f.get("attributes", {}) for f in features]
            if set(a.get("OBJECTID") for a in attributes) != set(batch) or len(attributes) != len(batch):
                raise DataError("Not all requested source rows were returned.")
            rows.extend(attributes)
        after = query({**params, "returnIdsOnly": "true", "returnGeometry": "false"})
        after_ids = after.get("objectIds")
        if not isinstance(after_ids, list) or after.get("exceededTransferLimit"):
            raise DataError("The second source-ID check was incomplete.")
        if set(after_ids) == set(identifiers) and len(after_ids) == len(identifiers):
            return rows
    raise DataError("Source changed during both fetch attempts; keep the last good snapshot.")


def normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    # Do not infer missing weapon detail from an offense description.
    if re.fullmatch(r"8[0-9]{2}(?:[A-Z0-9-]{0,3})?", text):
        return text
    if text in KNOWN:
        return text
    return "UNKNOWN"


def bucket_for(row: dict) -> str:
    status = " ".join(str(row.get(k) or "") for k in ("CLEARANCE_STATUS", "CLEARANCE_DETAIL_STATUS")).lower()
    if "unfounded" in status:
        return "unfounded"
    code = normalize_code(row.get("HIGHEST_NIBRS_CODE"))
    if code.startswith("8"):
        return "noncriminal"
    if code == "UNKNOWN":
        return "unclassified"
    if code in VIOLENT:
        return "violent"
    if code in VEHICLE:
        return "vehicle"
    if code in DRUGS:
        return "drugs"
    if code == "220":
        return "burglary"
    if code == "290":
        return "vandalism"
    if code.startswith(("23", "26")) or code in {"250", "270", "280"}:
        return "theft_fraud"
    return "other"


def deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    indexed: dict[str, dict] = {}
    signature_fields = tuple(k for k in FIELDS if k != "OBJECTID")
    for row in rows:
        identifier = str(row.get("INCIDENT_REPORT_ID") or "").strip()
        if not identifier:
            raise DataError("A source row has no incident-report identifier.")
        if identifier in indexed:
            previous = indexed[identifier]
            if any(previous.get(k) != row.get(k) for k in signature_fields):
                raise DataError("Conflicting versions of an incident report need review.")
        else:
            indexed[identifier] = row
    return list(indexed.values()), len(rows) - len(indexed)


def daily_aggregates(rows: list[dict], start: date, end: date) -> list[dict]:
    daily: dict[str, Counter] = {}
    for row in rows:
        day = to_local_date(row.get("DATE_REPORTED"))
        if not start <= day < end:
            raise DataError("Source returned a report outside the requested reporting period.")
        counts = daily.setdefault(day.isoformat(), Counter())
        counts[bucket_for(row)] += 1
    return [{"date": day, "counts": dict(sorted(counts.items()))} for day, counts in sorted(daily.items())]


def summarize(daily: list[dict], start: date, end: date) -> dict:
    totals = Counter()
    for record in daily:
        if start.isoformat() <= record["date"] < end.isoformat():
            totals.update(record["counts"])
    categories = {name: totals[name] for name in CATEGORY_LABELS}
    excluded = {name: totals[name] for name in EXCLUSIONS}
    criminal = sum(categories.values())
    return {
        "criminal": criminal, "all_reports": criminal + sum(excluded.values()),
        "categories": categories, "excluded": excluded,
    }


def annual_summaries(daily: list[dict], coverage_start: date, end: date, source_quiet: bool) -> list[dict]:
    """Three completed calendar years plus current YTD; estimates stay separate."""
    result = []
    for year in range(end.year - 3, end.year + 1):
        start, next_year = date(year, 1, 1), date(year + 1, 1, 1)
        finish = min(next_year, end)
        days, year_days = (finish - start).days, (next_year - start).days
        partial = year == end.year
        available = coverage_start <= start and days > 0
        totals = summarize(daily, start, finish)
        # A run rate is a simple extrapolation, not a forecast. Withhold short or
        # visibly delayed source windows; never manufacture a completed-year total.
        estimate = None
        if partial and available and days >= 30 and not source_quiet:
            estimate = {
                "criminal": round(totals["criminal"] * year_days / days, 1),
                "categories": {k: round(n * year_days / days, 1) for k, n in totals["categories"].items()},
            }
        result.append({"year": year, "start": start.isoformat(), "end_exclusive": finish.isoformat(),
                       "days": days, "days_in_year": year_days, "is_partial": partial,
                       "available": available, **totals, "annualized": estimate})
    return result


def build_snapshot(rows: list[dict], bounds: dict, end: date, fetched_at: str) -> dict:
    periods = periods_for(end)
    oldest_needed = min(min(v[0], v[2]) for v in periods.values())
    oldest_needed = min(oldest_needed, month_start_shift(end, -12), date(end.year - 3, 1, 1))
    unique, duplicate_count = deduplicate(rows)
    daily = daily_aggregates(unique, oldest_needed, end)
    coverage_start = to_local_date(bounds["first_report"])
    latest_source = to_local_date(bounds["latest_report"])
    if latest_source > end + timedelta(days=1):
        raise DataError("The source contains an implausible future report-date maximum.")
    result_periods = {}
    for label, (start, finish, comp_start, comp_end) in periods.items():
        result_periods[label] = {
            "start": start.isoformat(), "end_exclusive": finish.isoformat(),
            "comparison_start": comp_start.isoformat(), "comparison_end_exclusive": comp_end.isoformat(),
            "days": (finish - start).days,
            "current_available": coverage_start <= start and start < finish,
            "comparison_available": coverage_start <= comp_start and comp_start < comp_end,
            "current": summarize(daily, start, finish),
            "comparison": summarize(daily, comp_start, comp_end),
        }
    monthly = []
    for offset in range(-12, 0):
        start, finish = month_start_shift(end, offset), month_start_shift(end, offset + 1)
        monthly.append({"month": start.strftime("%Y-%m"), "available": coverage_start <= start,
                        **summarize(daily, start, finish)})
    canonical = json.dumps(daily, sort_keys=True, separators=(",", ":"))
    snapshot = {
        "schema_version": VERSION, "mode": "published",
        "scope": {"address": "715 N. Graham St., Charlotte, NC", "latitude": LAT, "longitude": LON, "radius_feet": RADIUS_FT},
        "last_successful_fetch": fetched_at,
        "report_date_window_end_exclusive": end.isoformat(),
        "query_start": oldest_needed.isoformat(),
        "citywide_latest_report_date": to_iso_timestamp(bounds["latest_report"]),
        "citywide_earliest_report_date": to_iso_timestamp(bounds["first_report"]),
        "source_completeness_cutoff": None,
        "source_activity_warning": (end - latest_source).days > 3,
        "periods": result_periods, "monthly": monthly, "daily": daily,
        "annual": annual_summaries(daily, coverage_start, end, (end - latest_source).days > 3),
        "quality": {"rows_received": len(rows), "unique_reports": len(unique), "exact_duplicates_removed": duplicate_count,
                    "aggregate_sha256": hashlib.sha256(canonical.encode()).hexdigest()},
        "source": {"name": "City of Charlotte / CMPD Incidents", "url": SOURCE_PAGE, "layer": LAYER},
        "method_version": "1.1",
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict) -> None:
    if snapshot.get("schema_version") != VERSION or snapshot.get("mode") != "published":
        raise DataError("Snapshot does not match the expected schema.")
    for block in list(snapshot["periods"].values()):
        for side in ("current", "comparison"):
            values = block[side]
            if values["criminal"] != sum(values["categories"].values()):
                raise DataError("Category reconciliation failed.")
            if values["all_reports"] != values["criminal"] + sum(values["excluded"].values()):
                raise DataError("Report reconciliation failed.")
            counts = [values["criminal"], values["all_reports"], *values["categories"].values(), *values["excluded"].values()]
            if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts):
                raise DataError("Counts must be non-negative integers.")
    annual = snapshot.get("annual", [])
    end = date.fromisoformat(snapshot["report_date_window_end_exclusive"])
    expected_years = list(range(end.year - 3, end.year + 1))
    if [a.get("year") for a in annual] != expected_years:
        raise DataError("Annual series must contain three completed years and current YTD.")
    for a in annual:
        start, finish = date.fromisoformat(a["start"]), date.fromisoformat(a["end_exclusive"])
        if start != date(a["year"], 1, 1) or finish != min(date(a["year"] + 1, 1, 1), end):
            raise DataError("Annual dates do not match the labeled calendar year.")
        if a["days"] != (finish - start).days or a["days_in_year"] != 365 + calendar.isleap(a["year"]):
            raise DataError("Annual day counts are inconsistent.")
        if a["is_partial"] != (a["year"] == end.year):
            raise DataError("A partial year was labeled as complete.")
        counts = [a["criminal"], a["all_reports"], *a["categories"].values(), *a["excluded"].values()]
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts):
            raise DataError("Annual actual counts must be non-negative integers.")
        if a["criminal"] != sum(a["categories"].values()) or a["all_reports"] != a["criminal"] + sum(a["excluded"].values()):
            raise DataError("Annual counts do not reconcile.")
        estimate = a["annualized"]
        eligible = a["is_partial"] and a["available"] and a["days"] >= 30 and not snapshot["source_activity_warning"]
        if (estimate is not None) != bool(eligible):
            raise DataError("Annualized estimate does not meet the publication rule.")
        if estimate is not None:
            pairs = [(a["criminal"], estimate["criminal"])] + [(a["categories"][k], estimate["categories"][k]) for k in CATEGORY_LABELS]
            if any(projected != round(actual * a["days_in_year"] / a["days"], 1) for actual, projected in pairs):
                raise DataError("Annualization does not match actual counts and elapsed days.")
    # Fail closed if a future edit accidentally carries raw source fields into output.
    blocked = {name.lower() for name in FIELDS} | {"location", "unit", "victim", "narrative", "report_id", "features", "attributes", "geometry"}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in blocked:
                    raise DataError("A raw or personal field reached the public aggregate.")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(snapshot)


def history_change_guard(previous: dict | None, current: dict) -> None:
    if not previous or previous.get("mode") != "published":
        return
    old = {r["date"]: sum(r["counts"].values()) for r in previous.get("daily", [])}
    new = {r["date"]: sum(r["counts"].values()) for r in current.get("daily", [])}
    # Compare exactly the same dates. Days with zero current reports still count.
    old_start = previous.get("query_start", min(p["comparison_start"] for p in previous["periods"].values()))
    new_start = current.get("query_start", min(p["comparison_start"] for p in current["periods"].values()))
    lower = max(old_start, new_start)
    upper = min(previous["report_date_window_end_exclusive"], current["report_date_window_end_exclusive"])
    old_total = sum(n for d, n in old.items() if lower <= d < upper)
    new_total = sum(n for d, n in new.items() if lower <= d < upper)
    if old_total >= 20 and new_total < old_total * .5:
        raise DataError("More than half of the overlapping report history disappeared; operator review required.")


def run(data_dir: Path = DATA, accept_history_change: bool = False) -> dict:
    attempt = utc_iso()
    previous = None
    old_path = data_dir / "latest.json"
    if old_path.exists():
        previous = json.loads(old_path.read_text(encoding="utf-8"))
    try:
        metadata = get_json(LAYER, {"f": "json"})
        check_layer(metadata)
        bounds = source_bounds()
        end = datetime.now(ET).date()  # yesterday is the last completed reporting day
        windows = periods_for(end)
        start = min(min(v[0], v[2]) for v in windows.values())
        start = min(start, month_start_shift(end, -12), date(end.year - 3, 1, 1))
        rows = fetch_rows(start, end)
        snapshot = build_snapshot(rows, bounds, end, utc_iso())
        if not accept_history_change:
            history_change_guard(previous, snapshot)
        snapshot["quality"]["history_change_override"] = bool(accept_history_change)
        atomic_json(old_path, snapshot)
        atomic_json(data_dir / "status.json", {"state": "ok", "last_attempt": attempt, "message": None})
        return snapshot
    except Exception:
        atomic_json(data_dir / "status.json", {
            "state": "error", "last_attempt": attempt,
            "message": "The latest data check failed. The last successful snapshot has been retained; no zero counts have been substituted.",
        })
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--accept-history-change", action="store_true", help="Allow a reviewed, large source-history reduction; never use unattended.")
    arguments = parser.parse_args()
    try:
        snapshot = run(arguments.data_dir, arguments.accept_history_change)
    except Exception as exc:
        print(f"Refresh failed: {type(exc).__name__}. Last good data retained. Inspect the source and rerun.", file=sys.stderr)
        return 1
    print(f"Refreshed {snapshot['quality']['unique_reports']} unique public reports into aggregates only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
