"""
trader.py

Handles trade execution.

Connects strategy signals to the wallet.
"""

from bot.strategy import TradingStrategy
from bot.paper_wallet import PaperWallet

from bot.config import (
    RISK_PER_TRADE,
    ATR_MULTIPLIER,
    MAX_POSITION_SIZE
)


class Trader:

    def __init__(self, wallet=None):

        self.wallet = wallet or PaperWallet()

        self.last_action = "NONE"


    def execute(
        self,
        signal,
        price,
        atr=None
    ):
        """
        Execute a trading signal.

        Parameters:
            signal: BUY / SELL / HOLD
            price : current market price

        Returns:
            action result
        """

        result = {
            "signal": signal,
            "price": price,
            "executed": False
        }


        # -------------------------
        # BUY
        # -------------------------

        if signal == TradingStrategy.BUY:

            # Avoid buying twice
            if self.wallet.has_position():
                result["message"] = "Already holding BTC"

                return result


            # -------------------------
            # Dynamic position sizing
            # -------------------------

            if atr is None:

                trade_amount = self.wallet.cash * 0.10

            else:

                risk_money = (
                    self.wallet.cash *
                    RISK_PER_TRADE
                )

                stop_distance = (
                    atr *
                    ATR_MULTIPLIER
                )


                if stop_distance <= 0:
                    return result


                position_value = (
                    risk_money /
                    stop_distance
                )


                max_position = (
                    self.wallet.cash *
                    MAX_POSITION_SIZE
                )


                trade_amount = min(
                    position_value,
                    max_position
                )


            success = self.wallet.buy(
                price,
                trade_amount
            )

            if success:
                self.last_action = "BUY"

                result["executed"] = True
                result["message"] = "BUY executed"


        # -------------------------
        # SELL
        # -------------------------

        elif signal == TradingStrategy.SELL:


            # Cannot sell nothing
            if not self.wallet.has_position():

                result["message"] = "No BTC position"

                return result


            success = self.wallet.sell(price)


            if success:

                self.last_action = "SELL"

                result["executed"] = True
                result["message"] = "SELL executed"


        # -------------------------
        # HOLD
        # -------------------------

        else:

            result["message"] = "No trade"


        return result