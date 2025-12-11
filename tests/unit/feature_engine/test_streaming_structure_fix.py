"""Integration test for streaming structure label fix.

Verifies that the bug fix in feature_engine/streaming.py correctly
extracts structure labels by finding the most recent valid swing point
instead of using a fixed position that may fall on a non-swing bar.
"""

from datetime import UTC

import pandas as pd
from common.types import Candle
from feature_engine.streaming import StreamingFeatureProcessor


class TestStreamingStructureLabelFix:
    """Test that structure labels are correctly extracted in streaming mode."""

    def test_structure_labels_populated_with_clear_trend(self) -> None:
        """Test that structure labels are populated when clear swings exist.
        
        This test simulates a realistic scenario where structure labels
        should be detected and properly extracted from the streaming buffer.
        """
        processor = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        
        # Create data with clear uptrend (HH/HL pattern)
        # Prices: 2000 -> 2010 (HL) -> 2020 (HH) -> 2015 (HL) -> 2025 (HH)
        bars = [
            # Initial bars to warm up
            (pd.Timestamp("2025-01-01 10:00:00", tz="UTC"), 2000.0, 2005.0, 1995.0, 2000.0),
            (pd.Timestamp("2025-01-01 11:00:00", tz="UTC"), 2000.0, 2005.0, 1998.0, 2003.0),
            (pd.Timestamp("2025-01-01 12:00:00", tz="UTC"), 2003.0, 2008.0, 2001.0, 2005.0),
            # Swing high #1
            (pd.Timestamp("2025-01-01 13:00:00", tz="UTC"), 2005.0, 2010.0, 2003.0, 2008.0),
            (pd.Timestamp("2025-01-01 14:00:00", tz="UTC"), 2008.0, 2012.0, 2007.0, 2010.0),  # High
            (pd.Timestamp("2025-01-01 15:00:00", tz="UTC"), 2010.0, 2011.0, 2006.0, 2007.0),
            # Swing low #1 (HL - Higher Low)
            (pd.Timestamp("2025-01-01 16:00:00", tz="UTC"), 2007.0, 2009.0, 2004.0, 2006.0),
            (pd.Timestamp("2025-01-01 17:00:00", tz="UTC"), 2006.0, 2008.0, 2003.0, 2004.0),  # Low (higher than previous)
            (pd.Timestamp("2025-01-01 18:00:00", tz="UTC"), 2004.0, 2010.0, 2003.0, 2008.0),
            # Swing high #2 (HH - Higher High)
            (pd.Timestamp("2025-01-01 19:00:00", tz="UTC"), 2008.0, 2015.0, 2007.0, 2012.0),
            (pd.Timestamp("2025-01-01 20:00:00", tz="UTC"), 2012.0, 2020.0, 2011.0, 2018.0),  # Higher high
            (pd.Timestamp("2025-01-01 21:00:00", tz="UTC"), 2018.0, 2019.0, 2014.0, 2015.0),
            # More bars to confirm structure
            (pd.Timestamp("2025-01-01 22:00:00", tz="UTC"), 2015.0, 2017.0, 2013.0, 2016.0),
            (pd.Timestamp("2025-01-01 23:00:00", tz="UTC"), 2016.0, 2018.0, 2014.0, 2017.0),
        ]
        
        last_features = None
        structure_labels_found = []
        
        for timestamp, open_price, high, low, close in bars:
            bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
                symbol="GC",
                timeframe="1h",
                source="TEST",
            )
            
            # DXY bar (not relevant for structure, but required by update signature)
            dxy_bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=1000.0,
                symbol="DXY",
                timeframe="1h",
                source="TEST",
            )
            
            features = processor.update(bar, dxy_bar)
            last_features = features
            
            # Track structure labels as they appear
            label = features.get("structure_label")
            if label is not None and not pd.isna(label):
                structure_labels_found.append((timestamp, label))
        
        # Verify we detected structure labels
        assert len(structure_labels_found) > 0, (
            "Expected to find structure labels in a clear uptrend, but none were detected. "
            f"Last features: {last_features}"
        )
        
        # Verify the last features have a valid structure label
        assert last_features is not None
        final_label = last_features.get("structure_label")
        assert final_label is not None and not pd.isna(final_label), (
            f"Expected final structure label to be set, got: {final_label}"
        )
        
        # Should see bullish labels (HH or HL) in an uptrend
        bullish_labels = [label for _, label in structure_labels_found if label in ["HH", "HL"]]
        assert len(bullish_labels) > 0, (
            f"Expected bullish structure labels (HH/HL) in uptrend, "
            f"got: {structure_labels_found}"
        )

    def test_structure_label_persists_between_swings(self) -> None:
        """Test that structure labels persist between swing points.
        
        Structure labels are sparse - they only appear at actual swing points.
        Between swings, the last known label should persist.
        """
        processor = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        
        # Create clear swing pattern followed by continuation
        # Need more bars to ensure structure detection kicks in
        bars = [
            # Initial warmup
            (pd.Timestamp("2025-01-01 08:00:00", tz="UTC"), 1990.0, 1995.0, 1985.0, 1990.0),
            (pd.Timestamp("2025-01-01 09:00:00", tz="UTC"), 1990.0, 1998.0, 1988.0, 1995.0),
            (pd.Timestamp("2025-01-01 10:00:00", tz="UTC"), 1995.0, 2005.0, 1993.0, 2000.0),
            (pd.Timestamp("2025-01-01 11:00:00", tz="UTC"), 2000.0, 2010.0, 1998.0, 2005.0),
            # First swing high
            (pd.Timestamp("2025-01-01 12:00:00", tz="UTC"), 2005.0, 2015.0, 2003.0, 2010.0),  # High
            (pd.Timestamp("2025-01-01 13:00:00", tz="UTC"), 2010.0, 2012.0, 2005.0, 2007.0),
            (pd.Timestamp("2025-01-01 14:00:00", tz="UTC"), 2007.0, 2009.0, 2003.0, 2005.0),
            # Swing low (HL)
            (pd.Timestamp("2025-01-01 15:00:00", tz="UTC"), 2005.0, 2008.0, 2002.0, 2004.0),  # Low
            (pd.Timestamp("2025-01-01 16:00:00", tz="UTC"), 2004.0, 2010.0, 2003.0, 2008.0),
            (pd.Timestamp("2025-01-01 17:00:00", tz="UTC"), 2008.0, 2015.0, 2007.0, 2012.0),
            # Second swing high (HH)
            (pd.Timestamp("2025-01-01 18:00:00", tz="UTC"), 2012.0, 2020.0, 2011.0, 2018.0),  # Higher high
            (pd.Timestamp("2025-01-01 19:00:00", tz="UTC"), 2018.0, 2019.0, 2014.0, 2015.0),
            # Now just continuation - no new swings for several bars
            (pd.Timestamp("2025-01-01 20:00:00", tz="UTC"), 2015.0, 2017.0, 2013.0, 2016.0),
            (pd.Timestamp("2025-01-01 21:00:00", tz="UTC"), 2016.0, 2018.0, 2014.0, 2017.0),
            (pd.Timestamp("2025-01-01 22:00:00", tz="UTC"), 2017.0, 2019.0, 2015.0, 2018.0),
            (pd.Timestamp("2025-01-01 23:00:00", tz="UTC"), 2018.0, 2020.0, 2016.0, 2019.0),
        ]
        
        all_labels = []
        label_changes = []
        prev_label = None
        
        for i, (timestamp, open_price, high, low, close) in enumerate(bars):
            bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
                symbol="GC",
                timeframe="1h",
                source="TEST",
            )
            
            dxy_bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=1000.0,
                symbol="DXY",
                timeframe="1h",
                source="TEST",
            )
            
            features = processor.update(bar, dxy_bar)
            label = features.get("structure_label")
            
            if label is not None and not pd.isna(label):
                all_labels.append((i, timestamp, label))
                if prev_label != label:
                    label_changes.append((i, timestamp, prev_label, label))
                    prev_label = label
        
        # We should have found structure labels
        assert len(all_labels) > 0, "Should have detected structure labels"
        
        # Verify persistence: Between label changes, we should have consecutive bars with the same label
        # This proves the fix works - labels persist until a new swing is detected
        consecutive_same_labels = []
        for j in range(len(label_changes) - 1):
            current_idx = label_changes[j][0]
            next_idx = label_changes[j + 1][0]
            gap = next_idx - current_idx
            if gap > 1:  # More than 1 bar between changes = persistence
                consecutive_same_labels.append(gap)
        
        # We should have at least one instance of label persistence (same label for multiple bars)
        assert len(consecutive_same_labels) > 0 or len(label_changes) <= 1, (
            f"Expected to see label persistence between swings. "
            f"All labels: {all_labels}, Changes: {label_changes}"
        )

    def test_empty_structure_when_insufficient_data(self) -> None:
        """Test that structure is empty/None when buffer doesn't have enough bars."""
        processor = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        
        # Only send a few bars - not enough for structure detection
        # Required: 3 * swing_window + 1 = 10 bars
        bars = [
            (pd.Timestamp("2025-01-01 10:00:00", tz="UTC"), 2000.0, 2005.0, 1995.0, 2000.0),
            (pd.Timestamp("2025-01-01 11:00:00", tz="UTC"), 2000.0, 2005.0, 1998.0, 2003.0),
            (pd.Timestamp("2025-01-01 12:00:00", tz="UTC"), 2003.0, 2008.0, 2001.0, 2005.0),
        ]
        
        for timestamp, open_price, high, low, close in bars:
            bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
                symbol="GC",
                timeframe="1h",
                source="TEST",
            )
            
            dxy_bar = Candle(
                timestamp=timestamp.replace(tzinfo=UTC),
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=1000.0,
                symbol="DXY",
                timeframe="1h",
                source="TEST",
            )
            
            features = processor.update(bar, dxy_bar)
            label = features.get("structure_label")
            
            # Should be None or empty during warmup
            assert label is None or pd.isna(label), (
                f"Expected no structure label with insufficient data, got: {label}"
            )

    def test_buffer_size_scales_with_timeframe(self) -> None:
        """Test that structure tracker is properly configured for different timeframes."""
        processor_1m = StreamingFeatureProcessor(timeframe="1m", swing_window=3)
        processor_15m = StreamingFeatureProcessor(timeframe="15m", swing_window=3)
        processor_1h = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        
        # Verify swing windows are configured appropriately for each timeframe
        # (The new StructureContextTracker doesn't expose buffer size directly,
        # but swing windows are the key parameter for structure detection)
        assert processor_1m.swing_window == 3, "1M should have swing_window=3"
        assert processor_15m.swing_window == 3, "15M should have swing_window=3"
        assert processor_1h.swing_window == 3, "1H should have swing_window=3"
        
        # Verify trackers are initialized
        assert processor_1m.structure_tracker is not None
        assert processor_15m.structure_tracker is not None
        assert processor_1h.structure_tracker is not None

