# Garrison at Graham | Neighborhood Safety

A public, aggregate-only dashboard for reported incidents within 1,000 feet of
715 N. Graham St., Charlotte. The daily view and July 2026 historical archive are
separate. Private Association documents are not included.

## Deployment status

This package targets the dedicated **public** repository
`nathanieldlewis/garrison-neighborhood-safety` and a **public** GitHub Pages site.
Only `public/` is uploaded to Pages. The initial snapshot stays pending until a
successful live CMPD refresh; never substitute historical counts for current data.
Check Actions and the Pages deployment for current operational status.

## What members receive

A public page with a fixed 1,000-foot boundary; 30-, 90-, 365-day and YTD reporting
windows; equal-duration prior-year comparisons; category counts and percentages;
twelve completed calendar months; a full reconciliation of exclusions; explicit
freshness warnings; CSV exports; print styling; and the 55-row historical table.
No visitor login, third-party analytics, external fonts or JavaScript CDNs are
used by the site. There is no street map or incident-pin display in this version.

## Deployment: public site repository and GitHub Pages

This repository contains only the public site package, its aggregate data, tests,
and operating documentation. Its source and commit history are public. Only the
reviewed `public/` directory is deployed as the website. Do not add HOA PDFs,
correspondence, financials, resident records or project exports.

1. Open https://github.com/nathanieldlewis/garrison-neighborhood-safety/settings/pages
   and select **GitHub Actions** under Build and deployment → Source.
2. Open Actions → **Refresh and publish neighborhood safety** → **Run workflow**
   on `main`. The workflow explicitly requests content, Pages and OIDC permissions.
3. Wait for the deployment and data-refresh checks; inspect any failure before
   sharing as a current reporting service. The deployment output reports the URL.
4. Expected project URL (verify the deployment before sharing):
   https://nathanieldlewis.github.io/garrison-neighborhood-safety/

The daily target is **6:17 a.m. America/New_York** (5:17 a.m. Central), including
DST changes. GitHub may delay or drop scheduled runs. Failed refreshes retain the
last good snapshot and publish a warning. A final failing step flags the run for
operator attention even when the warning page deployed successfully.

GitHub Pages serves static files and cannot securely enforce a shared password.
No password or client-side password gate is implemented. If access control is
needed later, move to a host that authenticates requests before serving assets.

`scripts/publish-github.sh` now only configures Pages and dispatches this workflow
for the existing site repository. It never changes repository visibility.

## First-production-run acceptance checks

1. The workflow succeeds and the real site opens without authentication on a phone
   and a computer. Four current cards contain actual fetched counts, not `Pending`.
2. Confirm `scope.radius_feet = 1000`, coordinates `35.23579, -80.84027`, Eastern
   report dates, the exact current/comparison windows, and the source schema.
3. Reconcile criminal reports plus the three exclusion groups to all returned
   reports. Compare a sample against the CMPD source using the same geography,
   dates and exclusions. A separately produced CMPD extract may use other rules.
4. Check the latest citywide report date and any source-activity warning. It is not
   a completeness cutoff. Do not represent a fresh download as complete coverage.
5. Confirm that no raw reports or private records appear in the repository
   or deployed assets. Check CSV downloads, the historical table and print output.
6. Verify the next scheduled morning run and designate a maintainer to check
   failures. No next-day run has been verified as part of this delivery.

## Data method

Source: City of Charlotte / CMPD Incidents, layer 0.

- The collector uses the published coordinates in a 1,000-foot ArcGIS radius
  query. Public geocoding may be generalized. This is not parcel attribution.
- It refetches the entire analysis horizon, about two years, on each run so older
  corrections are not missed. It does not simply append new reports.
- It obtains all object IDs, checks the count, fetches in batches of 400, and checks
  the IDs again. Missing rows, truncation and inconsistent IDs fail the refresh.
- It deduplicates by `INCIDENT_REPORT_ID`. Identical repeats count once; conflicting
  report versions require review rather than an arbitrary choice.
- Dates use `DATE_REPORTED`, converted from UTC epoch values to Eastern Time.
  This is not the date the incident occurred. The current partial day is excluded.
- A report marked unfounded in either clearance field is excluded first. Remaining
  800-series non-criminal codes are excluded next. Unrecognized codes are excluded
  and shown separately. Exclusions are mutually exclusive, not overlapping.
