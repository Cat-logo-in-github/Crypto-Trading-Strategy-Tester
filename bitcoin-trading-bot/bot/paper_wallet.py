"""
paper_wallet.py

Simple paper trading wallet.
Tracks virtual cash, BTC holdings and trade history.
"""

from bot.config import STARTING_BALANCE


class PaperWallet:

    def __init__(self):

        self.cash = STARTING_BALANCE
        self.btc = 0.0

        self.entry_price = None

        self.trade_history = []

    def buy(
        self,
        price: float,
        amount: float
    ):

        if self.cash <= 0:
            return False

        # Don't allow buying more than available cash
        amount = min(
            amount,
            self.cash
        )

        btc_amount = amount / price

        # Add to existing BTC instead of replacing
        self.btc += btc_amount

        self.entry_price = price

        # Only remove what we invested
        self.cash -= amount

        self.trade_history.append({
            "side": "BUY",
            "price": price,
            "btc": btc_amount,
            "amount": amount
        })

        return True

    def sell(self, price: float):

        if self.btc <= 0:
            return False

        cash_received = self.btc * price

        self.cash += cash_received

        self.trade_history.append({
            "side": "SELL",
            "price": price,
            "btc": self.btc,
            "amount": cash_received
        })

        self.btc = 0.0
        self.entry_price = None

        return True

    def total_value(self, current_price: float):

        return self.cash + (self.btc * current_price)

    def unrealized_profit(self, current_price: float):

        if self.entry_price is None:
            return 0.0

        return (current_price - self.entry_price) * self.btc

    def has_position(self):

        return self.btc > 0

    def print_status(self, current_price: float):

        print("-" * 40)
        print(f"Cash        : ${self.cash:,.2f}")
        print(f"BTC         : {self.btc:.8f}")
        print(f"BTC Price   : ${current_price:,.2f}")
        print(f"Portfolio   : ${self.total_value(current_price):,.2f}")
        print(f"Unrealized  : ${self.unrealized_profit(current_price):,.2f}")
        print("-" * 40)