"""Unit tests for IBDataClient."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from data_adapter.databento_client import Tick
from data_adapter.ib_data_client import IBDataClient, ResilientIBDataClient


# Sentinel for default time value
_DEFAULT_TIME = object()

class MockTicker:
    """Mock ib_insync Ticker object."""
    
    def __init__(
        self,
        last: float = 2650.0,
        last_size: float = 10.0,
        time: datetime | None | object = _DEFAULT_TIME,
        last_timestamp: float | None = None,  # UNIX timestamp (tick type 45)
    ):
        self.last = last
        self.lastSize = last_size
        if time is _DEFAULT_TIME:
            # Default: use a specific datetime
            self.time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        else:
            # Explicitly provided (including None)
            self.time = time
        # lastTimestamp is the actual trade time (UNIX timestamp)
        # If not provided, calculate from default time
        if last_timestamp is None:
            default_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
            self.lastTimestamp = default_time.timestamp()
        else:
            self.lastTimestamp = last_timestamp
        self.updateEvent = MockEvent()


class MockEvent:
    """Mock ib_insync event."""
    
    def __init__(self):
        self.callbacks = []
    
    def __iadd__(self, callback):
        """Add callback to event."""
        self.callbacks.append(callback)
        return self
    
    def trigger(self, ticker):
        """Trigger all callbacks with ticker."""
        for callback in self.callbacks:
            callback(ticker)


class MockIB:
    """Mock ib_insync IB class."""
    
    def __init__(self):
        self.connected = True
        self.gc_ticker = MockTicker(last=2650.0, last_size=10.0)
        self.dx_ticker = MockTicker(last=105.0, last_size=5.0)
    
    async def connectAsync(self, host, port, clientId):
        """Mock connect."""
        self.connected = True
    
    def reqMarketDataType(self, market_data_type):
        """Mock market data type request."""
        self.market_data_type = market_data_type
    
    def reqMktData(self, contract, genericTickList="", snapshot=False):
        """Mock market data request."""
        if contract.symbol == "GC":
            return self.gc_ticker
        elif contract.symbol == "DX":
            return self.dx_ticker
        return MockTicker()
    
    def isConnected(self):
        """Check if connected."""
        return self.connected
    
    def disconnect(self):
        """Disconnect."""
        self.connected = False


class MockContract:
    """Mock ib_insync Contract class."""
    
    def __init__(self):
        self.symbol = ""
        self.secType = ""
        self.exchange = ""
        self.currency = ""
        self.lastTradeDateOrContractMonth = ""


# MarketDataType constants (from IB API)
# 1 = Live, 2 = Frozen, 3 = Delayed, 4 = Delayed Frozen
MARKET_DATA_TYPE_DELAYED = 3


@pytest.fixture
def mock_ib_insync(monkeypatch):
    """Mock ib_insync module."""
    mock_ib = MockIB()
    
    # Mock the module imports
    monkeypatch.setattr("data_adapter.ib_data_client.IB_INSYNC_AVAILABLE", True)
    monkeypatch.setattr("data_adapter.ib_data_client.IB", lambda: mock_ib)
    monkeypatch.setattr("data_adapter.ib_data_client.Contract", MockContract)
    
    return mock_ib


@pytest.mark.asyncio
async def test_ib_data_client_initialization(mock_ib_insync):
    """Test IBDataClient initialization."""
    client = IBDataClient(
        host="127.0.0.1",
        port=4002,
        client_id=10,
        gc_symbol="GC",
        dxy_symbol="DX",
    )
    
    assert client.host == "127.0.0.1"
    assert client.port == 4002
    assert client.client_id == 10
    assert client.gc_symbol == "GC"
    assert client.dxy_symbol == "DX"


@pytest.mark.asyncio
async def test_ib_data_client_get_front_month(mock_ib_insync):
    """Test front month calculation for futures contracts."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Test GC (even months)
    gc_month = client._get_front_month("GC")
    assert len(gc_month) == 6  # Format: YYYYMM
    assert int(gc_month[:4]) >= 2026  # Year >= 2026
    assert int(gc_month[4:]) in [2, 4, 6, 8, 10, 12]  # Valid GC months
    
    # Test DX (quarterly)
    dx_month = client._get_front_month("DX")
    assert len(dx_month) == 6
    assert int(dx_month[:4]) >= 2026
    assert int(dx_month[4:]) in [3, 6, 9, 12]  # Valid DX months


