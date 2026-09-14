"""
Peer/regional benchmarking - "farmers in your district average X" - built
from services/score_history.py's REAL stored regen_score snapshots (never
simulated: there is no honest way to fabricate what other farmers scored).

MIN_PEERS exists for the same reason the Geographic Confidence Ladder never
pretends a single sample is a "district average": comparing one farmer
against one or two other submissions isn't a meaningful regional signal,
it's just naming their neighbour's score. Below that threshold this
returns None and the caller (services/regen/pipeline.py) leaves
peer_comparison null rather than showing a comparison built on noise - the
same "say nothing rather than fabricate confidence" rule the rest of Part C
already follows.
"""

from __future__ import annotations

from typing import Any, Optional

from services import score_history

MIN_PEERS = 3


def build_peer_comparison(farm_id: str, district: Optional[str], current_score: float) -> Optional[dict[str, Any]]:
    if not district:
        return None

    peer_scores = score_history.get_district_peer_scores(district, exclude_farm_id=farm_id)
    if len(peer_scores) < MIN_PEERS:
        return None

    peer_average = round(sum(peer_scores) / len(peer_scores), 1)
    delta = round(current_score - peer_average, 1)
    sign = "+" if delta >= 0 else ""

    return {
        "scope": "district",
        "label": f"{district} district",
        "peer_count": len(peer_scores),
        "peer_average_score": peer_average,
        "your_score": current_score,
        "delta": delta,
        "summary": f"{sign}{delta} points vs. the {len(peer_scores)} other farms tracked in {district} district",
    }
