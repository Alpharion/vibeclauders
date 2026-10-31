"""Stable flight identity.

The shared contract fixes ``src.shared.flight_key(date, carrier, number,
origin, dest, scheduled_hhmm)`` (owned by Member 3). If that module is absent
in this checkout, a provisional implementation is used and every artifact
records ``flight_key_impl`` so IDs can be re-verified against Member 2 before
acceptance.
"""
from __future__ import annotations

import hashlib


def _provisional_flight_key(date, carrier, number, origin, dest, scheduled_hhmm) -> str:
    parts = [
        str(date)[:10],
        str(carrier).strip().upper(),
        str(int(float(number))),
        str(origin).strip().upper(),
        str(dest).strip().upper(),
        f"{int(float(scheduled_hhmm)):04d}",
    ]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


try:  # pragma: no cover - depends on Member 3's checkout
    from src.shared import flight_key as _shared_flight_key  # type: ignore

    flight_key = _shared_flight_key
    FLIGHT_KEY_IMPL = "src.shared.flight_key"
except Exception:
    flight_key = _provisional_flight_key
    FLIGHT_KEY_IMPL = "provisional:src.data_capacity.identity (src.shared absent; verify against Member 2)"
