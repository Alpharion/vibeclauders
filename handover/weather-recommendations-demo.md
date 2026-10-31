# Weather recommendations demo

Branch: `codex/member-1-accuracy-integration`.

Run `python -m streamlit run app.py`, select historical replay, then open **Weather → Weather-condition recommendations**. For a published thunderstorm example select DFW, cutoff **2025-07-31 21:00 UTC**, horizon **+3h**.

The visible cards explain the condition, prevailing or conditional TAF evidence, and recommended human review. Four independent triggers cover thunderstorms, visibility below 3 SM, ceiling below 1,000 ft AGL and gusts of at least 25 kt. These screening thresholds are not operational limits. Conditional groups are not converted to probabilities. Missing or post-cutoff weather cannot create a recommendation.

Historical METAR frequencies remain context only, clearly separated from forecasts and recommendations. Revealing later outcomes does not change these cards. The prompts do not publish clearances, flight allocations or claims of intervention benefit.

The same build includes the full-BTS experiment evidence in Evaluation. Late-2024 macro AP improved 12.24% with 0.96% lower Brier; experimental model publication remains separate from the operational classifier. See full-bts-model-results.md for all six cells and updated 2025 backtests, including DFW regressions.