- Every remaining report has exactly one category based on its highest NIBRS code.
  This is not an offense-level census. Lower-ranked offenses can be absent.
- A comparison has the same number of days and ends one calendar year earlier.
  For leap-year YTD comparisons the start can differ by one day; exact dates are
  exposed. On January 1, the empty current YTD window is unavailable, not zero.
- Counts are withheld when the source's earliest observed citywide report date is
  too recent for the entire current window. Unsupported comparisons are withheld.
  This is a basic retention check, not proof of complete source history.
- The public output contains aggregates and timestamps only. Report IDs, individual
  dates and locations, narratives, names and demographics are not published.
  Daily aggregate counts do not represent individual report records.
- There is no reliable firearm-specific metric in this source schema. Code 520 is
  not treated as a gun-only offense. The historical selected-gun grouping stays
  in the archive and is not expanded by separately adding the June 13 incident.

## Failure and stale-data behavior

A network error, schema change, incomplete batch, conflicting duplicate or large
history disappearance stops the refresh. `latest.json` retains the last successful
snapshot. `status.json` records a safe, generic error. No failed request becomes a
zero count. The site shows a warning after a failed check or 36 hours without a
successful check. If the site itself cannot read or validate the snapshot, it
withholds current statistics.

A citywide maximum report date more than three days behind the requested window
end produces a source-activity warning. This is not a measured publication lag.
No completeness cutoff is asserted. If more than half of overlapping history
vanishes, an operator must investigate. The explicit CLI override
`--accept-history-change` is for reviewed changes only and is not in the schedule.

GitHub's public-repository schedule inactivity rule also requires monitoring.
Daily snapshot/status commits provide repository activity, but that does not
replace an accountable maintainer, notifications or a check that the schedule ran.
Enable workflow notifications for the maintainer. Exact daily delivery is not an
SLA offered by this package or by the default scheduler.

## Historical-source cautions

The archive comes from the supplied `Garrison_Project_Context.md`, reproduced in
the Association's July 2026 briefing, page 6. The original CMPD extract and original
incident report were not in the migration export. The 55 category rows reconcile
to 870 and 893. The source documents themselves are not copied into this package.

The website makes three material distinctions from some narrative statements in
the briefing: the total includes non-criminal reports; overlapping five-year
percent changes are not annual growth rates; and the two selected gun categories
sum to 21 earlier and 20 later, rather than showing an increase. The original
briefing remains unchanged and is not published here.

## Validation completed in this delivery

- 35 offline Python tests passed, covering classification, deduplication, period
  boundaries, time zones, source truncation, exclusions, privacy and failure retention.
- JavaScript syntax was checked. The offline preview was rendered at 1440-pixel
  desktop and 390-pixel mobile widths without horizontal overflow.
- Period selectors, historical and current-summary CSV exports, the twelve-month
  chart, failed-refresh retention, stale warnings and invalid-data withholding were
  exercised in a browser. Live-state UI tests used synthetic fixtures only. Those
  fixtures are not in the deployed assets or the delivered preview.
- A live CMPD pull, an actual GitHub deployment and an unattended next-day run have
  NOT been completed or verified.

## Local development

Python 3.11 or newer is required. No Python package installation is needed.

```bash
python3 -m unittest discover -s tests -v
python3 src/refresh.py                   # requires network access to CMPD
python3 -m http.server 8000 --directory public
```

Open the local server in a browser. To create a portable single-file preview:

```bash
python3 scripts/make_preview.py Garrison_Neighborhood_Safety_Preview.html
```

The preview captures a snapshot. It does not activate a schedule or update itself.
Tests contain clearly marked synthetic records only; they are never loaded by the
production site. Keep test fixtures out of the deployed `public/` directory.

## Primary technical references

- Source layer and published fields: https://gis.charlottenc.gov/arcgis/rest/services/CMPD/CMPDIncidents/MapServer/0
- Source dataset: https://data.charlottenc.gov/datasets/charlotte::cmpd-incidents-1
- City-provided catalog description and reuse metadata: https://catalog.data.gov/dataset/cmpd-incidents
- GitHub Pages workflow requirements: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Schedule, time zones, delay and inactivity rules: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

Attribution: City of Charlotte / Charlotte-Mecklenburg Police Department.
Changes: radius and date filtering, classification, exclusions and aggregation.
This is independent community analysis; no City or CMPD endorsement is implied.