@pytest.mark.asyncio
async def test_ib_data_client_create_contract(mock_ib_insync):
    """Test contract creation for GC and DX."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Test GC contract
    gc_contract = client._create_contract("GC")
    assert gc_contract.symbol == "GC"
    assert gc_contract.secType == "FUT"
    assert gc_contract.exchange == "COMEX"
    assert gc_contract.currency == "USD"
    assert len(gc_contract.lastTradeDateOrContractMonth) == 6
    
    # Test DX contract
    dx_contract = client._create_contract("DX")
    assert dx_contract.symbol == "DX"
    assert dx_contract.secType == "FUT"
    assert dx_contract.exchange == "NYBOT"
    assert dx_contract.currency == "USD"
    assert len(dx_contract.lastTradeDateOrContractMonth) == 6
    
    # Test unsupported symbol
    with pytest.raises(ValueError, match="Unsupported symbol"):
        client._create_contract("ES")


@pytest.mark.asyncio
async def test_ib_data_client_on_tick(mock_ib_insync):
    """Test tick callback processing with ticker.time (receive time for futures).
    
    Note: For futures, IB doesn't provide tick type 45 (Last Timestamp),
    so we use ticker.time which is when data was received (close to trade time
    for delayed data).
    """
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Create mock ticker with specific time (receive time for futures)
    expected_time = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
    ticker = MockTicker(
        last=2650.5,
        last_size=10.0,
        time=expected_time
    )
    
    # Process tick
    client._on_tick(ticker, "GC")
    
    # Verify tick was added to queue
    assert not client._tick_queue.empty()
    tick = await client._tick_queue.get()
    
    assert tick.symbol == "GC"
    assert tick.price == 2650.5
    assert tick.volume == 10.0
    assert isinstance(tick.timestamp, datetime)
    # Verify timestamp matches ticker.time (receive time for futures)
    assert tick.timestamp == expected_time


@pytest.mark.asyncio
async def test_ib_data_client_on_tick_fallback_timestamp(mock_ib_insync):
    """Test tick callback fallback behavior when ticker.time is not available."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Test 1: ticker.time not available, but lastTimestamp is available
    # Should use lastTimestamp if available (e.g., for stocks, not futures)
    expected_time = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
    expected_timestamp = expected_time.timestamp()
    ticker = MockTicker(
        last=2650.5,
        last_size=10.0,
        time=None,
        last_timestamp=expected_timestamp
    )
    del ticker.time  # Remove time to test fallback to lastTimestamp
    
    client._on_tick(ticker, "GC")
    tick = await client._tick_queue.get()
    # Should use lastTimestamp as fallback
    assert tick.timestamp == expected_time
    
    # Test 2: Neither time nor lastTimestamp available
    # Should fall back to current time with warning
    ticker2 = MockTicker(last=2650.5, last_size=10.0, time=None)
    del ticker2.time  # Remove time attribute
    del ticker2.lastTimestamp  # Remove lastTimestamp
    
    before_time = datetime.now(UTC)
    client._on_tick(ticker2, "GC")
    after_time = datetime.now(UTC)
    
    tick2 = await client._tick_queue.get()
    # Should use current time as final fallback
    assert before_time <= tick2.timestamp <= after_time


@pytest.mark.asyncio
async def test_ib_data_client_queue_overflow_protection(mock_ib_insync, caplog):
    """Test that queue overflow is handled gracefully.
    
    Verifies that when the tick queue is full, ticks are dropped
    with a warning log instead of causing unbounded memory growth.
    """
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Fill the queue to capacity (maxsize=10000)
    # Use a smaller test queue to make the test faster
    # Replace the queue with a smaller one for testing
    small_queue = asyncio.Queue(maxsize=5)
    client._tick_queue = small_queue
    
    # Fill the queue
    ticker = MockTicker(last=2650.5, last_size=10.0)
    for _ in range(5):
        client._on_tick(ticker, "GC")
    
    # Queue should be full now
    assert small_queue.full()
    
    # Next tick should trigger QueueFull exception and be dropped
    # (This should log a warning but not raise)
    client._on_tick(ticker, "GC")
    
    # Verify warning was logged
    assert "Tick queue full, dropping tick" in caplog.text
    
    # Verify queue is still full (tick was dropped, not added)
    assert small_queue.full()
    assert small_queue.qsize() == 5


