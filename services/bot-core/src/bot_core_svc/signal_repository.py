"""Signal repository for database persistence of all signals (approved and rejected)."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage
from scp_shared.rule_engine import Signal

logger = get_logger(__name__)


class SignalRepository:
    """Database repository for signal history persistence.

    Handles saving ALL signals (approved and rejected) with full diagnostic
    context for post-hoc analysis, debugging, and pattern discovery.

    Example:
        >>> repo = SignalRepository(db_pool)
        >>> signal_id = await repo.save_signal(
        ...     signal=signal,
        ...     features=features_msg,
        ...     htf_bias=bias_msg,
        ...     was_approved=True,
        ...     signal_message_id="uuid-here"
        ... )
    """

    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize signal repository.

        Args:
            db_pool: Database connection pool
        """
        self._db_pool = db_pool

    async def save_signal(
        self,
        signal: Signal,
        features: FeaturesMessage,
        htf_bias: HTFBiasMessage,
        was_approved: bool,
        rejection_stage: str | None = None,
        signal_message_id: str | None = None,
    ) -> str:
        """Persist signal with full diagnostic context.

        Saves ALL signals (approved and rejected) to signal_history table
        with complete input snapshots and scoring breakdown for analysis.

        Args:
            signal: Signal object from score_signal() with diagnostics
            features: FeaturesMessage used as input (for reproducibility)
            htf_bias: HTFBiasMessage used as input (for reproducibility)
            was_approved: True if A+ signal was published to execution
            rejection_stage: Rejection reason if rejected (e.g., "confidence_filter")
            signal_message_id: Published signal ID if approved (for linkage)

        Returns:
            Signal history ID (UUID string)
        """
        # Convert input messages to JSON-serializable dicts
        features_snapshot = self._serialize_features(features)
        htf_bias_snapshot = self._serialize_htf_bias(htf_bias)

        # Extract factor scores and diagnostics from signal
        factor_scores = signal.factors
        diagnostics = signal.diagnostics

        query = """
            INSERT INTO signal_history (
                timestamp, symbol, timeframe, direction, setup_type,
                score, confidence, was_approved, rejection_stage,
                features_snapshot, htf_bias_snapshot,
                factor_scores, diagnostics, signal_message_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """

        # Convert signal_message_id to UUID if provided
        signal_uuid = UUID(signal_message_id) if signal_message_id else None

        row = await self._db_pool.fetchrow(
            query,
            signal.timestamp,
            signal.symbol,
            signal.timeframe,
            signal.direction,
            signal.setup_type,
            signal.score,
            signal.confidence,
            was_approved,
            rejection_stage,
            json.dumps(features_snapshot),
            json.dumps(htf_bias_snapshot),
            json.dumps(factor_scores),
            json.dumps(diagnostics),
            signal_uuid,
        )

        signal_history_id = str(row["id"]) if row else None
        if signal_history_id is None:
            raise ValueError(f"Failed to insert signal history: {row}")

        # Log at appropriate level
        if was_approved:
            logger.info(
                f"Saved approved signal {signal_history_id}: {signal.direction} "
                f"{signal.setup_type} @ {signal.timestamp} (score: {signal.score:.1f})"
            )
        else:
            logger.debug(
                f"Saved rejected signal {signal_history_id}: {signal.direction} "
                f"{signal.setup_type} @ {signal.timestamp} "
                f"(score: {signal.score:.1f}, stage: {rejection_stage})"
            )

        return signal_history_id

    async def link_trade(self, signal_message_id: str, trade_id: str) -> None:
        """Link a signal to its resulting trade.

        Updates signal_history record with trade_id for complete audit trail.
        Called by execution service after trade is opened.

        Args:
            signal_message_id: Published signal ID
            trade_id: Trade ID from trades table
        """
        query = """
            UPDATE signal_history
            SET trade_id = $1
            WHERE signal_message_id = $2
        """

        await self._db_pool.execute(
            query,
            UUID(trade_id),
            UUID(signal_message_id),
        )

        logger.debug(f"Linked signal {signal_message_id} to trade {trade_id}")

    async def get_signals_for_period(
        self,
        start: datetime,
        end: datetime,
        was_approved: bool | None = None,
        setup_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query signal history for a time period.

        Args:
            start: Start timestamp (inclusive)
            end: End timestamp (exclusive)
            was_approved: Filter by approval status (None = all)
            setup_type: Filter by setup type (None = all)

        Returns:
            List of signal records with all fields
        """
        conditions = ["timestamp >= $1", "timestamp < $2"]
        params: list[Any] = [start, end]
        param_idx = 3

        if was_approved is not None:
            conditions.append(f"was_approved = ${param_idx}")
            params.append(was_approved)
            param_idx += 1

        if setup_type is not None:
            conditions.append(f"setup_type = ${param_idx}")
            params.append(setup_type)
            param_idx += 1

        query = f"""
            SELECT
                id, timestamp, symbol, timeframe, direction, setup_type,
                score, confidence, was_approved, rejection_stage,
                features_snapshot, htf_bias_snapshot,
                factor_scores, diagnostics,
                signal_message_id, trade_id, created_at
            FROM signal_history
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp ASC
        """

        rows = await self._db_pool.fetch(query, *params)

        signals = []
        for row in rows:
            signal_dict = {
                "id": str(row["id"]),
                "timestamp": row["timestamp"].isoformat(),
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "direction": row["direction"],
                "setup_type": row["setup_type"],
                "score": float(row["score"]),
                "confidence": row["confidence"],
                "was_approved": row["was_approved"],
                "rejection_stage": row["rejection_stage"],
                "features_snapshot": json.loads(row["features_snapshot"]),
                "htf_bias_snapshot": json.loads(row["htf_bias_snapshot"]),
                "factor_scores": json.loads(row["factor_scores"]),
                "diagnostics": json.loads(row["diagnostics"]),
                "signal_message_id": (
                    str(row["signal_message_id"]) if row["signal_message_id"] else None
                ),
                "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                "created_at": row["created_at"].isoformat(),
            }
            signals.append(signal_dict)

        logger.debug(
            f"Retrieved {len(signals)} signals for period "
            f"{start.isoformat()} to {end.isoformat()}"
        )

        return signals

    async def get_rejection_summary(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """Summarize rejection reasons for a time period.

        Args:
            start: Start timestamp (inclusive)
            end: End timestamp (exclusive)

        Returns:
            Dict mapping rejection_stage to count
        """
        query = """
            SELECT rejection_stage, COUNT(*) as count
            FROM signal_history
            WHERE timestamp >= $1
              AND timestamp < $2
              AND was_approved = FALSE
            GROUP BY rejection_stage
            ORDER BY count DESC
        """

        rows = await self._db_pool.fetch(query, start, end)

        summary = {row["rejection_stage"]: row["count"] for row in rows}

        logger.debug(
            f"Rejection summary for {start.isoformat()} to {end.isoformat()}: "
            f"{len(summary)} unique rejection stages"
        )

        return summary

    def _serialize_features(self, features: FeaturesMessage) -> dict[str, Any]:
        """Convert FeaturesMessage to JSON-serializable dict.

        Args:
            features: Features message

        Returns:
            Dictionary with all features (None values preserved)
        """
        # Use Pydantic's model_dump for proper serialization
        return features.model_dump(mode="json")

    def _serialize_htf_bias(self, htf_bias: HTFBiasMessage) -> dict[str, Any]:
        """Convert HTFBiasMessage to JSON-serializable dict.

        Args:
            htf_bias: HTF bias message

        Returns:
            Dictionary with all bias fields (None values preserved)
        """
        # Use Pydantic's model_dump for proper serialization
        return htf_bias.model_dump(mode="json")
