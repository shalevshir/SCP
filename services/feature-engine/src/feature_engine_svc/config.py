"""Configuration for Feature Engine service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class FeatureEngineConfig(BaseServiceConfig):
    """Feature Engine service configuration."""

    service_name: str = Field(default="feature-engine")
    service_version: str = Field(default="0.1.0")

