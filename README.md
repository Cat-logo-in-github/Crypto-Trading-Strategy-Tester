# 🧪 Crypto Trading Strategy Tester

```text
   ______                __            __
  / ____/________ ______/ /_____ _____/ /_
 / /   / ___/ __ `/ ___/ __/ __ `/ __  / /
/ /___/ /  / /_/ / /__/ /_/ /_/ / /_/ / /
\____/_/   \__,_/\___/\__/\__,_/\__,_/_/

          QUANTITATIVE RESEARCH & TRADING
                    FRAMEWORK
```

A modular Python project for **cryptocurrency trading research, strategy development, backtesting, market simulation, and paper trading**.

The repository contains two related systems:

```text
Crypto Trading Strategy Tester
│
├── 🧠 research-wing/
│   └── Quantitative research & backtesting framework
│
└── 🤖 bitcoin-trading-bot/
    └── Paper-trading Bitcoin bot
```

The two projects share the same overall goal:

> Build, test, evaluate, and eventually deploy systematic cryptocurrency trading strategies without mixing research logic with execution logic.

---

# 📖 Overview

This repository evolved from a relatively simple Bitcoin paper-trading bot into a more comprehensive quantitative research framework.

The original **Bitcoin Trading Bot** focuses on:

* collecting market data
* calculating technical indicators
* generating trading signals
* position sizing
* paper execution
* portfolio tracking
* monitoring

The newer **Research Wing** provides a more rigorous architecture for:

* historical market-data research
* deterministic market simulation
* strategy development
* backtesting
* execution modelling
* portfolio accounting
* performance evaluation
* visualization
* machine-learning strategy experimentation
* future multi-asset and live-trading support

The Research Wing is intended to become the primary research and simulation environment, while the Bitcoin Trading Bot serves as a simpler example of the complete trading pipeline.

---

# 🏗️ Repository Architecture

```text
                         CRYPTO TRADING STRATEGY TESTER
                                      │
                     ┌────────────────┴────────────────┐
                     │                                 │
                     ▼                                 ▼
             BITCOIN TRADING BOT                 RESEARCH WING
                     │                                 │
             Real-time market data              Historical data
                     │                                 │
             Technical indicators                Data cleaning
                     │                                 │
                Strategy                         Data loading
                     │                                 │
             Paper execution                    Market simulation
                     │                                 │
              Virtual wallet                    Indicators
                     │                                 │
                Dashboard                        Strategy
                     │                                 │
                     │                              Signal
                     │                                 │
                     │                              Broker
                     │                                 │
                     │                               Order
                     │                                 │
                     │                              Matcher
                     │                                 │
                     │                               Trade
                     │                                 │
                     │                             Portfolio
                     │                                 │
                     │                            Backtester
                     │                                 │
                     │                          Backtest Result
                     │                                 │
                     │                            Evaluation
                     │                                 │
                     └───────────────┬─────────────────┘
                                     │
                                     ▼
                           Research & Development
                                     │
                         ┌───────────┼───────────┐
                         ▼           ▼           ▼
                     Strategies      ML       Future Live
```

---

# 🧠 Research Wing

The Research Wing is the main quantitative research framework.

Its purpose is to provide a controlled environment where trading strategies can be tested against historical market data under deterministic and configurable execution conditions.

## Research Pipeline

```text
                    ┌─────────────────┐
                    │   Raw Market    │
                    │      Data       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Downloader   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Cleaner     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Data Loader   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Candle      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │      Market     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Indicator Engine│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Strategy    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │      Signal     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │      Broker     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │      Order      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Matcher     │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              Fee / Slippage       Latency
                    │                 │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │      Trade      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Portfolio    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Backtester   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  BacktestResult │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Evaluator    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Visualization   │
                    └─────────────────┘
```

---

# 🔬 What Research Wing Is For

Research Wing can be used to investigate questions such as:

