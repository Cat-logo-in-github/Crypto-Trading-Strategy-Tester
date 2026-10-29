"""
analysis.engine.evaluator

Research evaluation engine.

The Evaluator transforms immutable simulation
results into immutable research reports.

Responsibilities
----------------
- calculate performance metrics
- calculate risk metrics
- attach benchmark results
- produce a canonical ResearchReport

The Evaluator performs no simulation and
never mutates engine state.
"""

from __future__ import annotations

from analysis.engine.results import BacktestResult
from analysis.engine.models.candle import Candle

from analysis.engine.benchmark import (
    BenchmarkResult,
)

from analysis.engine.models.report import (
    ResearchReport,
)

from analysis.engine.metrics.performance import (
    calculate as calculate_performance,
)

from analysis.engine.metrics.risk import (
    calculate_risk,
)

from analysis.engine.metrics.statistics import (
    calculate as calculate_statistics,
)

from analysis.engine.analytics.trade_reconstruction import (
    reconstruct_closed_trades,
)

from analysis.engine.metrics.trades import (
    calculate as calculate_trade_statistics,
)


class Evaluator:
    """
    Research evaluation coordinator.

    The Evaluator is the single public entry
    point to the evaluation subsystem.

    Future versions may incorporate:

    - trade statistics
    - rolling metrics
    - benchmark comparison
    - factor analysis
    - attribution analysis

    without changing this interface.
    """


    def evaluate(
        self,
        result: BacktestResult,
        benchmark: BenchmarkResult | None = None,
        candles: tuple[Candle, ...] = (),
    ) -> ResearchReport:
        """
        Produce a complete research report.

        Parameters
        ----------
        result
            Completed simulation output.

        benchmark
            Optional benchmark evaluation.

        Returns
        -------
        ResearchReport
            Immutable research summary.
        """

        performance = (
            calculate_performance(
                result
            )
        )

        risk = (
            calculate_risk(
                result.equity_curve
            )
        )
        
        statistics = (
            calculate_statistics(
                result.trades
            )
        )

        closed_trades = (
            reconstruct_closed_trades(
                result.trades
            )
        )

        trade_statistics = (
            calculate_trade_statistics(
                closed_trades
            )
        )

        return ResearchReport(
            performance=performance,
            risk=risk,
            benchmark=benchmark,

            execution_statistics=statistics,
            closed_trades=tuple(
                closed_trades
            ),
            trade_statistics=trade_statistics,

            equity_curve=tuple(
                result.equity_curve
            ),
            candles=candles,
        )