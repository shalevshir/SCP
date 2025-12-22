"""Configuration for HTF Bias service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class HTFBiasConfig(BaseServiceConfig):
    """HTF Bias service configuration."""

    service_name: str = Field(default="htf-bias")
    service_version: str = Field(default="0.1.0")

