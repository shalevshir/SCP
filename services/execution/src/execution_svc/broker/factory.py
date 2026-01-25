"""Broker factory for creating broker instances based on configuration."""

from scp_shared.common.logger import get_logger

from execution_svc.broker.base import BaseBroker
from execution_svc.broker.paper import PaperBroker
from execution_svc.config import ExecutionConfig

logger = get_logger(__name__)

# Lazy import - only import IBPaperBroker when ib_paper mode is requested
# This allows the factory to work even if ibapi is not installed
try:
    from execution_svc.broker.ib_paper import IBPaperBroker

    IB_PAPER_AVAILABLE = True
except ImportError:
    IB_PAPER_AVAILABLE = False
    IBPaperBroker = None  # type: ignore[assignment,misc]


def create_broker(mode: str, config: ExecutionConfig) -> BaseBroker:
    """Create broker instance based on mode.

    Args:
        mode: Broker mode:
            - "paper": In-memory paper trading (no real broker connection)
            - "ib_paper": Interactive Brokers paper trading account
            - "live": Live trading (not yet implemented)
        config: Execution service configuration

    Returns:
        Broker instance implementing BaseBroker interface

    Raises:
        ValueError: If broker mode is invalid or not supported

    Example:
        >>> config = ExecutionConfig(broker_mode="paper")
        >>> broker = create_broker(config.broker_mode, config)
        >>> result = await broker.place_order("GC", "long", 1, 2650.0)
    """
    if mode == "paper":
        logger.info("Creating PaperBroker (in-memory simulation)")
        return PaperBroker()

    elif mode == "ib_paper":
        if not IB_PAPER_AVAILABLE or IBPaperBroker is None:
            raise ImportError(
                "ibapi is not installed. Install it with: poetry add ibapi\n"
                "Or use BROKER_MODE=paper for in-memory simulation."
            )

        logger.info(
            f"Creating IBPaperBroker (IB paper trading at {config.ib_host}:{config.ib_port})"
        )
        return IBPaperBroker(
            host=config.ib_host,
            port=config.ib_port,
            client_id=config.ib_client_id,
        )

    elif mode == "live":
        raise ValueError(
            "Live trading mode is not yet implemented. "
            "Use 'paper' or 'ib_paper' for now."
        )

    else:
        raise ValueError(
            f"Invalid broker mode: '{mode}'. " "Supported modes: 'paper', 'ib_paper'"
        )
