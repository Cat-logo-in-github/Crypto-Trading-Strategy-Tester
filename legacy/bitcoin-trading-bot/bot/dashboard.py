"""
dashboard.py

Terminal dashboard for the trading bot.
Displays live bot status.
"""

from rich.console import Console
from rich.table import Table
from rich.live import Live

from bot.config import SYMBOL


class Dashboard:

    def __init__(self):

        self.console = Console()


    def create_table(
        self,
        price,
        signal,
        wallet
    ):

        table = Table(
            title=f"Bitcoin Trading Bot - {SYMBOL}"
        )

        table.add_column(
            "Metric",
            style="cyan"
        )

        table.add_column(
            "Value",
            style="green"
        )


        table.add_row(
            "BTC Price",
            f"${price:,.2f}"
        )

        table.add_row(
            "Signal",
            signal
        )

        table.add_row(
            "Cash",
            f"${wallet.cash:,.2f}"
        )

        table.add_row(
            "BTC Holdings",
            f"{wallet.btc:.8f}"
        )

        table.add_row(
            "Portfolio",
            f"${wallet.total_value(price):,.2f}"
        )


        if wallet.has_position():

            table.add_row(
                "Position",
                "LONG BTC"
            )

            table.add_row(
                "Entry Price",
                f"${wallet.entry_price:,.2f}"
            )

            table.add_row(
                "Unrealized P/L",
                f"${wallet.unrealized_profit(price):,.2f}"
            )

        else:

            table.add_row(
                "Position",
                "NO POSITION"
            )


        return table


    def update(
        self,
        live_display,
        price,
        signal,
        wallet
    ):
        """
        Update an existing live dashboard.
        """

        live_display.update(
            self.create_table(
                price,
                signal,
                wallet
            )
        )


    def run_live(self):
        """
        Create a Rich live display context.
        """

        return Live(
            console=self.console,
            refresh_per_second=1
        )