"""
analysis.engine.metrics.risk

Risk and risk-adjusted performance calculations.

Functions operate only on equity curves.

They do not:
- access portfolio state
- access market data
- execute trades
"""

from __future__ import annotations

from math import sqrt
from typing import Sequence

from analysis.engine.metrics.returns import periodic_returns
from analysis.engine.metrics.equity import EquityPoint
from analysis.engine.models.risk import RiskSummary


def volatility(
    equity_curve: Sequence[EquityPoint],
    annualization_factor: float = 252,
) -> float:
    """
    Calculate annualized return volatility.

    Parameters
    ----------
    equity_curve:
        Portfolio equity history.

    annualization_factor:
        Number of periods per year.

        For daily data:
            252

        For minute data this should later
        be configured externally.

    Returns
    -------
    float
        Annualized volatility.
    """

    returns = periodic_returns(
        equity_curve
    )

    if len(returns) < 2:
        return 0.0


    mean = sum(returns) / len(returns)


    variance = sum(
        (r - mean) ** 2
        for r in returns
    ) / len(returns)


    return sqrt(
        variance
    ) * sqrt(
        annualization_factor
    )



def sharpe_ratio(
    equity_curve: Sequence[EquityPoint],
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252,
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Formula:

        (return - risk free rate)
        -------------------------
             volatility

    """

    returns = periodic_returns(
        equity_curve
    )

    if len(returns) < 2:
        return 0.0


    mean_return = (
        sum(returns)
        /
        len(returns)
    )


    variance = sum(
        (r - mean_return) ** 2
        for r in returns
    ) / len(returns)


    std = sqrt(
        variance
    )


    if std == 0:
        return 0.0


    excess_return = (
        mean_return
        -
        risk_free_rate
    )


    return (
        excess_return
        /
        std
    ) * sqrt(
        annualization_factor
    )


def calculate_risk(
    equity_curve: Sequence[EquityPoint],
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252,
) -> RiskSummary:
    """
    Calculate complete risk summary.
    """

    return RiskSummary(
        volatility=volatility(
            equity_curve,
            annualization_factor,
        ),

        sharpe_ratio=sharpe_ratio(
            equity_curve,
            risk_free_rate,
            annualization_factor,
        ),
    )