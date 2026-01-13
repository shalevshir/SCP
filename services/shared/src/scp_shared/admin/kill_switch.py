"""Kill switch repository for emergency trading halt."""

from datetime import datetime

from pydantic import BaseModel

from scp_shared.common.logger import get_logger
from scp_shared.database.connection import DatabasePool

logger = get_logger(__name__)


class KillSwitchState(BaseModel):
    """Kill switch state model."""
    
    service_name: str
    is_killed: bool
    killed_at: datetime | None = None
    killed_by: str | None = None
    reason: str | None = None
    updated_at: datetime


class KillSwitchRepository:
    """Repository for managing kill switch state.
    
    Provides emergency halt capability with database persistence
    to survive service restarts.
    
    Example:
        >>> repo = KillSwitchRepository(db_pool)
        >>> await repo.set_killed("execution", "admin", "Testing kill switch")
        >>> state = await repo.get_state("execution")
        >>> print(state.is_killed)  # True
        >>> await repo.set_resumed("execution")
    """
    
    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize repository.
        
        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool
    
    async def get_state(self, service_name: str) -> KillSwitchState:
        """Get current kill switch state for a service.
        
        Args:
            service_name: Service name ("bot-core" or "execution")
            
        Returns:
            Current kill switch state
            
        Raises:
            ValueError: If service not found in database
        """
        query = """
            SELECT service_name, is_killed, killed_at, killed_by, reason, updated_at
            FROM kill_switch_state
            WHERE service_name = $1
        """
        row = await self.db.fetchrow(query, service_name)
        
        if row is None:
            raise ValueError(f"Kill switch state not found for service: {service_name}")
        
        return KillSwitchState(
            service_name=row["service_name"],
            is_killed=row["is_killed"],
            killed_at=row["killed_at"],
            killed_by=row["killed_by"],
            reason=row["reason"],
            updated_at=row["updated_at"],
        )
    
    async def set_killed(
        self,
        service_name: str,
        killed_by: str = "admin",
        reason: str | None = None,
    ) -> None:
        """Activate kill switch for a service.
        
        Args:
            service_name: Service name ("bot-core" or "execution")
            killed_by: Who activated the kill switch
            reason: Optional reason for activation
        """
        query = """
            UPDATE kill_switch_state
            SET is_killed = TRUE,
                killed_at = NOW(),
                killed_by = $2,
                reason = $3
            WHERE service_name = $1
        """
        await self.db.execute(query, service_name, killed_by, reason)
        
        logger.warning(
            f"🚨 KILL SWITCH ACTIVATED for {service_name} "
            f"by {killed_by}: {reason or 'No reason provided'}"
        )
    
    async def set_resumed(self, service_name: str) -> None:
        """Deactivate kill switch for a service.
        
        Args:
            service_name: Service name ("bot-core" or "execution")
        """
        query = """
            UPDATE kill_switch_state
            SET is_killed = FALSE,
                killed_at = NULL,
                killed_by = NULL,
                reason = NULL
            WHERE service_name = $1
        """
        await self.db.execute(query, service_name)
        
        logger.info(f"✅ Kill switch DEACTIVATED for {service_name}")
