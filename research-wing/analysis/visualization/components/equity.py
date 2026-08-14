"""
analysis.visualization.components.equity

Equity curve visualization component.

Consumes EquityPoint sequences and returns
interactive Plotly figures.

This module:
- creates charts
- does not run simulations
- does not calculate performance metrics
"""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go

from analysis.engine.metrics.equity import EquityPoint

from analysis.visualization.theme import (
    GREEN,
    PLOT_TEMPLATE,
    GRAPH_CONFIG,
)



def equity_figure(
    equity_curve: Sequence[EquityPoint],
) -> go.Figure:
    """
    Create interactive equity curve chart.

    Features:
    - zoom
    - pan
    - hover values
    - fullscreen through dashboard toolbar
    """


    timestamps = [
        point.timestamp
        for point in equity_curve
    ]


    values = [
        point.equity
        for point in equity_curve
    ]


    figure = go.Figure()



    figure.add_trace(

        go.Scatter(

            x=timestamps,

            y=values,

            mode="lines",

            name="Equity",

            line={
                "color": GREEN,
                "width": 2,
            },

            hovertemplate=(

                "<b>%{x}</b>"
                "<br>"
                "Equity: %{y:.2f}"
                "<extra></extra>"

            ),

        )

    )



    figure.update_layout(

        title="Portfolio Equity",

        template=PLOT_TEMPLATE,

        hovermode="x unified",

    )


    return figure