# BTS On-Time Reporting: ATL/DFW extracts (2023-01 to 2025-07)

31 monthly parquet files, **3,255,141 flights** touching ATL or DFW (departures or arrivals), from the BTS On-Time Reporting Carrier On-Time Performance archives (`https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_<Y>_<M>.zip`).

- Population: reporting carriers only. Excludes non-reporting airlines, cargo, GA, military and most international flights. Not complete airport demand.
- Columns are renamed to the challenge CSV names (`FL_DATE`, `OP_UNIQUE_CARRIER`, `CRS_DEP_TIME`, `DEP_DELAY`, ...) by `src/data_capacity/bts.py`, so `flights.build_flights` reads them directly.
- Actual times, delays and cause minutes are outcomes. Never use them as predictors at an earlier cutoff.
- Each `*.meta.json` records the SHA-256 of the source zip it was cut from, the extract's SHA-256 and row count.
- The raw nationwide zips (about 859 MB) are not committed. Recreate them and these extracts with:

```powershell
python -m src.data_capacity bts --workers 4 --months 2023-01 2023-02 ... 2025-07
```

| File | Rows | Source zip SHA-256 (first 16) |
|---|---:|---|
| `ontime_ATL_DFW_2023_01.parquet` | 93,215 | `327924faa362d360` |
| `ontime_ATL_DFW_2023_02.parquet` | 87,164 | `bfa6eb7bebb53f10` |
| `ontime_ATL_DFW_2023_03.parquet` | 100,826 | `1a61dce7c50e5c4f` |
| `ontime_ATL_DFW_2023_04.parquet` | 99,764 | `adf3ecf6e3763a55` |
| `ontime_ATL_DFW_2023_05.parquet` | 104,181 | `aec2e926b11e55f8` |
| `ontime_ATL_DFW_2023_06.parquet` | 106,224 | `67dc6b993ba2e7c2` |
| `ontime_ATL_DFW_2023_07.parquet` | 110,699 | `b1b73635dcb2add3` |
| `ontime_ATL_DFW_2023_08.parquet` | 110,440 | `d374aa3ec2b844d4` |
| `ontime_ATL_DFW_2023_09.parquet` | 104,723 | `4e7bc3f76857accd` |
| `ontime_ATL_DFW_2023_10.parquet` | 108,995 | `a92cc51c6bb1e7fc` |
| `ontime_ATL_DFW_2023_11.parquet` | 102,004 | `9ad54595568704a1` |
| `ontime_ATL_DFW_2023_12.parquet` | 102,430 | `c8391a3f06749b6e` |
| `ontime_ATL_DFW_2024_01.parquet` | 98,819 | `fe089b45523f9d4a` |
| `ontime_ATL_DFW_2024_02.parquet` | 94,043 | `8463683d100504a9` |
| `ontime_ATL_DFW_2024_03.parquet` | 106,933 | `e2c5021406f480e8` |
| `ontime_ATL_DFW_2024_04.parquet` | 105,567 | `d8b1e88626a7375d` |
| `ontime_ATL_DFW_2024_05.parquet` | 112,851 | `03e4ae26c2d1247d` |
| `ontime_ATL_DFW_2024_06.parquet` | 112,966 | `4f329439fd6892aa` |
| `ontime_ATL_DFW_2024_07.parquet` | 117,143 | `4d992fee134137b3` |
| `ontime_ATL_DFW_2024_08.parquet` | 113,577 | `58d651379af90cc4` |
| `ontime_ATL_DFW_2024_09.parquet` | 107,803 | `c0df7503b0050ca4` |
| `ontime_ATL_DFW_2024_10.parquet` | 114,259 | `a417136d6c166373` |
| `ontime_ATL_DFW_2024_11.parquet` | 105,306 | `26b6e89e7c1f6616` |
| `ontime_ATL_DFW_2024_12.parquet` | 108,579 | `a324577aa76d1f0a` |
| `ontime_ATL_DFW_2025_01.parquet` | 96,939 | `868387dcedaef1b8` |
| `ontime_ATL_DFW_2025_02.parquet` | 90,058 | `12dc8dbdb3c8b3c2` |
| `ontime_ATL_DFW_2025_03.parquet` | 105,988 | `9c80fbc2112cdbf3` |
| `ontime_ATL_DFW_2025_04.parquet` | 101,279 | `f3718431e988e2af` |
| `ontime_ATL_DFW_2025_05.parquet` | 107,787 | `17c3419d7169b313` |
| `ontime_ATL_DFW_2025_06.parquet` | 110,741 | `087b75e4e059516c` |
| `ontime_ATL_DFW_2025_07.parquet` | 113,838 | `74309a3a734d5104` |
