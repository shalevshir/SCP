"""Feature engine package for streaming feature computation."""

from scp_shared.indicators.streaming import StreamingFeatureProcessor
from scp_shared.indicators.state import FeatureState

__all__ = [
    "StreamingFeatureProcessor",
    "FeatureState",
]