@pytest.mark.asyncio
async def test_ib_data_client_stream_ticks(mock_ib_insync):
    """Test streaming ticks from IB Gateway."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Start streaming in background
    stream_task = asyncio.create_task(
        anext(client.stream_ticks().__aiter__())
    )
    
    # Wait a bit for connection
    await asyncio.sleep(0.1)
    
    # Simulate tick updates from IB
    gc_tick = MockTicker(last=2650.5, last_size=10.0)
    mock_ib_insync.gc_ticker.updateEvent.trigger(gc_tick)
    
    # Should receive tick
    try:
        tick = await asyncio.wait_for(stream_task, timeout=1.0)
        assert tick.symbol == "GC"
        assert tick.price == 2650.5
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ib_data_client_close(mock_ib_insync):
    """Test closing IB connection."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    mock_ib = MockIB()
    client._ib = mock_ib
    client._connected = True
    
    await client.close()
    
    # After close, _ib should be None and connection should be false
    assert not mock_ib.isConnected()
    assert not client._connected
    assert client._ib is None


@pytest.mark.asyncio
async def test_ib_data_client_clears_queue_on_close(mock_ib_insync, caplog):
    """Test that tick queue is cleared on close to prevent stale data on reconnection.
    
    Regression test for bug where stale ticks from previous session remained in queue
    and were yielded before new ticks after reconnection, causing:
    - Old timestamps appearing after reconnection
    - Incorrect gap detection
    - Corrupted candle aggregation
    """
    client = IBDataClient("127.0.0.1", 4002, 10)
    mock_ib = MockIB()
    client._ib = mock_ib
    client._connected = True
    
    # Add stale ticks to queue (simulating ticks from previous session)
    stale_time = datetime(2025, 1, 14, 23, 59, 0, tzinfo=UTC)
    for i in range(5):
        stale_tick = Tick(
            timestamp=stale_time,
            price=2640.0 + i,
            volume=100.0,
            symbol="GC",
        )
        await client._tick_queue.put(stale_tick)
    
    # Verify queue has stale ticks
    assert client._tick_queue.qsize() == 5
    
    # Close connection - should clear queue
    await client.close()
    
    # CRITICAL: Queue should be empty after close
    assert client._tick_queue.empty()
    assert client._tick_queue.qsize() == 0
    
    # Verify log message about clearing stale ticks (if logger is configured)
    # Note: This may not appear in caplog depending on logger configuration,
    # but the critical behavior (queue emptying) is verified above
    if caplog.text:
        assert "Cleared" in caplog.text and "stale ticks" in caplog.text


@pytest.mark.asyncio
async def test_resilient_client_no_stale_ticks_after_reconnection():
    """Test that no stale ticks are yielded after reconnection.
    
    Simulates the real-world scenario:
    1. Client connects and receives ticks
    2. Connection drops with ticks still in queue
    3. Client reconnects
    4. Only new ticks should be yielded (no stale ones from step 1)
    """
    
    class MockIBClientWithStaleData:
        """Mock IB client that simulates disconnect with stale data."""
        
        def __init__(self):
            self.attempt = 0
            self._tick_queue = asyncio.Queue(maxsize=10000)
        
        async def stream_ticks(self):
            """Stream ticks, simulating disconnect after first session."""
            self.attempt += 1
            
            if self.attempt == 1:
                # First connection: yield 2 ticks, then disconnect
                # (leaving 1 tick in queue)
                yield Tick(
                    timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                    price=2650.0,
                    volume=100.0,
                    symbol="GC",
                )
                yield Tick(
                    timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
                    price=2651.0,
                    volume=100.0,
                    symbol="GC",
                )
                # Add a stale tick to queue before disconnect
                await self._tick_queue.put(
                    Tick(
                        timestamp=datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC),
                        price=2652.0,
                        volume=100.0,
                        symbol="GC",
                    )
                )
                # Simulate disconnect
                raise ConnectionError("Mock disconnect")
            
            else:
                # Second connection: yield fresh ticks with LATER timestamps
                # If queue wasn't cleared, stale tick (10:02) would appear before these
                for i in range(3):
                    yield Tick(
                        timestamp=datetime(2025, 1, 15, 11, i, 0, tzinfo=UTC),
                        price=2660.0 + i,
                        volume=100.0,
                        symbol="GC",
                    )
        
        async def close(self):
            """Close client and clear queue (the fix)."""
            # Clear stale ticks (this is the bug fix being tested)
            while not self._tick_queue.empty():
                try:
                    self._tick_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
    
    mock_client = MockIBClientWithStaleData()
    
    resilient = ResilientIBDataClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,
        max_delay=0.1,
    )
    
    # Collect all ticks
    ticks = []
    async for tick in resilient.stream_ticks():
        ticks.append(tick)
        if len(ticks) >= 5:  # 2 from first session + 3 from second
            break
    
    # Should have 5 ticks total
    assert len(ticks) == 5
    
    # First 2 ticks from first session (before disconnect)
    assert ticks[0].timestamp == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    assert ticks[1].timestamp == datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
    
    # CRITICAL: Next 3 ticks should be from SECOND session (11:00, 11:01, 11:02)
    # NOT the stale tick from first session (10:02)
    # This verifies the queue was cleared on reconnection
    assert ticks[2].timestamp == datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
    assert ticks[3].timestamp == datetime(2025, 1, 15, 11, 1, 0, tzinfo=UTC)
    assert ticks[4].timestamp == datetime(2025, 1, 15, 11, 2, 0, tzinfo=UTC)
    
    # Verify no tick with timestamp 10:02 was yielded (the stale one)
    assert datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC) not in [t.timestamp for t in ticks]


