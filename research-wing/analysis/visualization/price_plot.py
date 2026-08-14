"""
analysis.visualization.price_plot

Price chart visualization.

Displays:
- market price
- executed trades

Visualization only.
No calculations.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from analysis.engine.market import Candle
from analysis.engine.trade import Trade, TradeSide


def plot_price_with_trades(
    candles: list[Candle],
    trades: tuple[Trade, ...],
    *,
    title: str = "Price Chart",
) -> None:
    """
    Plot market price with execution markers.
    """


    timestamps = [
        candle.timestamp
        for candle in candles
    ]

    prices = [
        candle.close
        for candle in candles
    ]


    plt.figure(
        figsize=(14, 6)
    )


    plt.plot(
        timestamps,
        prices,
        label="Price",
        color="black",
    )


    buys = [
        trade
        for trade in trades
        if trade.side is TradeSide.BUY
    ]


    sells = [
        trade
        for trade in trades
        if trade.side is TradeSide.SELL
    ]


    if buys:

        plt.scatter(
            [
                trade.timestamp
                for trade in buys
            ],
            [
                trade.price
                for trade in buys
            ],
            marker="^",
            color="green",
            s=80,
            label="BUY",
        )


    if sells:

        plt.scatter(
            [
                trade.timestamp
                for trade in sells
            ],
            [
                trade.price
                for trade in sells
            ],
            marker="v",
            color="red",
            s=80,
            label="SELL",
        )


    plt.title(title)

    plt.xlabel(
        "Time"
    )

    plt.ylabel(
        "Price"
    )


    plt.legend()

    plt.grid(
        alpha=0.3
    )


    plt.tight_layout()

    plt.show()