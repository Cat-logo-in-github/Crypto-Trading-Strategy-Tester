"""
analysis.engine.models.report

Research report model.

A ResearchReport is the canonical output of the
evaluation subsystem.

It aggregates every evaluation model into a
single immutable object suitable for:

- experiment tracking
- reporting
- visualization
- persistence
- benchmark comparison

The report contains no business logic.

It is produced exclusively by the Evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.engine.models.performance import (
    PerformanceSummary,
)

from analysis.engine.models.risk import (
    RiskSummary,
)

from analysis.engine.benchmark import (
    BenchmarkResult,
)

from analysis.engine.models.statistics import (
    ExecutionStatistics,
)

from analysis.engine.models.closed_trade import (
    ClosedTrade,
)

from analysis.engine.metrics.equity import (
    EquityPoint,
)

from analysis.engine.models.trade_statistics import (
    TradeStatistics,
)

from analysis.engine.models.candle import (
    Candle
) #Cuz it gave an error otherwise

@dataclass(frozen=True, slots=True)
class ResearchReport:
    """
    Immutable evaluation report.

    This object represents the final output of a
    completed research simulation.

    Future versions may include:

    - trade statistics
    - benchmark comparison
    - rolling metrics
    - factor exposure
    - attribution analysis

    without changing the surrounding architecture.
    """

    performance: PerformanceSummary

    risk: RiskSummary

    benchmark: BenchmarkResult | None = None

    execution_statistics: ExecutionStatistics | None = None

    closed_trades: tuple[ClosedTrade, ...] = ()

    equity_curve: tuple[EquityPoint, ...] = ()

    candles: tuple[Candle, ...] = ()

    trade_statistics: TradeStatistics | None = None

    @property
    def initial_equity(self) -> float:
        """
        Portfolio equity before simulation.
        """

        return self.performance.initial_equity


    @property
    def final_equity(self) -> float:
        """
        Portfolio equity after simulation.
        """

        return self.performance.final_equity


    @property
    def total_return(self) -> float:
        """
        Total portfolio return.
        """

        return self.performance.total_return


    @property
    def max_drawdown(self) -> float:
        """
        Maximum portfolio drawdown.
        """

        return self.performance.max_drawdown


    @property
    def sharpe_ratio(self) -> float:
        """
        Portfolio Sharpe ratio.
        """

        return self.risk.sharpe_ratio


    @property
    def benchmark_return(self) -> float | None:
        """
        Benchmark total return.

        Returns None when no benchmark
        is available.
        """

        if self.benchmark is None:
            return None

        return self.benchmark.total_return


    @property
    def excess_return(self) -> float | None:
        """
        Portfolio return relative to benchmark.

        Returns None when no benchmark
        has been evaluated.
        """

        if self.benchmark is None:
            return None

        return (
            self.total_return
            -
            self.benchmark.total_return
        )


    def __repr__(self) -> str:

        benchmark = (
            "None"
            if self.benchmark is None
            else f"{self.benchmark.total_return:.2%}"
        )

        trades = len(
            self.closed_trades
        )

        return (
            "ResearchReport("
            f"return={self.total_return:.2%}, "
            f"drawdown={self.max_drawdown:.2%}, "
            f"sharpe={self.sharpe_ratio:.2f}, "
            f"trades={trades}, "
            f"benchmark={benchmark}"
            ")"
        )