* Does a moving-average strategy actually have an edge?
* How does a strategy behave during different market regimes?
* What happens when transaction fees are introduced?
* How sensitive is a strategy to slippage?
* How does execution latency affect performance?
* How much drawdown does a strategy experience?
* How frequently does a strategy trade?
* Does a strategy outperform buy-and-hold?
* How does position sizing affect risk?
* Which indicators improve a strategy?
* How do different strategies compare under identical market conditions?

It is designed so that these experiments can be performed without changing the core simulation engine.

---

# 🧩 Research Wing Design Principles

## Single Responsibility

Each component has one primary responsibility.

```text
Candle       → stores market data
Market       → controls simulation time
Indicator    → calculates features
Strategy     → produces Signals
Broker       → creates Orders
Matcher      → simulates execution
Trade        → records execution
Portfolio    → tracks ownership and money
Backtester   → coordinates simulation
Evaluator    → analyzes results
Visualization→ displays results
```

---

## No Look-Ahead Bias

Historical data is treated as immutable.

At a given point in the simulation, a strategy can only access information that would have been available at that point in time.

```text
Past candles ───────────────► Current candle
      │                              │
      │                              ▼
      └────────────────────────► Strategy

                     ❌ Future candles
```

The `Market` is the single source of simulation time.

---

## Strategy Isolation

Strategies express **intent**, rather than execution mechanics.

```text
Strategy
   │
   ▼
Signal
   │
   ▼
Broker
   │
   ▼
Order
```

A strategy does not directly:

* modify the portfolio
* execute orders
* calculate fees
* apply slippage
* control latency

This allows the same strategy to be tested using different execution models.

---

# 📊 Signals, Orders and Trades

The framework deliberately separates these concepts.

```text
┌──────────────┐
│    Signal    │
│              │
│ Strategy     │
│ Intent       │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Broker    │
│              │
│ Order        │
│ Construction │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     Order    │
│              │
│ Executable   │
│ Instruction  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Matcher   │
│              │
│ Execution    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     Trade    │
│              │
│ Actual       │
│ Execution    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Portfolio  │
│              │
│ State Update │
└──────────────┘
```

This distinction makes the simulation more realistic and easier to extend.

---

# 💰 Execution Simulation

The Matcher can model execution costs independently.

```text
                     Order
                       │
                       ▼
                ┌────────────┐
                │   Matcher  │
                └─────┬──────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Fees        Slippage    Latency
          │           │           │
          └───────────┼───────────┘
                      ▼
                    Trade
```

Current execution components include:

* zero-fee execution
* percentage-based fees
* no slippage
* percentage-based slippage
* zero latency
* fixed latency

Because these are isolated models, new execution assumptions can be introduced without rewriting strategies or portfolio accounting.

---

# 📈 Evaluation

A completed simulation produces an immutable `BacktestResult`.

```text
Backtest
   │
   ▼
BacktestResult
   │
   ▼
Evaluator
   │
   ├── Performance
   ├── Risk
   ├── Returns
   ├── Drawdown
   ├── Trade Statistics
   └── Closed Trade Analytics
            │
            ▼
       Research Report
```

The evaluation layer is intentionally separate from the simulation engine.

This means analysis does not modify the simulation that produced it.

---

# 📊 Visualization

The visualization layer consumes completed results and evaluation output.

It can be used to display:

* equity curves
* drawdowns
* market prices
* executed trades
* performance statistics
* trading activity
* research dashboards

```text
BacktestResult ──┐
                 ├──► Visualization ──► Dashboard
Research Report ─┘
```

Visualization does not need to know how the underlying simulation works.

---

# 🤖 Bitcoin Trading Bot

The `bitcoin-trading-bot/` directory contains the earlier, simpler trading system.

It is a Python-based Bitcoin paper-trading application designed to work with real-time market data.

```text
Exchange
   │
   ▼
Market Data
   │
   ▼
Indicators
   │
   ▼
Strategy
   │
   ▼
Trader
   │
   ▼
Paper Wallet
   │
   ▼
Dashboard
```

