"""
analysis.engine.metrics.report

Research report rendering.

This module formats immutable ResearchReport
objects for presentation.

Responsibilities
----------------
- console rendering
- future markdown rendering
- future HTML rendering
- future JSON export

This module performs no calculations.
"""

from __future__ import annotations

from analysis.engine.models.report import (
    ResearchReport,
)



def console(
    report: ResearchReport,
) -> str:
    """
    Render a human-readable console report.

    Parameters
    ----------
    report
        Completed research report.

    Returns
    -------
    str
        Multi-line formatted report.
    """

    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("RESEARCH REPORT")
    lines.append("=" * 60)

    # -------------------------------------------------
    # Performance
    # -------------------------------------------------

    lines.append("")
    lines.append("Performance")

    lines.append(
        f"Initial Equity : {report.initial_equity:.2f}"
    )

    lines.append(
        f"Final Equity   : {report.final_equity:.2f}"
    )

    lines.append(
        f"Total Return   : {report.total_return:.2%}"
    )

    lines.append(
        f"Max Drawdown   : {report.max_drawdown:.2%}"
    )

    # -------------------------------------------------
    # Risk
    # -------------------------------------------------

    lines.append("")
    lines.append("Risk")

    lines.append(
        f"Volatility     : {report.risk.volatility:.4f}"
    )

    lines.append(
        f"Sharpe Ratio   : {report.sharpe_ratio:.3f}"
    )

    # -------------------------------------------------
    # Execution Statistics
    # -------------------------------------------------

    if report.execution_statistics is not None:

        stats = report.execution_statistics

        lines.append("")
        lines.append("Execution Statistics")

        lines.append(
            f"Trades (executions)        : {stats.trade_count}"
        )

        lines.append(
            f"Buys   (executions)        : {stats.buy_count}"
        )

        lines.append(
            f"Sells  (executions)        : {stats.sell_count}"
        )

        lines.append(
            f"Fees Paid      : {stats.total_fees:.4f}"
        )

        lines.append(
            f"Avg Trade Size : {stats.average_trade_value:.2f}"
        )

    # -------------------------------------------------
    # Trade Statistics
    # -------------------------------------------------

    if report.trade_statistics is not None:

        stats = report.trade_statistics

        lines.extend(
            [
                "",
                "Completed Trade Statistics",
                "-------------------------",

                (
                    "Closed Trades : "
                    f"{stats.total_trades}"
                ),

                (
                    "Win Rate      : "
                    f"{stats.win_rate:.2%}"
                ),

                (
                    "Gross Profit  : "
                    f"{stats.gross_profit:.2f}"
                ),

                (
                    "Gross Loss    : "
                    f"{stats.gross_loss:.2f}"
                ),

                (
                    "Profit Factor : "
                    f"{stats.profit_factor:.2f}"
                ),

                (
                    "Average Win   : "
                    f"{stats.average_win:.2f}"
                ),

                (
                    "Average Loss  : "
                    f"{stats.average_loss:.2f}"
                ),

                (
                    "Expectancy    : "
                    f"{stats.expectancy:.2f}"
                ),

                (
                    "Avg Hold Time : "
                    f"{stats.average_holding_time_seconds / 60:.1f} min"
                ),
            ]
        )

    # -------------------------------------------------
    # Benchmark
    # -------------------------------------------------

    if report.benchmark is not None:

        lines.append("")
        lines.append("Benchmark")

        lines.append(
            f"Benchmark Return : {report.benchmark.total_return:.2%}"
        )

        lines.append(
            f"Excess Return    : {report.excess_return:.2%}"
        )

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)