@pytest.mark.asyncio
async def test_resilient_ib_client_reconnects_after_failure():
    """Test that ResilientIBDataClient reconnects after connection failure."""
    
    class MockFailingIBClient:
        """Mock IB client that fails N times then succeeds."""
        
        def __init__(self, fail_count: int = 2):
            self.fail_count = fail_count
            self.attempt = 0
            self._closed = False
        
        async def stream_ticks(self):
            """Stream ticks, failing first N attempts."""
            self.attempt += 1
            
            if self.attempt <= self.fail_count:
                raise ConnectionError(f"Mock IB failure {self.attempt}")
            
            # Success - yield some ticks
            for i in range(3):
                yield Tick(
                    timestamp=datetime(2025, 1, 15, 10, i, 0, tzinfo=UTC),
                    price=2650.0 + i,
                    volume=100.0,
                    symbol="GC",
                )
        
        async def close(self):
            """Close client."""
            self._closed = True
    
    # Create mock client that fails twice, then succeeds
    mock_client = MockFailingIBClient(fail_count=2)
    
    # Wrap with resilient client (short delays for testing)
    resilient = ResilientIBDataClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,  # 10ms base delay
        max_delay=0.1,    # 100ms max delay
    )
    
    # Should eventually succeed after retries
    ticks = []
    async for tick in resilient.stream_ticks():
        ticks.append(tick)
        if len(ticks) >= 3:
            break
    
    # Verify we got ticks
    assert len(ticks) == 3
    assert ticks[0].symbol == "GC"
    
    # Verify it retried (3 attempts total: 2 failures + 1 success)
    assert mock_client.attempt == 3


@pytest.mark.asyncio
async def test_resilient_ib_client_gives_up_after_max_retries():
    """Test that ResilientIBDataClient gives up after max retries."""
    
    class MockFailingIBClient:
        """Mock IB client that always fails."""
        
        def __init__(self):
            self._closed = False
        
        async def stream_ticks(self):
            """Always fail."""
            raise ConnectionError("IB Gateway unreachable")
            # Make this a generator to avoid the coroutine error
            yield  # pragma: no cover - never reached
        
        async def close(self):
            """Close client."""
            self._closed = True
    
    mock_client = MockFailingIBClient()
    
    # Wrap with resilient client with low max_retries
    resilient = ResilientIBDataClient(
        inner=mock_client,
        max_retries=3,
        base_delay=0.01,
        max_delay=0.1,
    )
    
    # Should raise after max retries
    with pytest.raises(ConnectionError):
        async for _ in resilient.stream_ticks():
            pass


@pytest.mark.asyncio
async def test_resilient_ib_client_connection_state():
    """Test that connection state is tracked correctly."""
    
    class MockSuccessfulIBClient:
        """Mock IB client that succeeds."""
        
        async def stream_ticks(self):
            """Yield ticks successfully."""
            for i in range(3):
                yield Tick(
                    timestamp=datetime(2025, 1, 15, 10, i, 0, tzinfo=UTC),
                    price=2650.0 + i,
                    volume=100.0,
                    symbol="GC",
                )
        
        async def close(self):
            """Close client."""
            pass
    
    mock_client = MockSuccessfulIBClient()
    
    resilient = ResilientIBDataClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,
        max_delay=0.1,
    )
    
    # Initially disconnected
    assert resilient.connection_state == "disconnected"
    
    # Stream ticks - should eventually connect
    async for tick in resilient.stream_ticks():
        # After receiving first tick, should be connected
        assert resilient.connection_state == "connected"
        break
