"""
analysis.visualization.components.trade_overlay

Trade visualization overlays for market charts.

This module paints execution and position information
onto an existing price chart.

Responsible for:
- execution markers
- position lifecycle visualization
- trade outcome visualization

Does NOT:
- calculate PnL
- reconstruct trades
- modify research objects
"""

from __future__ import annotations

import plotly.graph_objects as go

from analysis.engine.models.report import ResearchReport

from analysis.visualization.theme import (
    GREEN,
    RED,
    TEXT,
)


def add_trade_overlays(
    fig: go.Figure,
    report: ResearchReport,
) -> None:
    """
    Add all trade-related layers.

    Mutates only the provided Plotly figure.

    Layers:
        1. executions
        2. completed position spans
        3. entry/exit connections
    """

    if not report.closed_trades:
        return


    _add_position_regions(
        fig,
        report,
    )


    _add_execution_markers(
        fig,
        report,
    )



def _add_execution_markers(
    fig: go.Figure,
    report: ResearchReport,
) -> None:
    """
    Plot actual execution prices.

    Uses Trade objects directly.
    """

    buy_x = []
    buy_y = []

    sell_x = []
    sell_y = []


    for trade in report.closed_trades:

        entry = trade.entry_trade
        exit = trade.exit_trade


        buy_x.append(
            entry.timestamp
        )

        buy_y.append(
            entry.price
        )


        sell_x.append(
            exit.timestamp
        )

        sell_y.append(
            exit.price
        )



    fig.add_trace(

        go.Scatter(

            x=buy_x,

            y=buy_y,

            mode="markers",

            name="Entry",

            marker=dict(
                symbol="triangle-up",
                size=14,
                color=GREEN,
            ),

            hovertemplate=(
                "BUY<br>"
                "Price: %{y}<br>"
                "Time: %{x}"
                "<extra></extra>"
            ),

        )

    )



    fig.add_trace(

        go.Scatter(

            x=sell_x,

            y=sell_y,

            mode="markers",

            name="Exit",

            marker=dict(
                symbol="triangle-down",
                size=14,
                color=RED,
            ),

            hovertemplate=(
                "SELL<br>"
                "Price: %{y}<br>"
                "Time: %{x}"
                "<extra></extra>"
            ),

        )

    )



def _add_position_regions(
    fig: go.Figure,
    report: ResearchReport,
) -> None:
    """
    Add entry -> exit lifecycle lines.

    Each ClosedTrade receives its own trace.

    This prevents Plotly from connecting
    unrelated trades.
    """

    for trade in report.closed_trades:

        color = (
            GREEN
            if trade.is_winner
            else RED
        )


        fig.add_trace(

            go.Scatter(

                x=[
                    trade.entry_time,
                    trade.exit_time,
                ],

                y=[
                    trade.entry_price,
                    trade.exit_price,
                ],

                mode="lines",

                line=dict(
                    color=color,
                    width=2,
                    dash="dot",
                ),

                hovertemplate=(
                    "Trade<br>"
                    f"PnL: {trade.net_pnl:.2f}<br>"
                    f"Return: {trade.return_pct:.2%}"
                    "<extra></extra>"
                ),

                showlegend=False,

                connectgaps=False,

            )

        )