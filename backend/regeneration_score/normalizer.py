"""
STEP 2 - normalization layer.

Every module's raw output gets clamped and rescaled to a common 0-100
range here, before it ever reaches weighting or confidence adjustment.
Nothing else in this package is allowed to hand-roll its own scaling -
that's the whole point of pulling it out into one tested function.
"""

from __future__ import annotations


def normalize_score(raw_value: float, min_val: float, max_val: float) -> float:
    """Clamp raw_value to [min_val, max_val], then scale linearly to 0-100."""
    if max_val <= min_val:
        raise ValueError(f"max_val ({max_val}) must be greater than min_val ({min_val})")
    clamped = max(min_val, min(raw_value, max_val))
    return round(((clamped - min_val) / (max_val - min_val)) * 100, 1)
