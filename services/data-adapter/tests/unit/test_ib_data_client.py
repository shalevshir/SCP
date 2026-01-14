"""Unit tests for IBDataClient."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from data_adapter.databento_client import Tick
from data_adapter.ib_data_client import IBDataClient, ResilientIBDataClient


class MockTicker:
    """Mock ib_insync Ticker object."""
    
    def __init__(self, last: float = 2650.0, last_size: float = 10.0):
        self.last = last
        self.lastSize = last_size
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
    """Test tick callback processing."""
    client = IBDataClient("127.0.0.1", 4002, 10)
    
    # Create mock ticker
    ticker = MockTicker(last=2650.5, last_size=10.0)
    
    # Process tick
    client._on_tick(ticker, "GC")
    
    # Verify tick was added to queue
    assert not client._tick_queue.empty()
    tick = await client._tick_queue.get()
    
    assert tick.symbol == "GC"
    assert tick.price == 2650.5
    assert tick.volume == 10.0
    assert isinstance(tick.timestamp, datetime)


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
