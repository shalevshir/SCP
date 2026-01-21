"""Data normalization utilities for candle data streams.

This module provides the DataNormalizer class for validating, sorting,
and logging anomalies in candle data.
"""

from collections import defaultdict

from common.logger import get_logger
from common.types import Candle

logger = get_logger(__name__)


class DataNormalizer:
    """Normalizes candle data by sorting, validating, and logging anomalies.

    The DataNormalizer ensures that candle data streams are:
    - Sorted by timestamp in ascending order
    - Free from anomalies (with warnings logged)
    - Valid according to Candle schema rules

    Example:
        >>> normalizer = DataNormalizer()
        >>> candles = [candle2, candle1, candle3]  # Out of order
        >>> sorted_candles = normalizer.normalize(candles)
        >>> # Returns candles sorted by timestamp, logs warning about order
    """

    def __init__(self) -> None:
        """Initialize the DataNormalizer."""
        pass

    def normalize(self, candles: list[Candle]) -> list[Candle]:
        """Normalize a list of candles by sorting and logging anomalies.

        Args:
            candles: List of Candle objects to normalize

        Returns:
            New list of Candle objects sorted by timestamp (ascending).
            The input list is not modified.

        The method performs the following operations:
        1. Returns empty list if input is empty
        2. Sorts candles by timestamp (ascending order)
        3. Logs warning if input was not already sorted
        4. Detects and logs duplicate timestamps (same timestamp + symbol)
        5. Returns the sorted list

        Note:
            - Candle validation is already enforced by the Candle dataclass
            - Same timestamp with different symbols is allowed
            - All logging is at WARNING level
        """
        # Handle empty list
        if not candles:
            return []

        # Check if input is already sorted
        is_sorted = all(
            candles[i].timestamp <= candles[i + 1].timestamp
            for i in range(len(candles) - 1)
        )

        # Sort candles by timestamp
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        # Log warning if input was out of order
        if not is_sorted and len(candles) > 1:
            logger.warning(
                "Input candles were out of order. "
                f"Sorted {len(candles)} candles by timestamp."
            )

        # Detect duplicates (same timestamp + symbol)
        self._detect_duplicates(sorted_candles)

        return sorted_candles

    def _detect_duplicates(self, candles: list[Candle]) -> None:
        """Detect and log duplicate candles (same timestamp + symbol).

        Args:
            candles: List of candles to check for duplicates

        Duplicates are defined as candles with the same timestamp and symbol.
        Different symbols at the same timestamp are allowed.
        """
        # Track occurrences of (timestamp, symbol) pairs
        timestamp_symbol_counts: dict[tuple[object, str], int] = defaultdict(int)

        for candle in candles:
            key = (candle.timestamp, candle.symbol)
            timestamp_symbol_counts[key] += 1

        # Log duplicates
        for (timestamp, symbol), count in timestamp_symbol_counts.items():
            if count > 1:
                logger.warning(
                    f"Found {count} duplicate candles for symbol '{symbol}' "
                    f"at timestamp {timestamp}"
                )
