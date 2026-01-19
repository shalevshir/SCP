"""Unit tests for Data Adapter metrics."""

from datetime import UTC, datetime

from data_adapter import metrics


class TestTickTimestampTracking:
    """Test tick timestamp tracking for lag calculation."""
    
    def test_update_tick_timestamp(self):
        """Test updating tick timestamp for lag calculation."""
        symbol = "GC"
        timestamp = datetime(2025, 1, 18, 12, 30, tzinfo=UTC)
        
        # Update timestamp
        metrics.update_tick_timestamp(symbol, timestamp)
        
        # Verify timestamp is stored
        assert symbol in metrics._last_tick_timestamps
        assert metrics._last_tick_timestamps[symbol] == timestamp
    
    def test_update_lag_metrics(self):
        """Test lag metric calculation."""
        mode = "test"
        service = "data-adapter"
        symbol = "GC"
        
        # Set a tick timestamp 5 seconds in the past
        tick_time = datetime(2025, 1, 18, 12, 30, 0, tzinfo=UTC)
        metrics.update_tick_timestamp(symbol, tick_time)
        
        # Calculate lag
        current_time = datetime(2025, 1, 18, 12, 30, 5, tzinfo=UTC)
        metrics.update_lag_metrics(current_time, mode, service)
        
        # Verify lag is 5 seconds
        lag_value = metrics.market_data_lag_seconds.labels(
            mode=mode, service=service, symbol=symbol
        )._value.get()
        assert lag_value == 5.0
    
    def test_update_lag_metrics_multiple_symbols(self):
        """Test lag metrics for multiple symbols."""
        mode = "test"
        service = "data-adapter"
        
        # Set different tick timestamps for each symbol
        gc_time = datetime(2025, 1, 18, 12, 30, 0, tzinfo=UTC)
        dxy_time = datetime(2025, 1, 18, 12, 30, 2, tzinfo=UTC)
        
        metrics.update_tick_timestamp("GC", gc_time)
        metrics.update_tick_timestamp("DXY", dxy_time)
        
        # Calculate lag at a later time
        current_time = datetime(2025, 1, 18, 12, 30, 10, tzinfo=UTC)
        metrics.update_lag_metrics(current_time, mode, service)
        
        # Verify GC lag is 10 seconds
        gc_lag = metrics.market_data_lag_seconds.labels(
            mode=mode, service=service, symbol="GC"
        )._value.get()
        assert gc_lag == 10.0
        
        # Verify DXY lag is 8 seconds
        dxy_lag = metrics.market_data_lag_seconds.labels(
            mode=mode, service=service, symbol="DXY"
        )._value.get()
        assert dxy_lag == 8.0
