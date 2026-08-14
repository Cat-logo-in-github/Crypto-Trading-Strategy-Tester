from analysis.engine.market import Market
from analysis.engine.account import Account
from analysis.engine.portfolio import Portfolio
from analysis.engine.backtester import Backtester

from analysis.strategies.classic.sma_cross.sma_cross_strategy import (
    SMACrossoverStrategy,
)

from analysis.strategies.classic.buy_and_hold.buy_and_hold_strategy import (
    BuyAndHoldStrategy,
)
from analysis.data.loader import DataLoader
from analysis.engine.benchmark import BuyAndHoldBenchmark
from analysis.visualization.equity_plot import plot_equity_curve
from analysis.visualization.price_plot import (
    plot_price_with_trades,
)
from analysis.visualization.drawdown_plot import (
    plot_drawdown,
)

from analysis.engine.execution.broker import Broker
from analysis.engine.execution.matcher import Matcher

from analysis.engine.execution.fees import PercentageFee
from analysis.engine.execution.slippage import PercentageSlippage
from analysis.engine.execution.latency import NoLatency

from analysis.engine.indicators.engine import IndicatorEngine

from analysis.engine.indicators.sma import SMA
from analysis.engine.indicators.ema import EMA
from analysis.engine.indicators.rsi import RSI
from analysis.engine.indicators.atr import ATR


def main():
    """
    Real-market backtest entry point.
    """

    # ---------------------------------------------------------
    # 1. LOAD REAL MARKET DATA
    # ---------------------------------------------------------
    loader = DataLoader()

    candles = loader.load(
        symbol="BTCUSDT",
        interval="1m",
        start_time=None,
        end_time=None,
        force_download=True,   # first run ensures API fetch
        use_cache=True         # later runs will be fast
    )

    print(f"Loaded candles: {len(candles)}")

    if not candles:
        raise ValueError("No market data loaded. Check downloader/API.")

    # ---------------------------------------------------------
    # 2. BUILD SIMULATION ENGINE
    # ---------------------------------------------------------
    market = Market(
        symbol="BTCUSDT",
        candles=candles,
    )

    account = Account(starting_balance=10_000)
    portfolio = Portfolio(account=account)

    strategy = SMACrossoverStrategy(
        fast_period=20,
        slow_period=50,
        allocation=100.0,
    )

    broker = Broker()

    matcher = Matcher(
        fee_model=PercentageFee(
            maker_rate=0.0002,
            taker_rate=0.0005,
        ),
        slippage_model=PercentageSlippage(
            rate=0.0005,
        ),
        latency_model=NoLatency(),
    )

    indicator_engine = IndicatorEngine(
        [
            SMA(period=20),
            SMA(period=50),
        ]
    )

    backtester = Backtester(
        market=market,
        portfolio=portfolio,
        strategy=strategy,
        broker=broker,
        matcher=matcher,
        indicator_engine=indicator_engine,
    )
    # ---------------------------------------------------------
    # 3. RUN SIMULATION
    # ---------------------------------------------------------
    backtester.run()

    # ---------------------------------------------------------
    # 4. RESULTS
    # ---------------------------------------------------------

    result = backtester.results()

    print("\n--- BACKTEST RESULT ---")
    print(result)

    ...

    # ---------------------------------------------------------
    # 5. BENCHMARK
    # ---------------------------------------------------------

    benchmark = BuyAndHoldBenchmark(
        symbol="BTCUSDT",
        capital=10_000,
    )

    benchmark_result = benchmark.run(
        candles
    )

    print("\n--- BENCHMARK ---")

    print(
        benchmark_result.name
    )

    print(
        "Return:",
        f"{benchmark_result.total_return:.2%}"
    )

    # ---------------------------------------------------------
    # 6. EVALUATION
    # ---------------------------------------------------------

    from analysis.engine.evaluator import Evaluator
    from analysis.engine.metrics.report import console

    evaluator = Evaluator()

    report = evaluator.evaluate(
        result,
        benchmark_result,
        candles=tuple(candles),
    )

    print()

    print(
        console(report)
    )

    # ---------------------------------------------------------
    # 7. VISUALIZATION
    # ---------------------------------------------------------

    from analysis.visualization.dashboard import (
        ResearchDashboard,
    )


    dashboard = ResearchDashboard(
        report=report
    )


    dashboard.run()

if __name__ == "__main__":
    main()