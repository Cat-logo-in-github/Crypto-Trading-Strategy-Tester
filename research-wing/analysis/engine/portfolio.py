"""
analysis.engine.portfolio

Portfolio state and execution accounting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.engine.account import Account
from analysis.engine.position import Position
from analysis.engine.trade import Trade, TradeSide


@dataclass(slots=True)
class Portfolio:
    """
    Mutable portfolio state.

    Portfolio owns:

    - account
    - positions
    - execution history

    Portfolio does not create trades or make trading decisions.
    """

    account: Account

    positions: dict[str, Position] = field(
        default_factory=dict
    )

    trades: list[Trade] = field(
        default_factory=list
    )

    # =========================================================
    # Execution
    # =========================================================

    def apply_trade(
        self,
        trade: Trade,
    ) -> None:
        """
        Apply a completed execution atomically.

        A trade produces:

            1. cash movement
            2. position transition
            3. realized PnL bookkeeping
            4. execution-history record

        Cash affordability is checked before the position is
        mutated so a failed cash operation cannot leave the
        portfolio partially updated.
        """

        self._validate_trade(trade)

        # -----------------------------------------------------
        # Validate cash BEFORE mutating position
        # -----------------------------------------------------

        self._validate_cash_movement(trade)

        # -----------------------------------------------------
        # Resolve position
        # -----------------------------------------------------

        position = self.positions.get(
            trade.symbol
        )

        if position is None:

            position = Position(
                symbol=trade.symbol
            )

            self.positions[
                trade.symbol
            ] = position

        # -----------------------------------------------------
        # Capture previous realized PnL
        # -----------------------------------------------------

        previous_realized_pnl = (
            position.realized_pnl
        )

        # -----------------------------------------------------
        # Apply position transition
        # -----------------------------------------------------

        position.apply_trade(
            trade
        )

        realized_pnl_change = (
            position.realized_pnl
            - previous_realized_pnl
        )

        # -----------------------------------------------------
        # Apply cash movement
        # -----------------------------------------------------

        self._apply_cash_movement(
            trade
        )

        # -----------------------------------------------------
        # Record realized PnL
        # -----------------------------------------------------

        if realized_pnl_change != 0:

            self.account.record_realized_pnl(
                realized_pnl_change
            )

        # -----------------------------------------------------
        # Record execution
        # -----------------------------------------------------

        self.trades.append(
            trade
        )

    # =========================================================
    # Validation
    # =========================================================

    @staticmethod
    def _validate_trade(
        trade: Trade,
    ) -> None:
        """
        Validate basic trade invariants.
        """

        if trade.quantity <= 0:
            raise ValueError(
                "Trade quantity must be positive."
            )

        if trade.price <= 0:
            raise ValueError(
                "Trade price must be positive."
            )

        if trade.fees < 0:
            raise ValueError(
                "Trade fees cannot be negative."
            )

    def _validate_cash_movement(
        self,
        trade: Trade,
    ) -> None:
        """
        Validate whether the trade's cash consequence is
        currently possible.

        BUY:

            cash required =
                trade.value + fees

        SELL:

            cash received =
                trade.value - fees

        This method does not mutate state.
        """

        if trade.side is TradeSide.BUY:

            required = (
                trade.value
                + trade.fees
            )

            if required > self.account.available_cash:
                raise ValueError(
                    "Insufficient available cash for trade: "
                    f"required={required:.8f}, "
                    f"available={self.account.available_cash:.8f}, "
                    f"value={trade.value:.8f}, "
                    f"fees={trade.fees:.8f}"
                )

        elif trade.side is TradeSide.SELL:

            proceeds = (
                trade.value
                - trade.fees
            )

            if proceeds < 0:
                raise ValueError(
                    "Trade fees exceed trade value."
                )

        else:
            raise ValueError(
                f"Unsupported trade side: {trade.side}"
            )

    # =========================================================
    # Cash accounting
    # =========================================================

    def _apply_cash_movement(
        self,
        trade: Trade,
    ) -> None:
        """
        Apply the actual cash consequence of a trade.

        BUY:

            cash -= value + fees

        SELL:

            cash += value - fees
        """

        if trade.side is TradeSide.BUY:

            cash_debit = (
                trade.value
                + trade.fees
            )

            self.account.debit_cash(
                cash_debit
            )

        elif trade.side is TradeSide.SELL:

            cash_credit = (
                trade.value
                - trade.fees
            )

            if cash_credit > 0:

                self.account.credit_cash(
                    cash_credit
                )

        else:
            raise ValueError(
                f"Unsupported trade side: {trade.side}"
            )

    # =========================================================
    # Position access
    # =========================================================

    def position(
        self,
        symbol: str,
    ) -> Position | None:

        return self.positions.get(
            symbol
        )

    def has_position(
        self,
        symbol: str,
    ) -> bool:

        position = self.position(
            symbol
        )

        return (
            position is not None
            and position.is_open
        )

    def position_quantity(
        self,
        symbol: str,
    ) -> float:

        position = self.position(
            symbol
        )

        if position is None:
            return 0.0

        return position.quantity

    # =========================================================
    # Position cleanup
    # =========================================================

    def close_position(
        self,
        symbol: str,
    ) -> None:

        position = self.positions.get(
            symbol
        )

        if (
            position is not None
            and not position.is_open
        ):
            del self.positions[
                symbol
            ]

    # =========================================================
    # Valuation
    # =========================================================

    def equity(
        self,
        prices: dict[str, float],
    ) -> float:

        total = float(
            self.account.cash
        )

        for symbol, position in self.positions.items():

            if not position.is_open:
                continue

            price = prices.get(
                symbol
            )

            if price is None:
                continue

            total += position.market_value(
                price
            )

        return total

    def market_value(
        self,
        prices: dict[str, float],
    ) -> float:

        total = 0.0

        for symbol, position in self.positions.items():

            if not position.is_open:
                continue

            price = prices.get(
                symbol
            )

            if price is None:
                continue

            total += abs(
                position.market_value(
                    price
                )
            )

        return total

    # =========================================================
    # Account information
    # =========================================================

    @property
    def cash(self) -> float:
        return self.account.cash

    @property
    def available_cash(self) -> float:
        return self.account.available_cash

    @property
    def realized_pnl(self) -> float:
        return self.account.realized_pnl

    # =========================================================
    # Representation
    # =========================================================

    def __repr__(self) -> str:

        return (
            "Portfolio("
            f"cash={self.account.cash:.2f}, "
            f"available={self.account.available_cash:.2f}, "
            f"positions={len(self.positions)}, "
            f"trades={len(self.trades)}"
            ")"
        )