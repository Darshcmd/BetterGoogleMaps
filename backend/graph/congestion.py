"""BPR congestion model shared by the proposed algorithm and evaluation.

    t(flow) = t_free * (1 + alpha * (flow / capacity)^beta)

Defaults alpha=0.15, beta=4 (US Bureau of Public Roads). Capacities are
estimates (see graph/preprocessing.py), never measured live traffic.
"""

from __future__ import annotations

from .config import BPR_ALPHA, BPR_BETA, BPR_MAX_TIME_FACTOR, MIN_CAPACITY_VPH


def time_factor(flow: float, capacity: float,
                alpha: float = BPR_ALPHA, beta: float = BPR_BETA) -> float:
    cap = capacity if capacity and capacity > 0 else MIN_CAPACITY_VPH
    ratio = max(flow, 0.0) / cap
    return min(1.0 + alpha * (ratio ** beta), BPR_MAX_TIME_FACTOR)


def edge_time_s(length_s: float, flow: float, capacity: float,
                alpha: float = BPR_ALPHA, beta: float = BPR_BETA) -> float:
    return length_s * time_factor(flow, capacity, alpha, beta)
