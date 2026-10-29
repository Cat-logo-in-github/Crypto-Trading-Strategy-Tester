# Indicators

## Purpose

The Indicators subsystem computes reusable market features from historical candles.

Indicators are separate from strategy logic and execution. They transform market data into numeric signals that strategies can use to make decisions.

## Design Principles

- Indicators should be stateless from the perspective of the strategy: they only consume candles and expose values.
- Indicators should not create trades, access portfolio state, or manage orders.
- Indicator state should be resettable for repeated experiments.
- Indicator names must be unique because their values are exposed through `StrategyContext.indicators`.

## Architecture

### Indicator Engine

The `IndicatorEngine` manages a collection of indicators and updates them on each market step.

Responsibilities:

- register indicators
- update indicators with each new `Candle`
- expose current indicator values
- reset all indicator state

### Indicators

Each indicator implements the `Indicator` base class and provides:

- `name` — unique identifier
- `update(candle)` — consume the latest candle
- `value` — current computed output
- `ready` — whether the indicator has enough history to return a valid value
- `reset()` — clear internal state

## Current Implementations

### SMA

Simple Moving Average over a fixed number of candles.

- Uses a fixed-length rolling window
- Returns `None` until warm-up is complete
- Computes the arithmetic mean of close prices

### EMA

Exponential Moving Average using Wilder-like smoothing.

- Applies greater weight to recent price action
- Seeds initial state using SMA over the same period
- Returns `None` during warm-up

### RSI

Relative Strength Index for momentum measurement.

- Uses Wilder smoothing for average gains and losses
- Returns `None` until enough price changes exist
- Useful for overbought/oversold signals

### ATR

Average True Range for volatility measurement.

- Computes true range using high, low, and previous close
- Applies Wilder smoothing across the period
- Useful for position sizing, stop-loss calculations, and regime detection

## Usage

1. Construct indicators:

```python
from analysis.engine.indicators.engine import IndicatorEngine
from analysis.engine.indicators.sma import SMA
from analysis.engine.indicators.rsi import RSI

engine = IndicatorEngine([
    SMA(period=20),
    RSI(period=14),
])
```

2. Update on each market step:

```python
engine.update(candle)
```

3. Read values in strategy context:

```python
values = engine.values()
```

4. Reset before a new run:

```python
engine.reset()
```
