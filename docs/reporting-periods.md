# Reporting periods, scope and annual trends

## Display contract

The scope strip identifies the fixed 1,000-foot radius around 715 N. Graham St.,
Charlotte, NC; the criminal-report definition; the last successful data fetch in
Eastern Time; and the newest report date observed in the citywide CMPD feed.
That source date is not a certified completeness cutoff. Failed checks retain
and identify the last successful snapshot. A snapshot older than 36 hours is
flagged beside its timestamp.

Each period button shows its exact inclusive dates. The selected interval and
its equal-duration prior-year comparator are displayed together above the
metrics. Dates are taken from the loaded snapshot, never recalculated using a
visitor's local clock. The selector applies to totals, category mix, category
changes and reconciliation, not to the separately dated monthly or annual views.

## Annual series (Figure 1.06)

The collector queries from January 1 three calendar years before the current
year, through the previous completed reporting day. The annual series contains
three completed, non-overlapping calendar years and the current year to date.
It uses the same deduplication, report-date time zone, classification and
exclusion logic as the shorter windows. It is not derived from the historical
five-year extract. Source coverage flags are honored; missing years are not zero.

Current YTD actuals remain integers and are labeled PARTIAL YEAR. Annualized
estimates are separate fields and are not inserted into reported counts:

    annualized estimate = YTD actual / elapsed calendar days * days in the year

Leap years use 366 days. Estimates are rounded to one decimal and withheld for
fewer than 30 completed days, incomplete observed source coverage, or a citywide
source-activity gap exceeding three days. The current-year bar uses a solid
segment for actual reports and a hatched extension for the remaining year at
that pace. The estimate is not a forecast and does not adjust for seasonality,
late reports or enforcement changes. Earlier calendar years may also be revised.

The annual category selector and CSV export preserve these distinctions. CSV
columns separate actual reports from annualized estimates and include dates,
day counts, source, fixed center, radius, refresh time and coverage flags.

## Validation and publication

The existing 35 collector tests are retained. Nineteen annual tests cover year
boundaries, leap years, empty YTD, source delays, incomplete coverage, category
reconciliation, duplicates, estimate formulas and the expanded history guard.
The page uses one validated snapshot; reporting.js does not fetch a second copy.
No report-level records, personal information or private HOA documents are added.
The daily-refresh workflow and GitHub Pages publishing target are unchanged.
