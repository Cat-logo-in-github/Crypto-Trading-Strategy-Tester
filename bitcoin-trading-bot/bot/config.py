"""
Configuration settings for the Bitcoin Trading Bot.

All configurable values should live here.
"""

from dotenv import load_dotenv
import os

# ----------------------------------------------------
# Load environment variables
# ----------------------------------------------------

load_dotenv()

# ----------------------------------------------------
# Trading Settings
# ----------------------------------------------------

SYMBOL = "BTC/USDT"

TIMEFRAME = "1h"

EXCHANGE = "binance"

PAPER_TRADING = True

LOOP_INTERVAL = 10  # seconds

# ----------------------------------------------------
# Starting Balance
# ----------------------------------------------------

STARTING_BALANCE = 10_000.00

RISK_PER_TRADE = 0.02

# ----------------------------------------------------
# Risk Management
# ----------------------------------------------------

STOP_LOSS = 0.03      # 3%

TAKE_PROFIT = 0.06    # 6%

TRAILING_STOP = 0.02  # 2%

# ----------------------------------------------------
# Indicator Settings
# ----------------------------------------------------

EMA_FAST = 20

EMA_SLOW = 50

RSI_PERIOD = 14

RSI_BUY = 35

RSI_SELL = 70

MACD_FAST = 12

MACD_SLOW = 26

MACD_SIGNAL = 9

# ----------------------------------------------------
# Data Settings
# ----------------------------------------------------

OHLCV_LIMIT = 250

# ----------------------------------------------------
# Logging
# ----------------------------------------------------

LOG_LEVEL = "INFO"

LOG_FILE = "logs/bot.log"

# ----------------------------------------------------
# Data Files
# ----------------------------------------------------

TRADE_HISTORY = "data/trades.csv"

CANDLE_HISTORY = "data/candles.csv"

# ----------------------------------------------------
# Optional API Keys
# (Unused during paper trading)
# ----------------------------------------------------

API_KEY = os.getenv("API_KEY", "")

API_SECRET = os.getenv("API_SECRET", "")

# ----------------------------------------------------
# Dashboard
# ----------------------------------------------------

REFRESH_RATE = 1

# ----------------------------------------------------
# ATR values for position sizing
# ----------------------------------------------------

ATR_PERIOD = 14

ATR_MULTIPLIER = 2

MAX_POSITION_SIZE = 0.95