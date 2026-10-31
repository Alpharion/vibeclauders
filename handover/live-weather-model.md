# Live-input weather model

Open **Live weather**, fetch/refresh weather, and select ATL or DFW. The live-input forecast panel shows learned probabilities at +3/+6/+12 hours. The existing refresh controls update the inputs. Historical replay and its illustrative probability cards are unchanged.

The statistical model learns seasonal airport-specific transitions from current METAR state (low visibility/ceiling, gust and thunderstorm flags) to future observed conditions. Cells use 30 airport-baseline pseudo-observations for smoothing. The target is the first METAR at or after the target time within 60 minutes. Missing targets are excluded, never converted to negative labels.

Training uses 2023 observations with labels available before 2024. Transition probabilities versus airport climatology are selected separately for each condition/lead using 2024 Brier score, excluding labels crossing 2025. The 24 airport/lead/condition test metrics in `artifacts/live_weather/model.json` describe 2025 retrospective performance, not independent live validation. This is a small statistical model, not numerical weather prediction, an official TAF or a calibrated operational forecast.

Live inference uses the existing Aviation Weather Center METAR API. Unknown airports, failed/cached feed status, missing required fields, future timestamps and observations older than 90 minutes are refused. Observations can be older than the training availability latency; forecasts are anchored at refresh time and this mismatch is a limitation. No observation is replaced with an illustrative probability. Conditions are predicted independently and need not sum to 100%.

Rebuild: `python -m tools.delivery.train_live_weather`. The artifact records the input weather-file SHA-256, training/validation row counts, selected methods and test Brier scores. It is included in the delivery package and runtime fingerprint. A live ATL fetch and all 12 live probability outputs were verified on 31 October 2026, alongside stale/cached/unsupported-airport guards. Full release verification is not claimed for this change.
