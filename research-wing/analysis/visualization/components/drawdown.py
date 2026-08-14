"""
analysis.visualization.components.drawdown

Portfolio drawdown visualization.

Creates an underwater chart showing decline
from historical equity peaks.

Consumes equity history only.

Does NOT:
- calculate portfolio value
- modify results
- access simulation state
"""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go

from analysis.engine.metrics.equity import EquityPoint
from analysis.engine.metrics.drawdown import drawdowns

from analysis.visualization.theme import (
    RED,
    PLOT_TEMPLATE,
)



def drawdown_figure(
    equity_curve: Sequence[EquityPoint],
) -> go.Figure:
    """
    Create interactive drawdown chart.

    Displays:

    0%
     |
     |
     |____
          \
           \____

    """

    values = drawdowns(
        equity_curve
    )


    timestamps = [
        point.timestamp
        for point in equity_curve
    ]


    figure = go.Figure()



    figure.add_trace(

        go.Scatter(

            x=timestamps,

            y=values,

            mode="lines",

            name="Drawdown",

            fill="tozeroy",

            line={
                "color": RED,
                "width": 2,
            },


            hovertemplate=(

                "<b>%{x}</b>"
                "<br>"
                "Drawdown: %{y:.2%}"
                "<extra></extra>"

            ),

        )

    )



    figure.update_layout(

        title="Portfolio Drawdown",

        template=PLOT_TEMPLATE,

        hovermode="x unified",

        yaxis={
            "tickformat": ".1%",
        },

    )


    return figure