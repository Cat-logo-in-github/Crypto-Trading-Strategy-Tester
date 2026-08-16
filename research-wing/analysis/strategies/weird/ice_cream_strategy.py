"""
analysis.strategies.weird.ice_cream_strategy

Alternative-data strategy driven by FRED industrial production
data for ice cream / frozen desserts.

The external data is monthly while BTC market data may be minute-level.

The strategy deliberately bridges the frequency mismatch through a
deterministic signal schedule.

Signal cadence
--------------

Research window > 1 month
    One signal at the first BTC candle of each calendar month.

Research window > 2 days and <= 1 month
    One signal at the first BTC candle of each calendar day.

Research window <= 2 days
    One signal every 2 hours.

Important
---------

For the short-window modes, the available research window may contain
more signal slots than there are monthly observations inside that
window.

Therefore the strategy deliberately constructs a historical monthly
signal stream beginning approximately five years before the requested
research period.

Example:

    8 daily signals requested

becomes:

    month 1 -> January
    month 2 -> February
    month 3 -> March
    ...

Each signal therefore represents a NEW monthly ice-cream observation.

Every observation is evaluated against the previous six monthly
observations.

The strategy never executes trades directly.

Pipeline:

    Ice Cream Data
         |
         v
    IceCreamSalesStrategy
         |
         v
       Signal
         |
         v
       Broker
         |
         v
       Matcher
         |
         v
      Portfolio
         |
         v
      Evaluation
"""

from __future__ import annotations

import csv
import io
import urllib.request

from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean


from analysis.strategies.base import Strategy

from analysis.engine.models.context import StrategyContext

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)