The bot currently operates in **paper trading mode**.

No real orders are placed on an exchange.

---

# 🪙 Bitcoin Bot Features

### Market Data

* CCXT exchange integration
* Binance configuration
* BTC/USDT
* 1-hour candles
* OHLCV data collection

### Indicators

The bot supports technical indicators including:

* EMA
* RSI
* MACD
* ATR

### Strategy

The current strategy is primarily a testing strategy used to validate the trading pipeline.

The architecture allows future strategies such as:

* moving-average systems
* momentum strategies
* mean-reversion systems
* machine-learning strategies

### Paper Wallet

The virtual wallet tracks:

* cash
* BTC holdings
* entry price
* portfolio value
* trade history
* unrealized P/L

Default starting capital:

```text
$10,000
```

### Risk Management

The bot includes configuration for:

```text
Risk per trade     → 2%
Maximum position   → 95%
ATR multiplier     → 2
```

It also supports concepts such as:

* stop loss
* take profit
* trailing stops
* risk-based position sizing
* ATR-based sizing

---

# 📁 Project Structure

```text
Crypto-Trading-Strategy-Tester/
│
├── README.md
├── requirements.txt
│
├── bitcoin-trading-bot/
│   │
│   ├── main.py
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── bot/
│   │   ├── config.py
│   │   ├── dashboard.py
│   │   ├── indicators.py
│   │   ├── logger.py
│   │   ├── market.py
│   │   ├── paper_wallet.py
│   │   ├── strategy.py
│   │   ├── trader.py
│   │   └── utils.py
│   │
│   ├── data/
│   │   └── ...
│   │
│   └── logs/
│
└── research-wing/
    │
    ├── README.md
    ├── architecture.md
    ├── decisions.md
    ├── roadmap.md
    │
    └── analysis/
        │
        ├── config/
        ├── data/
        ├── engine/
        ├── experiments/
        ├── notebooks/
        ├── strategies/
        ├── tests/
        ├── utils/
        └── visualization/
```

Generated files such as Python bytecode, secrets, logs, raw datasets, and other local artifacts should not be committed to the repository.

---

# 🚀 Getting Started

## Requirements

Recommended:

```text
Python 3.10+
Git
pip
virtualenv / venv
```

---

## Clone the Repository

```bash
git clone https://github.com/cat-in-github-logo/CryptocurrencyTradeResearcher.git
cd CryptocurrencyTradeResearcher
```

---

# 🐍 Create a Virtual Environment

### Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project dependencies:

```bash
pip install -r requirements.txt
```

If working specifically with the Bitcoin Trading Bot:

```bash
pip install -r bitcoin-trading-bot/requirements.txt
```

---

# 🤖 Running the Bitcoin Trading Bot

Move into the bot directory:

```bash
cd bitcoin-trading-bot
```

Create your local environment configuration from the example:

```text
.env.example → .env
```

Do **not** commit `.env`.

The bot can then be started with:

```bash
python main.py
```

The basic pipeline is:

```text
1. Connect to exchange
        ↓
2. Retrieve market candles
        ↓
3. Calculate indicators
        ↓
4. Generate strategy signal
        ↓
5. Calculate position size
        ↓
6. Execute simulated trade
        ↓
7. Update paper wallet
        ↓
8. Display dashboard
        ↓
9. Repeat
```

The bot is intended for experimentation and paper trading.

---

# 🔬 Running Research Experiments

The Research Wing is intended for historical experimentation and backtesting.

```text
Historical Dataset
        │
        ▼
     DataLoader
        │
        ▼
      Market
        │
        ▼
   Strategy + Indicators
        │
        ▼
      Signals
        │
        ▼
      Broker
        │
        ▼
      Matcher
        │
        ▼
      Trades
        │
        ▼
     Portfolio
        │
        ▼
    Backtester
        │
        ▼
  BacktestResult
        │
        ▼
    Evaluator
        │
        ▼
 Research Report
```

