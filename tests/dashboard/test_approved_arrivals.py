from pathlib import Path
from src.dashboard.data import load_bundle
from src.dashboard import outputs, views


def test_published_approved_arrivals_are_visible_without_preview():
    bundle = load_bundle(Path(__file__).resolve().parents[2])
    assert not outputs.agreement_pending(bundle)
    table = bundle.table('throughput_forecast')
    row = table.iloc[0]
    result = outputs.movement_forecasts(bundle, views.resolve_airport(row.airport), row.asof_utc, False)
    assert result.at(row.target_hour_utc, 'arrival') is not None
    assert not result.held
    assert result.at(row.target_hour_utc, 'departure') is None
