"""Configuration for Bot Core service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class BotCoreConfig(BaseServiceConfig):
    """Bot Core service configuration."""

    service_name: str = Field(default="bot-core")
    service_version: str = Field(default="0.1.0")

