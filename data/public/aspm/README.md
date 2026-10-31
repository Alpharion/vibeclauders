# Genuine AAR label drop-in (FAA ASPM)

No file here = AAR capability `unavailable` (unmet core Challenge 5 requirement).
FAA ASPM hourly/quarter-hour data needs an authenticated ASPM account
(https://www.aspm.faa.gov/ -> Direct Login / MyAccess). The agent does not log in
or script around that gate; a team member with access exports the data.

## Requested extract

- Report: ASPM Airport Analysis / Airport Quarter Hour (or hourly), CSV export
- Airports: ATL, DFW
- Local dates: 2023-01-01 through 2025-07-31 (train 2023, validate 2024, test 2025-01..07)
- Fields: LOCID, YYYYMMDD, HR_LOCAL **or** HR_GMT (say which), QTR if quarter-hour,
  AAR (facility-set Airport Arrival Rate, arrivals/hour); optional ADR, scheduled/actual
  arrivals, runway configuration, VMC/IMC
- Label definition: facility-set called AAR, not actual arrival throughput, GDP program
  rate or efficiency AAR. Record the ASPM field definition alongside the export.

## Use

Save as `data/public/aspm/<name>.csv` (it is git-ignored), then:

    python -m src.data_capacity run --cache-only            # basis inferred from HR_LOCAL/HR_GMT
    python -m src.data_capacity run --cache-only --aar-time-basis local   # if columns are date+hour

Accepted headers are documented in `src/data_capacity/capacity.py`. Quarter-hour rates are
averaged per hour (never summed); hours missing a quarter are dropped.
