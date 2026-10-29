"""
analysis.engine.backtester

Research-grade simulation orchestrator.

The Backtester coordinates:

Market
    ↓
Strategy
    ↓
Signal
    ↓
Broker
    ↓
Order
    ↓
Matcher
    ↓
Trade
    ↓
Portfolio


The Backtester does NOT:
- create trades
- execute orders
- calculate fees
- calculate slippage
- manage positions

It only controls simulation flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.engine.market import Market
from analysis.engine.portfolio import Portfolio
from analysis.engine.trade import Trade
from analysis.engine.results import BacktestResult

from analysis.engine.models.context import StrategyContext
from analysis.engine.indicators.engine import IndicatorEngine

from analysis.engine.execution.broker import Broker
from analysis.engine.execution.matcher import Matcher

from analysis.engine.metrics.equity import EquityPoint

from analysis.engine.execution.context import (
    PortfolioBrokerContext,
)



@dataclass(slots=True)
class Backtester:
    """
    Main simulation coordinator.

    Owns:
    - simulation loop
    - component coordination

    Does not own:
    - trading logic
    - execution logic
    - portfolio logic
    """

    market: Market

    portfolio: Portfolio

    strategy: Any

    broker: Broker

    matcher: Matcher

    indicator_engine: IndicatorEngine

    trades: list[Trade] = field(
        default_factory=list
    )

    equity_curve: list[EquityPoint] = field(
        default_factory=list
    )


    # ---------------------------------------------------------
    # Main simulation loop
    # ---------------------------------------------------------

    def run(self) -> None:
        """
        Execute complete backtest.
        """


        while True:

            candle = (
                self.market.current
            )

            # Update indicators using only
            # information available at this timestep
            self.indicator_engine.update(
                candle
            )

            context = (
                self._build_strategy_context(
                    candle
                )
            )

            signal = (
                self.strategy.on(
                    context
                )
            )


            if signal is not None:

                self._execute_signal(
                    signal,
                    candle,
                )

            self.equity_curve.append(
                    EquityPoint(
                        timestamp=candle.timestamp,
                        equity=self._portfolio_value(candle),
                        cash=self.portfolio.account.cash,
                    )
                )


            if self.market.is_last:
                break


            self.market.step()



    # ---------------------------------------------------------
    # Strategy Context
    # ---------------------------------------------------------

    def _build_strategy_context(
        self,
        candle,
    ) -> StrategyContext:
        """
        Create immutable strategy observation.

        Strategy receives information only.
        """


        return StrategyContext(
            symbol=self.market.symbol,
            timestamp=candle.timestamp,

            current=candle,

            history=(
                self.market.history()
            ),

            portfolio_value=(
                self._portfolio_value(
                    candle
                )
            ),

            cash=(
                self.portfolio.account.cash
            ),

            positions=(
                self.portfolio.positions.copy()
            ),

            indicators=(
                self.indicator_engine.values()
            ),

            metadata={},
        )



    # ---------------------------------------------------------
    # Execution Pipeline
    # ---------------------------------------------------------

    def _execute_signal(
        self,
        signal,
        candle,
    ) -> None:
        """
        Execute:

            Signal
              ↓
            Order
              ↓
            Trade
              ↓
            Portfolio
        """


        broker_context = (
            PortfolioBrokerContext(
                portfolio=self.portfolio,

                prices={
                    signal.symbol:
                    candle.close
                },
            )
        )


        order = (
            self.broker.create_order(
                signal=signal,
                context=broker_context,
            )
        )


        if order is None:
            return



        trade = (
            self.matcher.match(
                order=order,

                market_price=(
                    candle.close
                ),

                timestamp=(
                    candle.timestamp
                ),
            )
        )


        if trade is None:
            return



        self.trades.append(
            trade
        )


        self.portfolio.apply_trade(
            trade
        )



    # ---------------------------------------------------------
    # Valuation
    # ---------------------------------------------------------

    def _portfolio_value(
        self,
        candle,
    ) -> float:
        """
        Mark portfolio to market.
        """


        prices = {
            symbol:
            candle.close

            for symbol
            in self.portfolio.positions.keys()
        }


        return self.portfolio.equity(
            prices
        )



    # ---------------------------------------------------------
    # Results
    # ---------------------------------------------------------

    def results(
        self,
    ) -> BacktestResult:
        """
        Return immutable simulation result.
        """

        final_positions = {
            symbol: position.snapshot()
            for symbol, position
            in self.portfolio.positions.items()
        }


        final_equity = (
            self.equity_curve[-1].equity
            if self.equity_curve
            else 0.0
        )


        return BacktestResult(
            equity_curve=tuple(
                self.equity_curve
            ),

            trades=tuple(
                self.trades
            ),

            final_cash=(
                self.portfolio.account.cash
            ),

            final_equity=final_equity,

            final_positions=final_positions,

            start_time=(
                self.equity_curve[0].timestamp
                if self.equity_curve
                else None
            ),

            end_time=(
                self.equity_curve[-1].timestamp
                if self.equity_curve
                else None
            ),

            metadata={},
        )