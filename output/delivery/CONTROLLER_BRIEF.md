# Controller review brief

Status: **available**. Historical replay only.
KATL | cutoff 2025-07-12T20:00:00+00:00 | +3h.
Risk run: `0949771a54bb4e49b4e215528eb5d46b`.

2 sampled departures scored; 2 flagged.
Review the flagged departures in descending risk order

| Flight ID | Probability | Threshold | Model |
|---|---:|---:|---|
| 460f3042c18b22443112 | 61.2% | 14.6% | weather_enhanced |
| a6e1ef65ebf371bd00f0 | 37.0% | 14.6% | weather_enhanced |

Review current weather and airline/inbound-aircraft status before deciding whether intervention is warranted.

## Boundaries

- Historical replay; these are not current operational alerts.
- This is a separate review briefing, not an action published to the dashboard or queue.
- Coverage is sampled departures, not complete airport traffic; probabilities are not calibrated guarantees.
- No capacity reduction, metering rate, flight time, routing or rescheduling is recommended.
- Qualified human review is required; no delay-minute or fuel benefit is established.

## Evidence

```json
{
  "predictions": "artifacts/risk/predictions.parquet",
  "predictions_sha256": "084efcd74bc6a35c6bf072541c9aa595952d02dab5d5086044416fb994a5a159",
  "manifest_sha256": "94e967c743226fe221b5a8976ece96b6851d7ed59833eed68d821a32543e3263"
}
```
