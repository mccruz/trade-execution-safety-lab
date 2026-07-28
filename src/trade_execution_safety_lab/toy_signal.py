"""A deliberately non-economic fixture used only to produce demo order sides."""

from __future__ import annotations

from .models import Side


def alternating_fixture_side(sequence: int) -> Side:
    """Alternate sides by fixture index without using market or strategy data."""

    if sequence < 0:
        raise ValueError("fixture sequence cannot be negative")
    return Side.BUY if sequence % 2 == 0 else Side.SELL
