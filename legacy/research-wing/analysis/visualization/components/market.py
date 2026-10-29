"""
analysis.visualization.components.market

Market visualization primitives.

Responsible for:
- OHLC candlestick rendering
- composing visualization overlays

Does NOT:
- calculate indicators
- calculate trades
- perform analytics

This module is the base chart layer for:
- trade analysis
- strategy analysis
- signal analysis
- execution analysis
"""

from __future__ import annotations

import plotly.graph_objects as go

from analysis.engine.models.report import ResearchReport

from analysis.visualization.theme import (
    PLOT_TEMPLATE,
)

from analysis.visualization.components.trade_overlay import (
    add_trade_overlays,
)



def market_figure(
    report: ResearchReport,
    *,
    show_trades: bool = True,
    height: int = 700,
) -> go.Figure:
    """
    Create interactive OHLC market chart.

    Parameters
    ----------
    report:
        Research report containing candles.

    show_trades:
        Overlay completed trade markers.

    height:
        Chart height.

    Returns
    -------
    plotly.graph_objects.Figure
    """

    fig = go.Figure()


    candles = report.candles


    if not candles:

        fig.update_layout(
            title="Market Data unavailable",
            template=PLOT_TEMPLATE,
        )

        return fig



    fig.add_trace(

        go.Candlestick(

            x=[
                candle.timestamp
                for candle in candles
            ],

            open=[
                candle.open
                for candle in candles
            ],

            high=[
                candle.high
                for candle in candles
            ],

            low=[
                candle.low
                for candle in candles
            ],

            close=[
                candle.close
                for candle in candles
            ],

            name="Price",

        )

    )



    # Overlay layers
    #
    # The market chart is the canvas.
    # Other components paint on top.

    if show_trades:

        add_trade_overlays(
            fig,
            report,
        )



    fig.update_layout(

        template=PLOT_TEMPLATE,

        height=height,

        hovermode="closest",

        xaxis_rangeslider_visible=False,

        margin=dict(
            l=40,
            r=20,
            t=40,
            b=40,
        ),

    )


    return fig