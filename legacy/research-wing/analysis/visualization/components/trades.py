"""
analysis.visualization.components.trades

Trade visualization overlays.

This module does NOT create charts.

It adds trade information onto
existing market figures.

Expected usage:

    fig = market_figure(report)

    add_trade_markers(
        fig,
        report,
    )

"""

from __future__ import annotations

import plotly.graph_objects as go

from analysis.engine.models.report import ResearchReport

from analysis.visualization.theme import (
    WHITE,
    BLACK,
    BLUE,
)



def add_trade_markers(
    fig: go.Figure,
    report: ResearchReport,
) -> None:
    """
    Add completed trade entry/exit markers.

    Parameters
    ----------
    fig:
        Existing Plotly market figure.

    report:
        Research report containing
        closed trades and candles.

    Notes
    -----
    This function mutates only the
    provided Plotly figure.

    It does not create a new figure.
    """

    if not report.closed_trades:
        return


    candles = report.candles


    if not candles:
        return


    entries_x = []
    entries_y = []

    exits_x = []
    exits_y = []


    for trade in report.closed_trades:

        entry_price = _price_at_time(
            candles,
            trade.entry_time,
        )

        exit_price = _price_at_time(
            candles,
            trade.exit_time,
        )


        entries_x.append(
            trade.entry_time
        )

        entries_y.append(
            entry_price
        )


        exits_x.append(
            trade.exit_time
        )

        exits_y.append(
            exit_price
        )



    fig.add_trace(

        go.Scatter(

            x=entries_x,

            y=entries_y,

            mode="markers",

            name="Entry",

            marker=dict(
                color=WHITE,
                size=14,
                symbol="triangle-up",
            ),

            hovertemplate=(
                "Entry<br>"
                "%{x}<br>"
                "Price: %{y:.2f}"
                "<extra></extra>"
            ),

        )

    )



    fig.add_trace(

        go.Scatter(

            x=exits_x,

            y=exits_y,

            mode="markers",

            name="Exit",

            marker=dict(
                color=BLUE if trade.gross_pnl > 0 else BLACK,
                size=14,
                symbol="triangle-down",
            ),

            hovertemplate=(
                "Exit<br>"
                "%{x}<br>"
                "Price: %{y:.2f}"
                "<extra></extra>"
            ),

        )

    )



def _price_at_time(
    candles,
    timestamp,
) -> float:
    """
    Find nearest candle close price.

    Used only for visualization.
    """

    closest = min(
        candles,
        key=lambda candle:
            abs(
                candle.timestamp - timestamp
            )
    )

    return closest.close