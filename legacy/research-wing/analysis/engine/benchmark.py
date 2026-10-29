"""
analysis.engine.benchmark

Benchmark models for strategy comparison.

Benchmarks provide passive reference
performance against which strategies can
be evaluated.

Benchmarks do not:
- execute orders
- modify portfolios
- interact with brokers
- generate signals
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from analysis.engine.models.candle import Candle
from analysis.engine.metrics.equity import EquityPoint



@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """
    Immutable benchmark output.
    """

    name: str

    equity_curve: list[EquityPoint]

    initial_equity: float

    final_equity: float


    @property
    def total_return(self) -> float:
        """
        Total benchmark return.
        """

        if self.initial_equity <= 0:
            return 0.0

        return (
            self.final_equity
            -
            self.initial_equity
        ) / self.initial_equity



class BuyAndHoldBenchmark:
    """
    Passive asset ownership benchmark.

    Assumes:
    - capital invested at first candle
    - asset held until final candle
    """


    def __init__(
        self,
        symbol: str,
        capital: float = 10_000.0,
        name: str = "BUY_AND_HOLD",
    ):
        self.symbol = symbol
        self.capital = capital
        self.name = name



    def run(
        self,
        candles: Sequence[Candle],
    ) -> BenchmarkResult:
        """
        Generate benchmark equity curve.
        """

        if not candles:
            raise ValueError(
                "Cannot benchmark empty candle data."
            )


        first_price = candles[0].close


        if first_price <= 0:
            raise ValueError(
                "Invalid initial price."
            )


        quantity = (
            self.capital
            /
            first_price
        )


        curve: list[EquityPoint] = []


        for candle in candles:

            equity = (
                quantity
                *
                candle.close
            )


            curve.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    equity=equity,
                    cash=0.0,
                )
            )


        return BenchmarkResult(
            name=self.name,

            equity_curve=curve,

            initial_equity=(
                self.capital
            ),

            final_equity=(
                curve[-1].equity
            ),
        )