class IceCreamProductionStrategy(Strategy):

    name = "IceCreamProductionStrategy"

    FRED_URL = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        "?id=IPN31152N"
    )

    # Used only for short-window experiments.
    # This gives us enough monthly observations to generate
    # daily / 2-hour signals without running out of monthly data.
    SHORT_WINDOW_HISTORY_YEARS = 5

    def __init__(
        self,
        *,
        start_time: int | None,
        end_time: int | None,
        lookback: int = 6,
        allocation: float = 99.0,
        external_path: str = (
            "analysis/data/external/ice_cream_sales.csv"
        ),
    ) -> None:

        super().__init__()

        # --------------------------------------------------
        # Validate parameters
        # --------------------------------------------------

        if lookback <= 0:
            raise ValueError(
                "lookback must be positive."
            )

        if not 0 < allocation <= 100:
            raise ValueError(
                "allocation must be between 0 and 100."
            )

        if start_time is None or end_time is None:
            raise ValueError(
                "IceCreamSalesStrategy requires "
                "start_time and end_time."
            )

        if end_time <= start_time:
            raise ValueError(
                "end_time must be greater than start_time."
            )

        self.start_time = int(start_time)
        self.end_time = int(end_time)

        self.start_datetime = self._timestamp_to_datetime(
            self.start_time
        )

        self.end_datetime = self._timestamp_to_datetime(
            self.end_time
        )

        self.start_date = self.start_datetime.date()
        self.end_date = self.end_datetime.date()

        self.lookback = lookback
        self.allocation = allocation

        self.external_path = Path(
            external_path
        )

        self.external_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # --------------------------------------------------
        # Load external data
        # --------------------------------------------------

        self.sales = self._load_external_data()

        if not self.sales:
            raise ValueError(
                "Ice-cream external dataset contains "
                "no usable observations."
            )

        self.monthly_dates = sorted(
            self.sales.keys()
        )

        # --------------------------------------------------
        # Determine signal cadence
        # --------------------------------------------------

        self.signal_frequency = (
            self._determine_signal_frequency()
        )

        # --------------------------------------------------
        # Build deterministic signal schedule
        # --------------------------------------------------

        self.signal_schedule = (
            self._build_signal_schedule()
        )

        # timestamp -> monthly observation date

        self._signal_lookup = {
            timestamp: observation_date
            for timestamp, observation_date
            in self.signal_schedule
        }

        self._consumed_signal_timestamps: set[int] = set()

        print(
            "Ice-cream signal frequency: "
            f"{self.signal_frequency}"
        )

        print(
            "Ice-cream signal dates: "
            f"{len(self.signal_schedule)}"
        )

    # ======================================================
    # Strategy interface
    # ======================================================

    def on(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Generate a signal only when the current market candle
        matches a predetermined signal timestamp.

        The engine supplies timestamps as integer Unix
        milliseconds, so this method explicitly normalizes
        the timestamp before doing anything else.
        """

        current_timestamp = self._normalize_timestamp(
            context.timestamp
        )

        observation_date = self._signal_lookup.get(
            current_timestamp
        )

        if observation_date is None:
            return None

        # --------------------------------------------------
        # Safety: never emit twice for the same signal slot.
        # --------------------------------------------------

        if (
            current_timestamp
            in self._consumed_signal_timestamps
        ):
            return None

        self._consumed_signal_timestamps.add(
            current_timestamp
        )

        # --------------------------------------------------
        # Current monthly observation
        # --------------------------------------------------

        current_value = self.sales.get(
            observation_date
        )

        if current_value is None:
            return self._hold(
                context,
                observation_date=observation_date,
            )

        # --------------------------------------------------
        # Six-month historical baseline
        #
        # STRICTLY before the current observation.
        #
        # This is critical:
        #
        #     Jan 2020
        #
        # may use:
        #
        #     Jul-Dec 2019
        #
        # but NEVER Jan 2020 itself.
        # --------------------------------------------------

        history = self._history_before(
            observation_date
        )

        if len(history) < self.lookback:
            return self._hold(
                context,
                observation_date=observation_date,
                current_value=current_value,
            )

        baseline_values = history[
            -self.lookback:
        ]

        baseline = mean(
            baseline_values
        )

        # --------------------------------------------------
        # Determine regime
        # --------------------------------------------------

        if current_value > baseline:

            regime = "HIGH"

        elif current_value < baseline:

            regime = "LOW"

        else:

            regime = "NEUTRAL"

        metadata = {
            "strategy": self.name,

            "external_dataset": (
                "FRED:IPN31152N"
            ),

            "external_observation_date": (
                observation_date.isoformat()
            ),

            "external_value": current_value,

            "external_baseline": baseline,

            "external_baseline_months": (
                self.lookback
            ),

            "external_regime": regime,

            "signal_frequency": (
                self.signal_frequency
            ),

            "signal_timestamp": (
                current_timestamp
            ),
        }

        # --------------------------------------------------
        # HIGH -> LONG
        # --------------------------------------------------

        if regime == "HIGH":

            return Signal(
                timestamp=context.timestamp,
                symbol=context.symbol,
                action=SignalAction.LONG,
                quantity=self.allocation,
                sizing=PositionSizing.PERCENT_EQUITY,
                confidence=0.5,
                metadata=metadata,
            )

        # --------------------------------------------------
        # LOW -> EXIT LONG
        # --------------------------------------------------

        if regime == "LOW":

            return Signal(
                timestamp=context.timestamp,
                symbol=context.symbol,
                action=SignalAction.EXIT_LONG,
                quantity=100.0,
                sizing=PositionSizing.PERCENT_POSITION,
                confidence=0.5,
                metadata=metadata,
            )

        # --------------------------------------------------
        # NEUTRAL
        # --------------------------------------------------

        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=SignalAction.HOLD,
            quantity=0.0,
            sizing=PositionSizing.PERCENT_EQUITY,
            confidence=0.0,
            metadata=metadata,
        )

    # ======================================================
    # Signal frequency
    # ======================================================

    def _determine_signal_frequency(
        self,
    ) -> str:

        span = (
            self.end_datetime
            - self.start_datetime
        )

        if span <= timedelta(days=2):

            return "2h"

        if span <= timedelta(days=31):

            return "daily"

        return "monthly"

    # ======================================================
    # Signal schedule
    # ======================================================

    def _build_signal_schedule(
        self,
    ) -> list[tuple[int, date]]:
        """
        Build:

            market signal timestamp
                ->
            monthly ice-cream observation

        The schedule is deterministic.

        Long window:
            Actual research months are used.

        Short window:
            Monthly observations begin approximately five
            years before the requested start and are consumed
            sequentially.
        """

        if self.signal_frequency == "monthly":

            return self._build_monthly_schedule()

        if self.signal_frequency == "daily":

            signal_times = (
                self._build_daily_schedule()
            )

        else:

            signal_times = (
                self._build_two_hour_schedule()
            )

        return self._map_short_window_signals(
            signal_times
        )

    # ======================================================
    # Long-window monthly schedule
    # ======================================================

    def _build_monthly_schedule(
        self,
    ) -> list[tuple[int, date]]:
        """
        One signal at the first market candle of every
        calendar month inside the requested research window.

        The signal uses that month's external observation.

        No five-year offset is used here.
        """

        schedule = []

        current = date(
            self.start_date.year,
            self.start_date.month,
            1,
        )

        while current <= self.end_date:

            signal_date = max(
                current,
                self.start_date,
            )

            # Find the actual first candle timestamp
            # represented by the requested start boundary.
            #
            # Since the backtester calls us on actual candles,
            # we schedule at the first valid market timestamp
            # for the month/day rather than inventing a candle.
            signal_datetime = self._first_market_time_for_date(
                signal_date
            )

            if signal_datetime is not None:

                observation_date = date(
                    current.year,
                    current.month,
                    1,
                )

                if observation_date in self.sales:

                    schedule.append(
                        (
                            self._datetime_to_timestamp(
                                signal_datetime
                            ),
                            observation_date,
                        )
                    )

            current = self._next_month(
                current
            )

        return schedule

    # ======================================================
    # Daily schedule
    # ======================================================

    def _build_daily_schedule(
        self,
    ) -> list[int]:
        """
        One signal per calendar day.

        Signal timestamps are aligned to the requested
        research start time.

        The actual mapping to monthly observations is
        performed separately.
        """

        timestamps = []

        current_date = self.start_date

        while current_date <= self.end_date:

            candidate = datetime.combine(
                current_date,
                self.start_datetime.time(),
            )

            candidate_timestamp = (
                self._datetime_to_timestamp(
                    candidate
                )
            )

            # First signal cannot precede the requested start.
            if candidate_timestamp < self.start_time:
                candidate_timestamp = self.start_time

            if candidate_timestamp <= self.end_time:
                timestamps.append(
                    candidate_timestamp
                )

            current_date += timedelta(
                days=1
            )

        return timestamps

    # ======================================================
    # Two-hour schedule
    # ======================================================

    def _build_two_hour_schedule(
        self,
    ) -> list[int]:
        """
        One signal every two hours.

        The first signal occurs exactly at start_time.
        """

        timestamps = []

        current = self.start_datetime

        while current <= self.end_datetime:

            timestamps.append(
                self._datetime_to_timestamp(
                    current
                )
            )

            current += timedelta(
                hours=2
            )

        return timestamps

    # ======================================================
    # Short-window monthly mapping
    # ======================================================

    def _map_short_window_signals(
        self,
        signal_times: list[int],
    ) -> list[tuple[int, date]]:
        """
        Map each short-window signal to a NEW monthly
        observation.

        The monthly sequence begins approximately five years
        before the requested research period.

        Example:

            signal 1 -> Jan 2019
            signal 2 -> Feb 2019
            signal 3 -> Mar 2019
            ...

        The exact starting month is anchored to the requested
        start month.

        This gives every signal a unique monthly observation
        and prevents a short research window from repeatedly
        using the same monthly value.
        """

        if not signal_times:
            return []

        anchor_year = (
            self.start_date.year
            - self.SHORT_WINDOW_HISTORY_YEARS
        )

        anchor_month = (
            self.start_date.month
        )

        observation_dates = []

        current = date(
            anchor_year,
            anchor_month,
            1,
        )

        for _ in signal_times:

            # Make sure we have a six-month historical
            # baseline available.
            #
            # If not, move forward until one exists.
            while True:

                history = self._history_before(
                    current
                )

                if len(history) >= self.lookback:
                    break

                current = self._next_month(
                    current
                )

            observation_dates.append(
                current
            )

            current = self._next_month(
                current
            )

        # --------------------------------------------------
        # Verify that the downloaded FRED dataset contains
        # every required observation.
        # --------------------------------------------------

        missing = [
            d
            for d in observation_dates
            if d not in self.sales
        ]

        if missing:

            raise ValueError(
                "Ice-cream dataset does not contain "
                "enough monthly observations for the "
                "requested short-window experiment. "
                f"Missing {len(missing)} observations."
            )

        return list(
            zip(
                signal_times,
                observation_dates,
            )
        )

    # ======================================================
    # First market timestamp helper
    # ======================================================

    def _first_market_time_for_date(
        self,
        target_date: date,
    ) -> datetime | None:
        """
        For monthly scheduling we cannot know the actual
        BTC candle timestamps from the strategy constructor.

        Return the requested start-of-day time as the intended
        schedule point. The backtester will only call `on()`
        at real candles, so the schedule is later matched by
        date/month in `_resolve_market_signal`.
        """

        if target_date == self.start_date:

            return self.start_datetime

        return datetime.combine(
            target_date,
            datetime.min.time(),
        )

    # ======================================================
    # External data
    # ======================================================

    def _load_external_data(
        self,
    ) -> dict[date, float]:
        """
        Load cached external data when available.

        Download only when the cache does not exist or contains
        no usable rows.
        """

        if self.external_path.exists():

            cached = (
                self._load_cached_external_data()
            )

            if cached:

                print(
                    "Loading cached "
                    "ice-cream research data..."
                )

                print(
                    "Using cached ice-cream data: "
                    f"{len(cached)} observations"
                )

                return cached

        print(
            "Downloading ice-cream research data..."
        )

        with urllib.request.urlopen(
            self.FRED_URL,
            timeout=30,
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

        reader = csv.DictReader(
            io.StringIO(raw)
        )

        rows = []

        for row in reader:

            observation_date = (
                row.get("observation_date")
                or row.get("DATE")
            )

            value = row.get(
                "IPN31152N"
            )

            if not observation_date:
                continue

            if value in (
                None,
                "",
                ".",
            ):
                continue

            try:

                parsed_date = (
                    date.fromisoformat(
                        observation_date
                    )
                )

                parsed_value = float(
                    value
                )

            except (
                ValueError,
                TypeError,
            ):

                continue

            rows.append(
                {
                    "date": (
                        parsed_date.isoformat()
                    ),
                    "value": parsed_value,
                }
            )

        if not rows:

            raise ValueError(
                "FRED returned no usable "
                "ice-cream observations."
            )

        self._save_csv(
            rows
        )

        return {
            date.fromisoformat(
                row["date"]
            ): float(
                row["value"]
            )
            for row in rows
        }

    # ======================================================
    # Cached external data
    # ======================================================

    def _load_cached_external_data(
        self,
    ) -> dict[date, float]:
        """
        Read the existing CSV.

        Supports both:

            date,value

        and the original FRED:

            observation_date,IPN31152N
        """

        try:

            with self.external_path.open(
                "r",
                newline="",
                encoding="utf-8",
            ) as file:

                reader = csv.DictReader(
                    file
                )

                if not reader.fieldnames:
                    return {}

                rows = []

                for row in reader:

                    observation_date = (
                        row.get("date")
                        or row.get(
                            "observation_date"
                        )
                    )

                    value = (
                        row.get("value")
                        or row.get(
                            "IPN31152N"
                        )
                    )

                    if not observation_date:
                        continue

                    if value in (
                        None,
                        "",
                        ".",
                    ):
                        continue

                    try:

                        parsed_date = (
                            date.fromisoformat(
                                observation_date
                            )
                        )

                        parsed_value = float(
                            value
                        )

                    except (
                        ValueError,
                        TypeError,
                    ):

                        continue

                    rows.append(
                        (
                            parsed_date,
                            parsed_value,
                        )
                    )

                return dict(
                    rows
                )

        except (
            OSError,
            csv.Error,
        ):

            return {}

    # ======================================================
    # Persistence
    # ======================================================

    def _save_csv(
        self,
        rows: list[dict[str, object]],
    ) -> None:

        with self.external_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "date",
                    "value",
                ],
            )

            writer.writeheader()
            writer.writerows(
                rows
            )

        print(
            f"Ice-cream data saved to "
            f"{self.external_path}"
        )

    # ======================================================
    # Historical observations
    # ======================================================

    def _history_before(
        self,
        observation_date: date,
    ) -> list[float]:
        """
        Return all external observations strictly before
        the current observation.
        """

        dates = sorted(
            d
            for d in self.sales
            if d < observation_date
        )

        return [
            self.sales[d]
            for d in dates
        ]

    # ======================================================
    # Timestamp normalization
    # ======================================================

    @staticmethod
    def _normalize_timestamp(
        timestamp,
    ) -> int:
        """
        Normalize whatever the engine gives us into
        Unix milliseconds.

        The current Research Wing engine uses integers,
        but accepting datetime/date makes the strategy
        robust.
        """

        if isinstance(
            timestamp,
            datetime,
        ):

            return int(
                timestamp.timestamp()
                * 1000
            )

        if isinstance(
            timestamp,
            date,
        ):

            value = datetime.combine(
                timestamp,
                datetime.min.time(),
            )

            return int(
                value.timestamp()
                * 1000
            )

        if isinstance(
            timestamp,
            (int, float),
        ):

            return int(
                timestamp
            )

        raise TypeError(
            "Unsupported timestamp type: "
            f"{type(timestamp)!r}"
        )

    @staticmethod
    def _timestamp_to_datetime(
        timestamp: int,
    ) -> datetime:

        return datetime.fromtimestamp(
            int(timestamp) / 1000
        )

    @staticmethod
    def _datetime_to_timestamp(
        value: datetime,
    ) -> int:

        return int(
            value.timestamp()
            * 1000
        )

    # ======================================================
    # Calendar helpers
    # ======================================================

    @staticmethod
    def _next_month(
        value: date,
    ) -> date:

        if value.month == 12:

            return date(
                value.year + 1,
                1,
                1,
            )

        return date(
            value.year,
            value.month + 1,
            1,
        )

    # ======================================================
    # HOLD
    # ======================================================

    @staticmethod
    def _hold(
        context: StrategyContext,
        *,
        observation_date: date | None = None,
        current_value: float | None = None,
    ) -> Signal:

        metadata = {
            "strategy": IceCreamSalesStrategy.name,
            "external_dataset": (
                "FRED:IPN31152N"
            ),
            "external_regime": "WARMUP",
        }

        if observation_date is not None:

            metadata[
                "external_observation_date"
            ] = observation_date.isoformat()

        if current_value is not None:

            metadata[
                "external_value"
            ] = current_value

        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=SignalAction.HOLD,
            quantity=0.0,
            sizing=PositionSizing.PERCENT_EQUITY,
            confidence=0.0,
            metadata=metadata,
        )

    # ======================================================
    # Reset
    # ======================================================

    def reset(self) -> None:

        self._consumed_signal_timestamps.clear()
