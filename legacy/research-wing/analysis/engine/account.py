"""
analysis.engine.account

Account model.

Tracks cash and capital state during simulation.

Account owns:
- cash
- starting capital
- deposits
- withdrawals
- realized P&L bookkeeping
- reserved cash

Account does NOT own:
- positions
- trades
- market prices
- portfolio valuation
- execution logic

Portfolio owns asset positions.
Execution produces Trades.
Portfolio applies Trades to Account and Positions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Account:
    """
    Trading account state.

    The Account is responsible only for monetary state.

    Cash is actual available account currency.

    Realized P&L is a bookkeeping measure and is NOT
    added to cash independently. Cash changes through
    actual capital movements and trade cash flows.

    This separation is important:

        Trade
          |
          +--> cash movement
          |
          +--> position change
          |
          +--> realized P&L

    Realized P&L must never be treated as a second
    source of cash.
    """

    starting_balance: float

    cash: float | None = None

    realized_pnl: float = 0.0

    _reserved_cash: float = 0.0

    _total_deposits: float = 0.0

    _total_withdrawals: float = 0.0

    def __post_init__(self) -> None:
        """
        Validate and initialize account state.
        """

        if self.starting_balance < 0:
            raise ValueError(
                "Starting balance cannot be negative."
            )

        if self.cash is None:
            self.cash = self.starting_balance

        if self.cash < 0:
            raise ValueError(
                "Cash cannot be negative."
            )

        if self.realized_pnl != 0:
            raise ValueError(
                "Initial realized P&L must be zero."
            )

        if self._reserved_cash < 0:
            raise ValueError(
                "Reserved cash cannot be negative."
            )

        if self._total_deposits < 0:
            raise ValueError(
                "Total deposits cannot be negative."
            )

        if self._total_withdrawals < 0:
            raise ValueError(
                "Total withdrawals cannot be negative."
            )

    # --------------------------------------------------
    # Capital
    # --------------------------------------------------

    @property
    def total_deposits(self) -> float:
        """
        Total external capital deposited after initialization.

        The starting balance is not included.
        """

        return self._total_deposits

    @property
    def total_withdrawals(self) -> float:
        """
        Total external capital withdrawn after initialization.
        """

        return self._total_withdrawals

    @property
    def net_external_flow(self) -> float:
        """
        Net external capital flow after initialization.

        Positive:
            More capital was deposited than withdrawn.

        Negative:
            More capital was withdrawn than deposited.
        """

        return (
            self._total_deposits
            - self._total_withdrawals
        )

    @property
    def deposits(self) -> float:
        """
        Backwards-compatible alias for total deposits.

        This represents actual external deposits only.

        It does NOT attempt to infer deposits from cash
        and realized P&L.
        """

        return self._total_deposits

    # --------------------------------------------------
    # Cash
    # --------------------------------------------------

    @property
    def available_cash(self) -> float:
        """
        Cash currently available for new transactions.

        Reserved cash is excluded.
        """

        return (
            self.cash
            - self._reserved_cash
        )

    @property
    def reserved_cash(self) -> float:
        """
        Cash reserved for pending orders.
        """

        return self._reserved_cash

    # --------------------------------------------------
    # External capital
    # --------------------------------------------------

    def deposit(
        self,
        amount: float,
    ) -> None:
        """
        Add external capital to the account.
        """

        self._validate_positive_amount(
            amount,
            "Deposit",
        )

        self.cash += amount
        self._total_deposits += amount

    def withdraw(
        self,
        amount: float,
    ) -> None:
        """
        Remove external capital from the account.

        Withdrawals can only use currently available cash.
        """

        self._validate_positive_amount(
            amount,
            "Withdrawal",
        )

        if amount > self.available_cash:
            raise ValueError(
                "Insufficient available cash."
            )

        self.cash -= amount
        self._total_withdrawals += amount

    # --------------------------------------------------
    # Trade cash flow
    # --------------------------------------------------

    def debit_cash(
        self,
        amount: float,
    ) -> None:
        """
        Remove cash as the result of a transaction.

        Used by Portfolio when a trade requires a cash
        outflow, such as a spot BUY.

        This is NOT a withdrawal.

        It therefore does not affect deposit/withdrawal
        statistics.
        """

        self._validate_positive_amount(
            amount,
            "Cash debit",
        )

        if amount > self.available_cash:
            raise ValueError(
                "Insufficient available cash."
            )

        self.cash -= amount

    def credit_cash(
        self,
        amount: float,
    ) -> None:
        """
        Add cash as the result of a transaction.

        Used by Portfolio when a trade produces a cash
        inflow, such as a spot SELL.

        This is NOT a deposit.
        """

        self._validate_positive_amount(
            amount,
            "Cash credit",
        )

        self.cash += amount

    # --------------------------------------------------
    # Order reservation
    # --------------------------------------------------

    def reserve(
        self,
        amount: float,
    ) -> None:
        """
        Reserve cash for a pending order.

        Reservation does not permanently remove cash.

        Example:

            cash = 10,000
            reserve = 2,000

            cash            = 10,000
            reserved_cash   = 2,000
            available_cash  = 8,000
        """

        self._validate_positive_amount(
            amount,
            "Reservation",
        )

        if amount > self.available_cash:
            raise ValueError(
                "Insufficient available cash."
            )

        self._reserved_cash += amount

    def release(
        self,
        amount: float,
    ) -> None:
        """
        Release previously reserved cash.

        Released cash becomes available again.
        """

        self._validate_positive_amount(
            amount,
            "Release",
        )

        if amount > self._reserved_cash:
            raise ValueError(
                "Cannot release more cash than reserved."
            )

        self._reserved_cash -= amount

    # --------------------------------------------------
    # Realized P&L
    # --------------------------------------------------

    def record_realized_pnl(
        self,
        pnl: float,
    ) -> None:
        """
        Record realized profit or loss.

        IMPORTANT:

        This method changes the P&L ledger only.

        It does NOT change cash.

        Cash must already have been updated through
        the corresponding trade cash flow.

        Example:

            Buy 1 BTC @ 100
            Sell 1 BTC @ 120

        The portfolio records:

            cash:
                -100
                +120

            realized P&L:
                +20

        The +20 must NOT be added to cash again.
        """

        if not isinstance(pnl, (int, float)):
            raise TypeError(
                "Realized P&L must be numeric."
            )

        self.realized_pnl += pnl

    # --------------------------------------------------
    # Accounting helpers
    # --------------------------------------------------

    @property
    def capital_contributed(self) -> float:
        """
        Total capital contributed to the account.

        Includes the initial starting balance and all
        subsequent external deposits.
        """

        return (
            self.starting_balance
            + self._total_deposits
        )

    @property
    def capital_withdrawn(self) -> float:
        """
        Total capital withdrawn from the account.
        """

        return self._total_withdrawals

    # --------------------------------------------------
    # Validation
    # --------------------------------------------------

    @staticmethod
    def _validate_positive_amount(
        amount: float,
        label: str,
    ) -> None:
        """
        Validate a monetary amount.
        """

        if amount <= 0:
            raise ValueError(
                f"{label} must be positive."
            )

    # --------------------------------------------------
    # Representation
    # --------------------------------------------------

    def __repr__(self) -> str:
        return (
            "Account("
            f"cash={self.cash:.2f}, "
            f"available={self.available_cash:.2f}, "
            f"reserved={self.reserved_cash:.2f}, "
            f"realized={self.realized_pnl:.2f}"
            ")"
        )