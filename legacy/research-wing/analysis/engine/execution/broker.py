"""
analysis.engine.execution.broker

Broker converts strategy Signals into executable Orders.

Architecture
------------

Strategy
    |
    | Signal
    v
Broker
    |
    | Order
    v
Execution engine
    |
    | Trade
    v
Portfolio

The Broker is responsible for translating strategy intent
into executable order instructions.

The Broker does NOT:

- execute orders
- determine fill prices
- calculate realized PnL
- mutate Portfolio
- mutate Account
- create Trades

The Broker DOES:

- translate SignalAction -> OrderSide
- resolve strategy sizing -> absolute units
- resolve position-aware exits
- prevent obviously impossible buy orders
- preserve strategy intent in order metadata
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)

from analysis.engine.order import (
    Order,
    OrderSide,
    OrderType,
)


# ============================================================
# Broker context
# ============================================================


class BrokerContext(Protocol):
    """
    Read-only information required by the Broker.

    Broker intentionally depends on a small interface rather
    than directly depending on Portfolio or Account.

    This makes the Broker reusable in:

    - backtests
    - paper trading
    - live execution
    - unit tests
    """

    @property
    def equity(self) -> float:
        """
        Current marked-to-market account equity.
        """
        ...

    @property
    def available_cash(self) -> float:
        """
        Cash currently available for a new transaction.
        """
        ...

    @property
    def price_lookup(self) -> dict[str, float]:
        """
        Current market prices.
        """
        ...

    def position_quantity(
        self,
        symbol: str,
    ) -> float:
        """
        Signed current position quantity.

        Positive:
            long

        Negative:
            short

        Zero:
            flat
        """
        ...


# ============================================================
# Simple testing context
# ============================================================


@dataclass(slots=True)
class SimpleBrokerContext:
    """
    Minimal BrokerContext implementation.

    Useful for unit tests.

    It intentionally does not know anything about Portfolio.
    """

    equity_value: float

    cash_value: float

    prices: dict[str, float]

    positions: dict[str, float]

    @property
    def equity(self) -> float:
        return self.equity_value

    @property
    def available_cash(self) -> float:
        return self.cash_value

    @property
    def price_lookup(self) -> dict[str, float]:
        return self.prices

    def position_quantity(
        self,
        symbol: str,
    ) -> float:
        return self.positions.get(
            symbol,
            0.0,
        )


# ============================================================
# Broker
# ============================================================


@dataclass(slots=True)
class Broker:
    """
    Strategy-intent -> Order translator.

    Currently supports:

    - MARKET orders
    - absolute unit sizing
    - percentage equity sizing
    - percentage position sizing
    - full position exits
    - partial position exits

    The Broker never executes an Order.
    """

    # Estimated transaction cost used only when sizing BUY
    # orders against available cash.

    estimated_fee_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.estimated_fee_rate < 0:
            raise ValueError(
                "estimated_fee_rate cannot be negative."
            )

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def create_order(
        self,
        *,
        signal: Signal,
        context: BrokerContext,
    ) -> Order | None:
        """
        Convert a strategy Signal into an executable Order.

        Returns None when:

        - signal is HOLD
        - requested action is impossible
        - requested quantity resolves to zero
        """

        if signal.is_hold:
            return None

        side = self._resolve_side(
            signal.action
        )

        if side is None:
            return None

        quantity = self._resolve_quantity(
            signal=signal,
            context=context,
        )

        if quantity <= 0:
            return None

        self._validate_order(
            signal=signal,
            side=side,
            quantity=quantity,
            context=context,
        )

        return Order(
            id=str(uuid4()),
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            metadata={
                "signal_action": signal.action.name,
                "confidence": signal.confidence,
                **signal.metadata,
            },
        )

    # --------------------------------------------------------
    # Quantity resolution
    # --------------------------------------------------------

    def _resolve_quantity(
        self,
        signal: Signal,
        context: BrokerContext,
    ) -> float:

        if signal.quantity <= 0:
            return 0.0

        # --------------------------------------------------
        # Explicit exits are always position-aware
        # --------------------------------------------------

        if signal.action in (
            SignalAction.EXIT_LONG,
            SignalAction.EXIT_SHORT,
        ):

            position_quantity = abs(
                context.position_quantity(
                    signal.symbol
                )
            )

            return self._resolve_exit_quantity(
                signal=signal,
                position_quantity=position_quantity,
            )

        # --------------------------------------------------
        # Entries
        # --------------------------------------------------

        if signal.sizing is PositionSizing.UNITS:
            return signal.quantity

        if signal.sizing is PositionSizing.PERCENT_EQUITY:
            return self._resolve_equity_quantity(
                signal=signal,
                context=context,
            )

        if signal.sizing is PositionSizing.PERCENT_POSITION:
            raise ValueError(
                "PERCENT_POSITION is only valid for exits."
            )

        raise ValueError(
            f"Unsupported position sizing mode: "
            f"{signal.sizing}"
        )
    
    # --------------------------------------------------------
    # Equity sizing
    # --------------------------------------------------------

    def _resolve_equity_quantity(
        self,
        *,
        signal: Signal,
        context: BrokerContext,
    ) -> float:
        """
        Convert percentage-of-equity sizing into executable units.
        """

        if context.equity <= 0:
            raise ValueError(
                "Cannot size order with zero equity."
            )

        price = context.price_lookup.get(
            signal.symbol
        )

        if price is None or price <= 0:
            raise ValueError(
                "Missing positive price for percentage sizing."
            )

        requested_capital = (
            context.equity
            * signal.quantity
            / 100.0
        )

        if requested_capital <= 0:
            return 0.0

        # BUY orders must fit inside available cash,
        # including the estimated broker fee.
        if signal.action is SignalAction.LONG:

            notional = min(
                requested_capital,
                context.available_cash
                / (1.0 + self.estimated_fee_rate),
            )

        else:
            # SELL / SHORT does not consume spot cash
            # in this accounting model.
            notional = requested_capital

        return notional / price


    # --------------------------------------------------------
    # Exit sizing
    # --------------------------------------------------------

    @staticmethod
    def _resolve_exit_quantity(
        *,
        signal: Signal,
        position_quantity: float,
    ) -> float:
        """
        Resolve how much of an existing position should be closed.

        EXIT_* semantics are position-aware.

        UNITS:
            close explicit number of units

        PERCENT_POSITION:
            close percentage of current position

        PERCENT_EQUITY:
            treated as full exit because an explicit exit
            should be driven by position state rather than
            account equity.
        """

        if position_quantity <= 0:
            return 0.0

        if signal.sizing is PositionSizing.UNITS:

            return min(
                signal.quantity,
                position_quantity,
            )

        if signal.sizing is PositionSizing.PERCENT_POSITION:

            return min(
                position_quantity
                * signal.quantity
                / 100.0,
                position_quantity,
            )

        if signal.sizing is PositionSizing.PERCENT_EQUITY:

            # Explicit EXIT intent means:
            #
            # "remove this exposure"
            #
            # not:
            #
            # "sell X dollars worth"
            #
            # Therefore a percentage-equity exit closes the
            # current position completely.
            return position_quantity

        raise ValueError(
            "Unsupported exit sizing mode."
        )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    def _validate_order(
        self,
        *,
        signal: Signal,
        side: OrderSide,
        quantity: float,
        context: BrokerContext,
    ) -> None:
        """
        Validate the resolved order against current state.
        """

        if quantity <= 0:
            raise ValueError(
                "Resolved order quantity must be positive."
            )

        price = context.price_lookup.get(
            signal.symbol
        )

        if price is None or price <= 0:
            raise ValueError(
                "Missing positive market price."
            )

        # EXIT_LONG must actually be selling a long.
        if signal.action is SignalAction.EXIT_LONG:

            if (
                context.position_quantity(
                    signal.symbol
                )
                <= 0
            ):
                raise ValueError(
                    "Cannot EXIT_LONG without a long position."
                )

            if side is not OrderSide.SELL:
                raise ValueError(
                    "EXIT_LONG must produce a SELL order."
                )

        # EXIT_SHORT must actually be buying a short.
        if signal.action is SignalAction.EXIT_SHORT:

            if (
                context.position_quantity(
                    signal.symbol
                )
                >= 0
            ):
                raise ValueError(
                    "Cannot EXIT_SHORT without a short position."
                )

            if side is not OrderSide.BUY:
                raise ValueError(
                    "EXIT_SHORT must produce a BUY order."
                )

    # --------------------------------------------------------
    # Action -> exchange side
    # --------------------------------------------------------

    @staticmethod
    def _resolve_side(
        action: SignalAction,
    ) -> OrderSide | None:
        """
        Translate high-level intent into exchange transaction
        direction.

        LONG:
            BUY

        SHORT:
            SELL

        EXIT_LONG:
            SELL

        EXIT_SHORT:
            BUY
        """

        if action is SignalAction.LONG:
            return OrderSide.BUY

        if action is SignalAction.SHORT:
            return OrderSide.SELL

        if action is SignalAction.EXIT_LONG:
            return OrderSide.SELL

        if action is SignalAction.EXIT_SHORT:
            return OrderSide.BUY

        return None