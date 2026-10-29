"""
analysis.visualization.drawdown_plot

Portfolio underwater drawdown visualization.

Displays:
- percentage decline from previous equity peak

Visualization only.
No calculations.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from analysis.engine.metrics.drawdown import (
    drawdowns,
)

from analysis.engine.metrics.equity import (
    EquityPoint,
)



def plot_drawdown(
    equity_curve: tuple[EquityPoint, ...],
    *,
    title: str = "Portfolio Drawdown",
) -> None:
    """
    Plot portfolio underwater curve.
    """

    if not equity_curve:
        return


    values = drawdowns(
        equity_curve
    )


    timestamps = [
        point.timestamp
        for point in equity_curve
    ]


    plt.figure(
        figsize=(14, 4)
    )


    plt.plot(
        timestamps,
        values,
        color="crimson",
        linewidth=2,
    )


    plt.fill_between(
        timestamps,
        values,
        0,
        color="crimson",
        alpha=0.25,
    )


    plt.axhline(
        0,
        color="black",
        linewidth=1,
    )


    plt.title(
        title
    )


    plt.xlabel(
        "Time"
    )


    plt.ylabel(
        "Drawdown %"
    )


    plt.gca().yaxis.set_major_formatter(
        lambda x, _: f"{x:.2%}"
    )


    plt.grid(
        alpha=0.3
    )


    plt.tight_layout()

    plt.show()