"""Database query helpers for loading features and signal history data."""

import asyncpg
import pandas as pd
from datetime import datetime
from typing import Any


async def load_features(
    db_url: str,
    start_date: str,
    end_date: str,
    symbol: str = "GC",
    timeframe: str = "1m",
) -> pd.DataFrame:
    """
    Load features data from the database.

    Args:
        db_url: PostgreSQL connection URL
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        symbol: Asset symbol (default: GC)
        timeframe: Candle timeframe (default: 1m)

    Returns:
        DataFrame with features data

    Raises:
        asyncpg.PostgresError: If database query fails
    """
    # Convert date strings to datetime objects
    from dateutil import parser
    start_dt = parser.parse(start_date)
    end_dt = parser.parse(end_date)

    query = """
        SELECT
            f.timestamp,
            f.symbol,
            f.timeframe,
            f.close,
            f.vwap,
            f.vwap_deviation,
            f.vwap_deviation_normalized,
            f.max_abs_deviation_last_20,
            f.min_abs_deviation_last_20,
            f.bars_near_vwap,
            f.near_vwap_count_last_20,
            f.bars_since_last_vwap_touch,
            f.atr,
            f.vwap_slope,
            f.rsi,
            f.structure_label,
            f.ema_9,
            f.ema_20,
            f.ema_50,
            sh.direction
        FROM features f
        LEFT JOIN (
            SELECT DISTINCT ON (timestamp, symbol, timeframe)
                timestamp,
                symbol,
                timeframe,
                direction
            FROM signal_history
            WHERE symbol = $1
              AND timeframe = $2
              AND timestamp >= $3
              AND timestamp < $4
              AND (setup_type = 'REJECTED' OR setup_type = 'VWAP_RECLAIM')
            ORDER BY timestamp, symbol, timeframe, was_approved DESC, created_at DESC
        ) sh
          ON f.timestamp = sh.timestamp
         AND f.symbol = sh.symbol
         AND f.timeframe = sh.timeframe
        WHERE f.symbol = $1
          AND f.timeframe = $2
          AND f.timestamp >= $3
          AND f.timestamp < $4
        ORDER BY f.timestamp;
    """

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            query,
            symbol,
            timeframe,
            start_dt,
            end_dt,
        )

        # Convert to DataFrame
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Convert Decimal columns to float for pandas compatibility
        from decimal import Decimal
        for col in df.columns:
            if df[col].dtype == object and len(df[col]) > 0:
                # Check if first non-null value is a Decimal
                first_val = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                if isinstance(first_val, Decimal):
                    df[col] = df[col].astype(float)

        return df

    finally:
        await conn.close()


async def load_signal_history(
    db_url: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Load signal history data including VWAP_RECLAIM rejections.

    Args:
        db_url: PostgreSQL connection URL
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)

    Returns:
        DataFrame with signal history data including diagnostics

    Raises:
        asyncpg.PostgresError: If database query fails
    """
    # Convert date strings to datetime objects
    from dateutil import parser
    start_dt = parser.parse(start_date)
    end_dt = parser.parse(end_date)

    query = """
        SELECT
            sh.timestamp,
            sh.id,
            sh.symbol,
            sh.direction,
            sh.setup_type,
            sh.score,
            sh.confidence,
            sh.was_approved,
            sh.rejection_stage,
            sh.diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as failed_constraint,
            sh.diagnostics->'vwap_reclaim_validation'->>'reject_reason' as reject_reason,
            sh.diagnostics->'vwap_reclaim_validation'->'context_snapshot' as context_snapshot,
            sh.features_snapshot
        FROM signal_history sh
        WHERE sh.timestamp >= $1
          AND sh.timestamp < $2
          AND (sh.setup_type = 'REJECTED' OR sh.setup_type = 'VWAP_RECLAIM')
        ORDER BY sh.timestamp;
    """

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(query, start_dt, end_dt)

        # Convert to DataFrame
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Convert Decimal columns to float for pandas compatibility
        from decimal import Decimal
        for col in df.columns:
            if df[col].dtype == object and len(df[col]) > 0:
                # Check if first non-null value is a Decimal
                first_val = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                if isinstance(first_val, Decimal):
                    df[col] = df[col].astype(float)

        return df

    finally:
        await conn.close()


def extract_context_values(df: pd.DataFrame, field_name: str) -> pd.Series:
    """
    Extract specific field values from context_snapshot JSON.

    Args:
        df: DataFrame with context_snapshot column
        field_name: Name of field to extract from context_snapshot

    Returns:
        Series with extracted values (NaN if field not present)
    """
    if 'context_snapshot' not in df.columns:
        return pd.Series([None] * len(df))

    def extract_value(context: Any) -> Any:
        if context is None or not isinstance(context, dict):
            return None
        return context.get(field_name)

    return df['context_snapshot'].apply(extract_value)
