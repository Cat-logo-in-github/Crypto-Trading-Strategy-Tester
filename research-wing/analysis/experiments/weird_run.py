from analysis.engine.market import Market
from analysis.engine.account import Account
from analysis.engine.portfolio import Portfolio
from analysis.engine.backtester import Backtester

from analysis.data.loader import DataLoader

from analysis.engine.benchmark import BuyAndHoldBenchmark
from analysis.engine.indicators.engine import IndicatorEngine

from analysis.engine.execution.broker import Broker
from analysis.engine.execution.matcher import Matcher

from analysis.engine.execution.fees import PercentageFee
from analysis.engine.execution.slippage import PercentageSlippage
from analysis.engine.execution.latency import NoLatency

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)

from analysis.strategies.weird.ice_cream_strategy import (
    IceCreamProductionStrategy,
)


class EndOfBacktestLiquidationStrategy:
    """
    Thin wrapper around the real strategy.

    Normal candles:
        delegate completely to IceCreamSalesStrategy.

    Final candle:
        if a position is still open, force it closed.

    This does NOT modify the portfolio directly.

    The liquidation is returned as a normal Signal so it goes through:

        Signal
          -> Broker
          -> Matcher
          -> Portfolio
    """

    name = "IceCreamProductionStrategyWithEndLiquidation"

    def __init__(
        self,
        strategy,
        final_timestamp,
    ):
        self.strategy = strategy
        self.final_timestamp = final_timestamp

    def on(self, context):

        # -----------------------------------------------------
        # Normal strategy behavior until final candle
        # -----------------------------------------------------

        if context.timestamp != self.final_timestamp:
            return self.strategy.on(context)

        # -----------------------------------------------------
        # FINAL CANDLE
        # -----------------------------------------------------

        position = context.positions.get(
            context.symbol
        )

        if position is None:
            return self.strategy.on(context)

        quantity = position.quantity

        # Already flat.
        if quantity == 0:
            return self.strategy.on(context)

        # -----------------------------------------------------
        # Force-close long
        # -----------------------------------------------------

        if quantity > 0:

            return Signal(
                timestamp=context.timestamp,
                symbol=context.symbol,
                action=SignalAction.EXIT_LONG,
                quantity=100.0,
                sizing=PositionSizing.PERCENT_POSITION,
                confidence=1.0,
                metadata={
                    "strategy": getattr(
                        self.strategy,
                        "name",
                        "IceCreamProductionStrategy",
                    ),
                    "reason": "end_of_backtest_liquidation",
                    "original_strategy": "IceCreamProductionStrategy",
                },
            )

        # -----------------------------------------------------
        # Force-close short
        # -----------------------------------------------------

        if quantity < 0:

            return Signal(
                timestamp=context.timestamp,
                symbol=context.symbol,
                action=SignalAction.EXIT_SHORT,
                quantity=100.0,
                sizing=PositionSizing.PERCENT_POSITION,
                confidence=1.0,
                metadata={
                    "strategy": getattr(
                        self.strategy,
                        "name",
                        "IceCreamProductionStrategy",
                    ),
                    "reason": "end_of_backtest_liquidation",
                    "original_strategy": "IceCreamProductionStrategy",
                },
            )

        return None

    def reset(self):

        if hasattr(self.strategy, "reset"):
            self.strategy.reset()


def main():

    # =========================================================
    # EXPERIMENT PARAMETERS
    # =========================================================

    symbol = "BTCUSDT"

    interval = "1m"

    start_time = 1733011200000  # Dec 1 2024
    end_time = 1733616000000    # Dec 8 2024

    starting_equity = 10_000

    ice_cream_lookback = 6
    allocation = 99.0

    # =========================================================
    # MARKET DATA
    # =========================================================

    loader = DataLoader()

    candles = loader.load(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        force_download=True,
        use_cache=True,
    )

    if not candles:
        raise ValueError(
            "No market data loaded."
        )

    print(
        f"Loaded candles: {len(candles)}"
    )

    # ---------------------------------------------------------
    # Final candle
    # ---------------------------------------------------------

    final_candle = candles[-1]

    final_timestamp = final_candle.timestamp

    print(
        "Final candle timestamp:",
        final_timestamp,
    )

    # =========================================================
    # MARKET
    # =========================================================

    market = Market(
        symbol=symbol,
        candles=candles,
    )

    # =========================================================
    # ACCOUNT
    # =========================================================

    account = Account(
        starting_balance=starting_equity
    )

    portfolio = Portfolio(
        account=account
    )

    # =========================================================
    # ICE CREAM STRATEGY
    # =========================================================

    ice_cream_strategy = IceCreamProductionStrategy(
        start_time=start_time,
        end_time=end_time,
        lookback=ice_cream_lookback,
        allocation=allocation,
    )

    # =========================================================
    # END-OF-BACKTEST LIQUIDATION
    # =========================================================

    strategy = EndOfBacktestLiquidationStrategy(
        strategy=ice_cream_strategy,
        final_timestamp=final_timestamp,
    )

    # =========================================================
    # EXECUTION
    # =========================================================

    broker = Broker(
        estimated_fee_rate=0.0,
    )

    matcher = Matcher(
        fee_model=PercentageFee(
            maker_rate=0.0,
            taker_rate=0.0,
        ),
        slippage_model=PercentageSlippage(
            rate=0.0,
        ),
        latency_model=NoLatency(),
    )

    # Ice-cream strategy does not require indicators.
    indicator_engine = IndicatorEngine([])

    # =========================================================
    # BACKTESTER
    # =========================================================

    backtester = Backtester(
        market=market,
        portfolio=portfolio,
        strategy=strategy,
        broker=broker,
        matcher=matcher,
        indicator_engine=indicator_engine,
    )

    # =========================================================
    # RUN
    # =========================================================

    backtester.run()

    # =========================================================
    # RESULT
    # =========================================================

    result = backtester.results()

    print()
    print("--- ICE CREAM STRATEGY RESULT ---")
    print(result)

    # =========================================================
    # BENCHMARK
    # =========================================================

    benchmark = BuyAndHoldBenchmark(
        symbol=symbol,
        capital=starting_equity,
    )

    benchmark_result = benchmark.run(
        candles
    )

    # =========================================================
    # EVALUATION
    # =========================================================

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

    # =========================================================
    # DASHBOARD
    # =========================================================

    from analysis.visualization.dashboard import (
        ResearchDashboard,
    )

    dashboard = ResearchDashboard(
        report=report
    )

    dashboard.run()


if __name__ == "__main__":
    main()
