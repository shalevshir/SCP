"""Interactive Brokers historical data fetcher for gap backfill and warmup.

This module provides an IB Gateway historical data client using ib_insync
for fetching OHLCV bars.
"""

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta

from scp_shared.common import get_logger
from scp_shared.messaging.schemas import CandleMessage

logger = get_logger(__name__)

# Check if ib_insync is available
try:
    from ib_insync import IB, Contract

    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    # Create dummy classes for type checking when ib_insync is not available
    IB = None  # type: ignore
    Contract = None  # type: ignore


class IBHistoricalFetcher:
    """Fetches historical OHLCV data from IB Gateway for gap backfill and warmup.

    Uses a dedicated IB connection (separate from streaming client) to fetch
    historical bars without disrupting live data stream. Implements rate limiting
    to comply with IB's 60 requests per 10 minutes limit.

    Example:
        >>> fetcher = IBHistoricalFetcher("127.0.0.1", 4002, 11)
        >>> candles = await fetcher.fetch_candles(
        ...     symbol="GC",
        ...     start=datetime(2025, 1, 15, 8, 0, tzinfo=UTC),
        ...     end=datetime(2025, 1, 15, 12, 0, tzinfo=UTC),
        ...     timeframe="1m"
        ... )
        >>> len(candles)  # ~240 candles (4 hours * 60 minutes)
        240
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        market_data_type: int = 3,
    ) -> None:
        """Initialize IB historical fetcher.

        Args:
            host: IB Gateway/TWS host
            port: IB port (4002=Gateway paper, 7497=TWS paper)
            client_id: Unique client ID (should differ from streaming client)
            market_data_type: 1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen

        Raises:
            ImportError: If ib_insync is not installed
        """
        if not IB_INSYNC_AVAILABLE:
            raise ImportError(
                "ib_insync is not installed. Install it with: pip install ib-insync"
            )

        self.host = host
        self.port = port
        self.client_id = client_id
        self.market_data_type = market_data_type

        self._ib: IB | None = None

        # Rate limit tracking: 60 requests per 10 minutes
        self._request_timestamps: deque[datetime] = deque(maxlen=60)
        self._rate_limit_window = timedelta(minutes=10)
        self._max_requests = 60

    def _get_front_month(self, symbol: str) -> str:
        """Get the current front month contract for futures.

        Args:
            symbol: Futures symbol (GC or DX)

        Returns:
            Contract month string (e.g., "202602" for Feb 2026)

        Raises:
            ValueError: If symbol is not supported
        """
        now = datetime.now(UTC)
        year = now.year
        month = now.month

        if symbol == "GC":
            # GC trades in even months: Feb, Apr, Jun, Aug, Oct, Dec
            valid_months = [2, 4, 6, 8, 10, 12]
        elif symbol == "DX":
            # DX trades in Mar, Jun, Sep, Dec (quarterly)
            valid_months = [3, 6, 9, 12]
        else:
            raise ValueError(f"Unsupported symbol: {symbol}")

        # Find next valid month (current month + 1 to allow for rollover)
        target_month = month + 1

        for vm in valid_months:
            if vm >= target_month:
                return f"{year}{vm:02d}"

        # If no valid month this year, use first month next year
        return f"{year + 1}{valid_months[0]:02d}"

    def _create_contract(self, symbol: str) -> Contract:
        """Create IB contract for a symbol.

        Args:
            symbol: Internal symbol (GC or DX)

        Returns:
            ib_insync Contract object

        Raises:
            ValueError: If symbol is not supported
        """
        if symbol == "GC":
            contract = Contract()
            contract.symbol = "GC"
            contract.secType = "FUT"
            contract.exchange = "COMEX"
            contract.currency = "USD"
            contract.lastTradeDateOrContractMonth = self._get_front_month("GC")
            return contract
        elif symbol == "DX":
            contract = Contract()
            contract.symbol = "DX"
            contract.secType = "FUT"
            contract.exchange = "NYBOT"
            contract.currency = "USD"
            contract.lastTradeDateOrContractMonth = self._get_front_month("DX")
            return contract
        else:
            raise ValueError(f"Unsupported symbol: {symbol}. Use GC or DX.")

    def _map_timeframe_to_bar_size(self, timeframe: str) -> str:
        """Map internal timeframe to IB barSizeSetting.

        Args:
            timeframe: Internal timeframe string (1m, 5m, 15m, 1h)

        Returns:
            IB bar size string

        Raises:
            ValueError: If timeframe is not supported
        """
        mapping = {
            "1m": "1 min",
            "5m": "5 mins",
            "15m": "15 mins",
            "1h": "1 hour",
            "1d": "1 day",
        }

        if timeframe not in mapping:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Supported: {list(mapping.keys())}"
            )

        return mapping[timeframe]

    def _calculate_duration(self, start: datetime, end: datetime) -> str:
        """Calculate IB duration string from time range.

        IB duration format: "<amount> <unit>" where unit is S|D|W|M|Y
        Examples: "14400 S" (4 hours in seconds), "5 D"

        Args:
            start: Start datetime
            end: End datetime

        Returns:
            IB duration string

        Notes:
            IB API requires duration in seconds for intraday data.
            For multi-day requests, uses days.
        """
        duration_seconds = int((end - start).total_seconds())

        # For short durations (< 24h), use seconds
        if duration_seconds < 86400:
            return f"{duration_seconds} S"

        # For longer durations, use days (round up to cover partial days)
        days = (duration_seconds + 86399) // 86400
        return f"{days} D"

    async def _ensure_connected(self) -> None:
        """Ensure connected to IB Gateway with retry logic.

        Raises:
            ConnectionError: If cannot connect after max retries
        """
        if self._ib and self._ib.isConnected():
            return

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._ib = IB()
                await self._ib.connectAsync(
                    self.host, self.port, clientId=self.client_id
                )
                self._ib.reqMarketDataType(self.market_data_type)
                logger.info(
                    f"Connected to IB Gateway for historical data "
                    f"(client_id={self.client_id})"
                )
                return
            except Exception as e:
                if self._ib:
                    try:
                        if self._ib.isConnected():
                            self._ib.disconnect()
                    except Exception as disconnect_error:
                        logger.warning(
                            "Failed to disconnect IB after connection error: "
                            f"{disconnect_error}"
                        )
                    finally:
                        self._ib = None
                if attempt == max_retries - 1:
                    raise ConnectionError(
                        f"Failed to connect to IB Gateway after "
                        f"{max_retries} attempts: {e}"
                    ) from e
                wait = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Connection attempt {attempt + 1}/{max_retries} failed: {e}. "
                    f"Retrying in {wait}s"
                )
                await asyncio.sleep(wait)

    async def _check_rate_limit(self) -> None:
        """Check rate limit and wait if necessary.

        IB allows 60 historical data requests per 10 minutes.
        If we've made 60 requests in the last 10 minutes, wait until
        the oldest request ages out.
        """
        now = datetime.now(UTC)

        # Remove timestamps older than 10 minutes
        while (
            self._request_timestamps
            and (now - self._request_timestamps[0]) > self._rate_limit_window
        ):
            self._request_timestamps.popleft()

        # If we've hit the limit, wait
        if len(self._request_timestamps) >= self._max_requests:
            oldest = self._request_timestamps[0]
            wait_until = oldest + self._rate_limit_window
            wait_seconds = (wait_until - now).total_seconds() + 1  # +1 for safety

            if wait_seconds > 0:
                rate_window_min = self._rate_limit_window.seconds // 60
                logger.warning(
                    f"IB rate limit reached ({self._max_requests} req/"
                    f"{rate_window_min}min). Waiting {wait_seconds:.1f}s"
                )
                await asyncio.sleep(wait_seconds)

        # Record this request with current time (after potential wait)
        self._request_timestamps.append(datetime.now(UTC))

    def _bar_to_candle_message(
        self, bar, symbol: str, timeframe: str
    ) -> CandleMessage:
        """Convert IB BarData to CandleMessage.

        Args:
            bar: ib_insync BarData object
            symbol: Internal symbol (GC or DXY)
            timeframe: Internal timeframe string

        Returns:
            CandleMessage instance

        Notes:
            With formatDate=2, IB returns timezone-aware datetime objects in UTC.
            This avoids timezone ambiguity (formatDate=1 returns TWS local timezone).
        """
        # IB with formatDate=2 returns UTC-aware datetimes
        timestamp = bar.date
        
        # Ensure timestamp is in UTC (should already be with formatDate=2)
        if timestamp.tzinfo is None:
            # This shouldn't happen with formatDate=2, but handle defensively
            logger.warning(
                f"Received naive datetime from IB (expected UTC with formatDate=2): {timestamp}"
            )
            timestamp = timestamp.replace(tzinfo=UTC)
        elif timestamp.tzinfo != UTC:
            # Convert to UTC if in different timezone
            timestamp = timestamp.astimezone(UTC)

        return CandleMessage(
            timestamp=timestamp,
            symbol=symbol,
            timeframe=timeframe,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
        )

    async def fetch_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> list[CandleMessage]:
        """Fetch historical OHLCV candles from IB Gateway.

        Args:
            symbol: Internal symbol (GC or DXY)
            start: Start datetime (inclusive, UTC)
            end: End datetime (exclusive, UTC)
            timeframe: Timeframe (1m, 5m, 15m, 1h)

        Returns:
            List of CandleMessage objects, sorted by timestamp ascending

        Raises:
            ValueError: If symbol not supported or timeframe invalid

        Notes:
            - Respects IB rate limit (60 requests per 10 minutes)
            - Automatically waits if rate limit would be exceeded
            - Uses delayed market data by default (market_data_type=3)
            - Maximum lookback depends on IB subscription (typically 1 year for 1m bars)
        """
        # Normalize symbol (DXY -> DX for IB)
        ib_symbol = "DX" if symbol == "DXY" else symbol

        try:
            await self._ensure_connected()
            await self._check_rate_limit()

            contract = self._create_contract(ib_symbol)
            bar_size = self._map_timeframe_to_bar_size(timeframe)
            duration = self._calculate_duration(start, end)

            logger.info(
                f"Fetching historical data for {symbol} "
                f"from {start.isoformat()} to {end.isoformat()} "
                f"(duration={duration}, bar_size={bar_size})"
            )

            # Request historical data
            bars = await self._ib.reqHistoricalDataAsync(
                contract=contract,
                endDateTime=end,
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=False,  # Include all hours (RTH + ETH)
                formatDate=2,  # Return as UTC timezone-aware datetime objects
            )

            if not bars:
                logger.warning(
                    f"No historical data returned for {symbol} {start}-{end}"
                )
                return []

            # Convert to CandleMessage
            candles = [
                self._bar_to_candle_message(bar, symbol, timeframe) for bar in bars
            ]

            # Filter to exact range (IB may return extra bars)
            candles = [c for c in candles if start <= c.timestamp < end]

            logger.info(f"Fetched {len(candles)} historical candles for {symbol}")
            return candles

        except ValueError:
            # Invalid input - don't retry
            raise
        except Exception as e:
            logger.error(
                f"Error fetching historical data for {symbol}: {e}", exc_info=True
            )
            # Return empty list instead of raising (gap detector expects this)
            return []

    async def close(self) -> None:
        """Disconnect from IB Gateway."""
        if self._ib and self._ib.isConnected():
            logger.info("Closing IB Gateway historical connection")
            self._ib.disconnect()
            self._ib = None