Strategies currently include examples such as:

```text
strategies/
│
├── classic/
│   ├── buy_and_hold/
│   └── sma_cross/
│
├── random/
│
└── ml/
```

This makes the Research Wing suitable for comparing different approaches under the same simulation environment.

---

# 🧪 Example Research Workflow

A typical experiment might look like:

```text
Question
   │
   ▼
"Does SMA crossover outperform Buy & Hold?"
   │
   ▼
Select historical dataset
   │
   ▼
Run Strategy A
   │
   ├── Same candles
   ├── Same fees
   ├── Same slippage
   └── Same starting capital
   │
   ▼
Run Strategy B
   │
   ├── Same candles
   ├── Same fees
   ├── Same slippage
   └── Same starting capital
   │
   ▼
Compare Results
   │
   ├── Return
   ├── Drawdown
   ├── Risk
   ├── Number of trades
   ├── Win rate
   └── Other metrics
   │
   ▼
Research Report
```

This is the primary purpose of the Research Wing.

---

# 🧠 What Can This Repository Eventually Become?

The architecture is intentionally designed to support growth beyond the current implementation.

## Strategy Research

```text
Classic Strategies
       │
       ├── Trend Following
       ├── Momentum
       ├── Mean Reversion
       └── Breakout
```

## Machine Learning

```text
Market Data
     │
     ▼
Feature Engineering
     │
     ▼
ML Model
     │
     ▼
Signal
     │
     ▼
Backtesting
```

Future research can include:

* supervised learning
* reinforcement learning
* feature engineering
* model comparison
* walk-forward testing
* parameter optimization
* regime detection

---

# 🌎 Multi-Asset Research

The architecture is intended to eventually support:

```text
BTC
ETH
SOL
Stocks
Futures
Other Assets
     │
     ▼
Multi-Asset Portfolio
     │
     ▼
Portfolio-Level Risk
```

This would allow research into:

* diversification
* portfolio allocation
* correlation
* cross-asset strategies
* portfolio-level risk management

---

# ⚡ Future Execution

The current Research Wing primarily focuses on historical simulation.

A possible future architecture is:

```text
                    Strategy
                       │
                     Signal
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
      Backtest Broker       Live Broker
            │                     │
            ▼                     ▼
       Simulated              Exchange
       Execution              Execution
            │                     │
            └──────────┬──────────┘
                       ▼
                    Trade
                       │
                       ▼
                   Portfolio
```

The separation between strategy intent and execution is designed to make this evolution possible without rewriting strategy logic.

---

# 🏛️ Architectural Decisions

The repository documents architectural decisions in:

```text
research-wing/decisions.md
```

Some of the major decisions are:

```text
Historical Data
      │
      └── Immutable

Strategy
      │
      └── Signal only

Signal
      │
      └── Intent, not execution

Broker
      │
      └── Signal → Order

Matcher
      │
      └── Order → Trade

Portfolio
      │
      └── Trade → State

Backtester
      │
      └── Orchestration only

Evaluator
      │
      └── Read-only analysis
```

These boundaries are intended to keep the system testable, extensible, and resistant to accidental coupling.

---

# 🔐 Data & Security

Never commit credentials or API keys.

Files such as:

```text
.env
.env.*
```

should remain local.

Use:

```text
.env.example
```

to document required environment variables without exposing secrets.

Generated artifacts such as:

```text
__pycache__/
*.pyc
logs/
data/raw/
```

should also generally remain outside version control.

---

# ⚠️ Important Disclaimer

This repository is intended for **education, software development, quantitative research, and experimentation**.

The Bitcoin Trading Bot currently uses paper trading and is not intended to execute real trades.

Cryptocurrency markets are highly volatile and involve substantial financial risk.

Backtested performance does not guarantee future performance.

