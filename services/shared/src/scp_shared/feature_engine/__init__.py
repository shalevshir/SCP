"""Feature engine package for streaming feature computation."""

from scp_shared.feature_engine.streaming import StreamingFeatureProcessor
from scp_shared.feature_engine.state import FeatureState

__all__ = [
    "StreamingFeatureProcessor",
    "FeatureState",
]
