# Bitcoin Trading Bot

The Bitcoin Trading Bot is a Python-based automated cryptocurrency trading system designed to simulate algorithmic trading using real-time Bitcoin market data.

The project connects to a cryptocurrency exchange through the CCXT library, collects live OHLCV (Open, High, Low, Close, Volume) market data, processes the data using technical indicators, generates trading decisions through a strategy module, and executes simulated trades using a virtual paper trading wallet.

The main goal of this project is to create a structured and modular environment for experimenting with trading strategies, risk management techniques, portfolio tracking, and automated market analysis without risking real capital.

The bot currently operates in paper trading mode, meaning all trades are simulated. No real orders are placed on an exchange. This allows strategies to be tested, monitored, and improved before connecting the system to live trading.

---

# Features

## Market Data

* Connects to cryptocurrency exchanges using CCXT
* Currently configured for:

  * Exchange: Binance
  * Pair: BTC/USDT
  * Timeframe: 1 hour
* Fetches and stores OHLCV candle data

---

## Technical Indicators

The bot supports technical analysis using indicators such as:

* EMA (trend analysis)
* RSI (momentum)
* MACD (trend and momentum confirmation)
* ATR (volatility and position sizing)

Indicators are calculated before every trading decision.

---

## Trading Strategy

The strategy module generates three possible signals:

```
BUY
SELL
HOLD
```

The current strategy is a testing strategy used to validate the trading pipeline.

The strategy system is separated from execution, making it easy to replace with more advanced approaches such as:

* Moving average strategies
* Momentum strategies
* Mean reversion
* Machine learning models

---

## Paper Trading

The bot uses a virtual wallet instead of real funds.

The wallet tracks:

* Cash balance
* BTC holdings
* Entry price
* Portfolio value
* Trade history
* Unrealized profit/loss

Default starting balance:

```
$10,000
```

No real trades are executed.

---

## Risk Management

The trader module includes basic risk controls:

* Risk-based position sizing
* ATR-based trade sizing
* Maximum position limits
* Stop-loss configuration
* Take-profit configuration
* Trailing stop configuration

Current configuration examples:

```
Risk per trade: 2%
Maximum position: 95%
ATR multiplier: 2
```

---

# Project Architecture

The project follows a modular design:

```
project/
│
├── main.py
│
└── bot/
    ├── market.py
    ├── indicators.py
    ├── strategy.py
    ├── trader.py
    ├── paper_wallet.py
    ├── dashboard.py
    ├── logger.py
    ├── utils.py
    └── config.py
```

Component responsibilities:

| File            | Purpose                 |
| --------------- | ----------------------- |
| main.py         | Runs the trading loop   |
| market.py       | Retrieves exchange data |
| indicators.py   | Calculates indicators   |
| strategy.py     | Generates signals       |
| trader.py       | Executes trades         |
| paper_wallet.py | Simulates portfolio     |
| dashboard.py    | Displays live status    |
| logger.py       | Handles logging         |
| config.py       | Stores settings         |

---

# Installation

Clone the repository:

```bash
git clone https://github.com/cat-in-github-logo/CryptocurrencyTradeResearcher.git
cd bitcoin-trading-bot
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it:

Windows:

```bash
venv\Scripts\activate
```

Linux/Mac:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Configuration

All configurable settings are stored in:

```
bot/config.py
```

Important settings include:

```python
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"

STARTING_BALANCE = 10000

RISK_PER_TRADE = 0.02
```

API keys are supported through environment variables, but are not required while using paper trading mode.

Example:

```
API_KEY=
API_SECRET=
```

---

# Running The Bot

Start the bot using:

```bash
python main.py
```

The bot will:

1. Create required directories
2. Connect to the exchange
3. Download market candles
4. Calculate indicators
5. Generate a signal
6. Execute paper trades
7. Update the dashboard
8. Repeat continuously

---

# Data & Logs

Market data is saved to:

```
data/candles.csv
```

Trade records are stored in:

```
data/trades.csv
```

Logs are stored in:

```
logs/bot.log
```

---

# Dashboard

The terminal dashboard displays:

* Current BTC price
* Trading signal
* Cash balance
* BTC holdings
* Portfolio value
* Current position
* Entry price
* Unrealized P/L

Example:

```
Bitcoin Trading Bot - BTC/USDT

BTC Price       $95000
Signal          HOLD
Cash            $10000
BTC Holdings    0
Portfolio       $10000
Position        NO POSITION
```

---

# Development Roadmap

Possible future improvements:

* Replace testing strategy with a real strategy
* Add execution layer with Broker, Slippage and practical considerations
* Add historical backtesting
* Store data in a database/json
* Add multiple trading pairs
* Add performance metrics
* Build a web dashboard
* Add live trading support
* Improve risk management
* Add machine learning experiments

### An improved version with most developments is present in folder research-wing>

---

# Disclaimer

This project is for educational and research purposes.

It currently uses paper trading and does not execute real trades. Cryptocurrency markets involve significant risk, and any future live trading implementation should be tested carefully before using real capital.

---

# Summary

This project demonstrates the core components required to build an automated trading system:

* Market data collection
* Technical analysis
* Strategy generation
* Trade execution
* Risk management
* Portfolio simulation
* Monitoring and logging

The modular structure allows the bot to evolve from a simple trading experiment into a more advanced algorithmic trading framework.
