"""
main.py

Starts the Bitcoin trading bot.
"""

import time


from bot.market import MarketData
from bot.indicators import IndicatorCalculator
from bot.strategy import TradingStrategy
from bot.paper_wallet import PaperWallet
from bot.trader import Trader
from bot.dashboard import Dashboard
from bot.logger import logger
from bot.utils import ensure_directories

from bot.config import LOOP_INTERVAL


def run_bot():

    ensure_directories()

    logger.info(
        "Starting Bitcoin trading bot"
    )


    market = MarketData()

    wallet = PaperWallet()

    trader = Trader(
        wallet
    )

    dashboard = Dashboard()


    with dashboard.run_live() as live:


        while True:

            try:

                # ---------------------
                # Get market data
                # ---------------------

                df = market.fetch_ohlcv()


                market.save_candles(
                    df
                )


                # ---------------------
                # Indicators
                # ---------------------

                df = IndicatorCalculator.add_all(
                    df
                )


                current = df.iloc[-1]


                price = current["close"]


                # ---------------------
                # Strategy
                # ---------------------

                signal = TradingStrategy.generate_signal(
                    df
                )

                logger.info(
                    f"Price={price} "
                    f"EMA20={current['ema_fast']:.2f} "
                    f"EMA50={current['ema_slow']:.2f} "
                    f"RSI={current['rsi']:.2f} "
                    f"MACD={current['macd']:.2f} "
                    f"Signal={current['macd_signal']:.2f} "
                    f"Decision={signal}"
                )


                # ---------------------
                # Trading
                # ---------------------

                result = trader.execute(
                    signal,
                    price,
                    current["atr"]
                )


                if result["executed"]:

                    logger.info(
                        result["message"]
                    )


                # ---------------------
                # Dashboard
                # ---------------------

                dashboard.update(
                    live,
                    price,
                    signal,
                    wallet
                )


                time.sleep(
                    LOOP_INTERVAL
                )


            except Exception as e:

                logger.error(
                    str(e)
                )

                time.sleep(10)



if __name__ == "__main__":

    run_bot()