A strategy that performs well historically may fail in live markets due to:

* changing market regimes
* liquidity constraints
* slippage
* fees
* latency
* data quality
* execution differences
* overfitting
* model assumptions
* unexpected market behavior

Any future live-trading implementation should be tested extensively before being connected to real capital.

---

# 🗺️ Roadmap

```text
                         CURRENT
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
       Research Wing                Bitcoin Bot
              │                           │
              ▼                           ▼
      Backtesting Engine            Paper Trading
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Research   │
                     │   Expansion  │
                     └──────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
       More Data           ML            More Strategies
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
                    Multi-Asset Research
                            │
                            ▼
                     Advanced Execution
                            │
                            ▼
                       Live Trading
```

Potential future work includes:

* advanced strategy families
* additional data providers
* additional execution models
* historical backtesting improvements
* walk-forward analysis
* parameter optimization
* richer performance metrics
* machine-learning experiments
* reinforcement-learning experiments
* multi-asset portfolios
* database-backed datasets
* improved dashboards
* live execution infrastructure

---

# 🎯 Project Philosophy

The long-term goal is not simply to create a bot that can place trades.

The goal is to create a **research environment where trading ideas can be tested scientifically**.

```text
       IDEA
        │
        ▼
     STRATEGY
        │
        ▼
    EXPERIMENT
        │
        ▼
    BACKTEST
        │
        ▼
    EVALUATION
        │
        ▼
     ANALYSIS
        │
        ▼
      ITERATE
        │
        └──────────────► IDEA
```

The separation of data, strategy, execution, portfolio accounting, evaluation, and visualization is intended to make that process reproducible and extensible.

---

# 📚 Documentation

Additional documentation can be found inside the Research Wing:

```text
research-wing/
│
├── README.md          → Research Wing overview
├── architecture.md    → System architecture
├── decisions.md       → Architectural decisions
├── roadmap.md         → Planned development
│
└── analysis/
    ├── engine/
    │   ├── engine.md
    │   ├── EVALUATION.md
    │   ├── execution/
    │   ├── indicators/
    │   ├── metrics/
    │   └── models/
    │
    └── data/
        └── data.md
```

---

# 👨‍💻 Development Status

### Research Wing

```text
[████████████████████░░░░] Core Framework
```

Implemented:

* Candle model
* Data downloader
* Provider abstraction
* Data cleaner
* Data loader
* Market simulation
* Indicator engine
* Strategy signal pipeline
* Broker
* Order creation
* Matcher
* Fee models
* Slippage models
* Latency models
* Account
* Position
* Portfolio
* Backtester
* Immutable backtest results
* Evaluator
* Research reports
* Visualization
* Dashboard components

In progress:

* advanced strategy families
* additional market-data providers
* additional execution models
* richer evaluation and reporting
* machine-learning experimentation

### Bitcoin Trading Bot

```text
[████████████████░░░░░░░░] Paper Trading System
```

The bot provides a simpler end-to-end implementation of:

```text
Market Data
    ↓
Indicators
    ↓
Strategy
    ↓
Risk Management
    ↓
Paper Execution
    ↓
Portfolio
    ↓
Dashboard
```

---

# ⭐ Summary

This repository contains two stages of the same broader idea:

```text
                 SIMPLE TRADING SYSTEM
                         │
                         ▼
               Bitcoin Trading Bot
                         │
                         │
                  lessons learned
                         │
                         ▼
               RESEARCH FRAMEWORK
                         │
                         ▼
                  Research Wing
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Backtest          ML         Simulation
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                Quantitative Research
                         │
                         ▼
                  Future Live Trading
```

**Bitcoin Trading Bot** provides a practical paper-trading implementation.

**Research Wing** provides the more structured architecture for rigorous historical research and simulation.

Together, they form an evolving environment for experimenting with algorithmic trading ideas while keeping **research, execution, accounting, and evaluation clearly separated**.
