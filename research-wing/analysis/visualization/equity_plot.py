"""
analysis.visualization.equity_plot

Equity curve visualization.

This module converts portfolio equity history
into visual representations.

It does not:
- run backtests
- access portfolios
- calculate metrics
- modify simulation data
"""

from __future__ import annotations

from typing import Sequence

import matplotlib.pyplot as plt

from analysis.engine.metrics.equity import EquityPoint



def plot_equity_curve(
    equity_curve: Sequence[EquityPoint],
    *,
    title: str = "Portfolio Equity Curve",
    figsize: tuple[int, int] = (12, 6),
    show: bool = True,
):
    """
    Plot portfolio equity over time.

    Parameters
    ----------
    equity_curve:
        Time series of portfolio valuation snapshots.

    title:
        Chart title.

    figsize:
        Matplotlib figure size.

    show:
        Whether to display immediately.

    Returns
    -------
    matplotlib.figure.Figure
        Generated figure.
    """

    if not equity_curve:
        raise ValueError(
            "Cannot plot empty equity curve."
        )


    timestamps = [
        point.timestamp
        for point in equity_curve
    ]


    values = [
        point.equity
        for point in equity_curve
    ]


    fig, ax = plt.subplots(
        figsize=figsize
    )


    ax.plot(
        timestamps,
        values,
        linewidth=2,
        label="Equity",
    )


    ax.set_title(
        title
    )

    ax.set_xlabel(
        "Time"
    )

    ax.set_ylabel(
        "Portfolio Value"
    )


    ax.grid(
        True,
        alpha=0.3,
    )


    ax.legend()


    fig.autofmt_xdate()


    plt.tight_layout()


    if show:
        plt.show()


    return fig