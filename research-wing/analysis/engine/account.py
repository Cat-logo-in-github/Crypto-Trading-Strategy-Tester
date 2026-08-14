"""
analysis.engine.account

Account model.

Tracks capital state during simulation.

Account manages money.
Portfolio manages ownership.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Account:
    """
    Trading account state.

    Responsible for:

    - cash tracking
    - capital accounting
    - realized profit/loss

    Does not manage positions.
    """

    starting_balance: float

    cash: float | None = None

    realized_pnl: float = 0.0


    def __post_init__(self) -> None:
        """
        Initialize account.
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



    @property
    def deposits(self) -> float:
        """
        Capital added since start.

        Placeholder for future support.
        """

        return (
            self.cash
            -
            self.starting_balance
            +
            self.realized_pnl
        )



    @property
    def available_cash(self) -> float:
        """
        Spendable cash.
        """

        return self.cash



    def deposit(
        self,
        amount: float
    ) -> None:
        """
        Add capital.
        """

        if amount <= 0:
            raise ValueError(
                "Deposit must be positive."
            )

        self.cash += amount



    def withdraw(
        self,
        amount: float
    ) -> None:
        """
        Remove capital.
        """

        if amount <= 0:
            raise ValueError(
                "Withdrawal must be positive."
            )

        if amount > self.cash:
            raise ValueError(
                "Insufficient cash."
            )

        self.cash -= amount



    def reserve(
        self,
        amount: float
    ) -> None:
        """
        Remove cash for pending orders.

        Used later by Broker.
        """

        if amount > self.cash:
            raise ValueError(
                "Insufficient cash."
            )

        self.cash -= amount



    def release(
        self,
        amount: float
    ) -> None:
        """
        Return reserved funds.
        """

        self.cash += amount



    def apply_realized_pnl(
        self,
        pnl: float
    ) -> None:
        """
        Update realized profit/loss.
        """

        self.realized_pnl += pnl

        self.cash += pnl



    def __repr__(self) -> str:

        return (
            "Account("
            f"cash={self.cash:.2f}, "
            f"realized={self.realized_pnl:.2f}"
            ")"
        )