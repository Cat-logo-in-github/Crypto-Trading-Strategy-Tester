"""
analysis.engine.models.risk

Risk metric result models.

Immutable data containers for
risk and risk-adjusted performance.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskSummary:
    """
    Immutable risk evaluation result.

    Contains risk statistics calculated
    from portfolio equity history.
    """

    volatility: float

    sharpe_ratio: float