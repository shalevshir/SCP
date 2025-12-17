"""Unified backtest replay loop - processes historical data candle-by-candle.

This module implements the complete backtest replay engine that orchestrates:
- Incremental feature computation (no lookahead)
- SOP validation and guardrails enforcement
- Signal generation and entry execution
- Active trade management and simulation
- State tracking (PnL, loss streaks, daily counters, Risk Ladder)

The replay loop processes historical data in strict chronological order, ensuring
deterministic and reproducible results that mirror the live trading bot's behavior.

Key Components:
- BacktestProcessor: Incremental feature computation
- ValidationEngine: SOP validation
- BehaviorGuardrails: Loss streak and fatigue checks
- InvalidationChecker: PDLL and invalidation detection
- RuleEngine: Signal scoring and generation
- EntryModel: Entry execution at next bar open
- Simulator: Trade outcome simulation

Architecture:
    For each candle:
        1. Update active trades (check exits)
        2. Compute HTF bias (must run on every bar for structure warmup)
        3. Check if active trade exists (skip signal generation if true)
        4. Check guardrails (PDLL, loss streak, session, etc.)
        5. Generate signal (if guardrails pass)
        6. Execute entry (if signal is A+)
        7. Create trade (if entry executed)
        8. Update state (PnL, loss streak, daily counters)

Example:
    >>> from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
    >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
    >>> multi_tf_data = sync_layer.load(start, end)
    >>>
    >>> market_state = {
    ...     "buffer_phase": "growth",
    ...     "tier_active": "EarlyMild",
    ...     "ceo_directive_active": True,
    ...     "news_ok": True,
    ...     "session_ok": True,
    ... }
    >>>
    >>> risk_config = {
    ...     "risk_per_trade": 600.0,
    ...     "buffer_phase": "growth",
    ...     "max_contracts": 1,
    ... }
    >>>
    >>> loop = BacktestReplayLoop(
    ...     multi_tf_data=multi_tf_data,
    ...     timeframe="1m",
    ...     market_state=market_state,
    ...     risk_config=risk_config,
    ... )
    >>>
    >>> results = loop.run()
    >>> print(f"Total trades: {len(results.trades)}")
    >>> print(f"Win rate: {results.win_rate:.1f}%")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from common.logger import get_logger
from common.types import Candle
from data_layer.multi_timeframe_helpers import extract_execution_dataframes
from data_layer.multi_timeframe_sync import MultiTimeframeData
from feature_engine.backtesting import BacktestProcessor
from feature_engine.integration import process_features_with_validation
from rule_engine.htf.integration import create_htf_bias_func_with_sync_layer
from validation.engine import ValidationEngine
from validation.guardrails import BehaviorGuardrails

from backtester.entry_model import EntryExecution, execute_entry_at_next_open
from backtester.invalidations import InvalidationChecker
from backtester.simulator import simulate_trade_outcome
from backtester.trade import Trade, create_trade_from_entry

logger = get_logger(__name__)


@dataclass
class BacktestResults:
    """Complete backtest results with trades and performance metrics.

    Attributes:
        trades: List of all closed trades
        executions: List of all entry executions (including rejected)
        total_pnl: Total realized PnL in points
        total_pnl_dollars: Total realized PnL in dollars (if config provided)
        win_rate: Percentage of winning trades
        total_trades: Total number of trades executed
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        average_r: Average R-multiple per trade
        chop_diagnostics: Dict containing chop-related statistics
        max_consecutive_losses: Maximum consecutive losses encountered
        pdll_hits: Number of times PDLL was hit
        session_resets: Number of session resets performed
        structure_stats: Structure label distribution for diagnostics
        setup_candidates: Total bars classified as setup type (not REJECTED)
        rejected_at_scoring: Signals rejected due to score below minimum
        rejected_at_execution: A+ signals rejected at execution (expansion gate)
        executed_trades: Number of trades actually executed
    """

    trades: list[Trade] = field(default_factory=list)
    executions: list[EntryExecution] = field(default_factory=list)
    total_pnl: float = 0.0
    total_pnl_dollars: float | None = None
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    average_r: float = 0.0
    max_consecutive_losses: int = 0
    pdll_hits: int = 0
    session_resets: int = 0
    structure_stats: dict[str, int] = field(default_factory=dict)
    chop_diagnostics: dict = field(default_factory=dict)
    setup_candidates: int = 0
    rejected_at_scoring: int = 0
    rejected_at_execution: int = 0
    executed_trades: int = 0


class BacktestReplayLoop:
    """Unified backtest replay loop that processes data candle-by-candle.

    This class orchestrates the complete backtesting pipeline, integrating:
    - Feature computation (BacktestProcessor)
    - Validation and guardrails (ValidationEngine, BehaviorGuardrails)
    - Signal generation (RuleEngine via process_features_with_validation)
    - Entry execution (EntryModel)
    - Trade simulation (Simulator)
    - State management (PnL, loss streaks, daily counters)

    The loop ensures:
    - No lookahead bias (only uses data up to current candle)
    - Deterministic results (same input → same output)
    - SOP compliance (all guardrails enforced)
    - Realistic execution (next bar open entries)
    - Complete auditability (all trades logged)

    Example:
        >>> loop = BacktestReplayLoop(
        ...     multi_tf_data=multi_tf_data,
        ...     timeframe="1m",
        ...     market_state=market_state,
        ...     risk_config=risk_config,
        ... )
        >>> results = loop.run()
        >>> print(f"Total trades: {results.total_trades}")
    """

    def __init__(
        self,
        multi_tf_data: MultiTimeframeData,
        timeframe: str,
        market_state: dict[str, Any],
        risk_config: dict[str, Any],
        htf_approach: str = "streaming",
        config: dict | None = None,
        log_signals: bool = False,
        log_dir: str | None = None,
        execution_start: datetime | None = None,
    ) -> None:
        """Initialize backtest replay loop.

        Args:
            multi_tf_data: Synchronized multi-timeframe data
            timeframe: Execution timeframe (e.g., "1m")
            market_state: Market context dict containing:
                - buffer_phase: Current capital phase ("startup", "growth", etc.)
                - tier_active: Active enforcer tier ("Conservative", "EarlyMild", etc.)
                - ceo_directive_active: Whether CEO directive is active (bool)
                - news_ok: Whether trading is allowed during news events (bool)
                - session_ok: Whether current session is valid for trading (bool)
            risk_config: Risk configuration dict containing:
                - risk_per_trade: Dollar risk per trade
                - buffer_phase: Current capital phase
            execution_start: Optional start datetime for signal execution.
                            Candles before this time are used for warmup only
                            (HTF features are computed but signals are not recorded).
                - max_contracts: Maximum contracts allowed
            htf_approach: "streaming" (incremental) or "vectorized" (pre-computed)
                         for HTF feature computation (default: "streaming")
            config: Optional config dict for dollar PnL calculation
            log_signals: Whether to log signals to disk (default: False)
            log_dir: Directory for signal logs (required if log_signals=True)
        """
        self.timeframe = timeframe
        self.market_state = market_state
        self.risk_config = risk_config
        self.htf_approach = htf_approach
        self.config = (
            config
            if config is not None
            else {
                "backtest": {
                    "pdll_limit": 600.0,
                    "max_trades_per_day": 2,
                    "slippage_points": 0.5,
                    "commission_per_trade": 5.0,
                },
                "assets": {
                    "tick_values": {"GC": 10.0},
                    "tick_sizes": {"GC": 0.1},
                },
            }
        )
        self.log_signals = log_signals
        self.log_dir = log_dir
        self.execution_start = execution_start

        # Extract execution DataFrames from multi-timeframe data
        self.gc_df, self.dxy_df = extract_execution_dataframes(multi_tf_data)

        # Initialize components
        self._processor = BacktestProcessor(timeframe=timeframe, enable_validation=True)
        self._validation_engine = ValidationEngine()
        self._behavior_guardrails = BehaviorGuardrails()
        self._invalidation_checker = InvalidationChecker()

        # Create HTF bias function
        self._htf_bias_func = create_htf_bias_func_with_sync_layer(
            multi_tf_data, approach=htf_approach
        )

        # State tracking
        self._active_trades: dict[str, Trade] = {}
        self._trade_bar_counts: dict[str, int] = {}  # External bar tracking (trade_id -> bars_elapsed)
        self._daily_pnl: float = 0.0
        self._session_date: datetime | None = None
        self._trades_today: int = 0
        self._pdll_hit: bool = False
        self._max_consecutive_losses: int = 0
        self._pdll_hit_count: int = 0
        self._session_reset_count: int = 0

        # Structure label statistics for diagnostics
        from collections import Counter

        self._structure_stats: Counter = Counter()

        # Track simulated exits to prevent overlapping trades
        self._simulated_exits: dict[str, datetime] = {}

        # Results tracking
        self._all_trades: list[Trade] = []
        self._all_executions: list[EntryExecution] = []

        # Signal flow diagnostic counters
        self._setup_candidates: int = 0  # Total bars with setup_type != "REJECTED"
        self._rejected_at_scoring: int = 0  # Score below minimum
        self._rejected_at_execution: int = 0  # A+ but expansion gate failed
        self._executed_trades: int = 0  # Actually executed

        logger.info(
            f"BacktestReplayLoop initialized: timeframe={timeframe}, "
            f"htf_approach={htf_approach}, tier={market_state.get('tier_active')}"
        )

    def run(self) -> BacktestResults:
        """Run the complete backtest replay loop.

        Processes the entire historical dataset candle-by-candle, executing the
        full trading pipeline at each step. Returns complete backtest results
        including all trades and performance metrics.

        Returns:
            BacktestResults object with all trades and metrics

        Example:
            >>> results = loop.run()
            >>> print(f"Win rate: {results.win_rate:.1f}%")
            >>> print(f"Total PnL: {results.total_pnl:.2f} points")
        """
        logger.info("=" * 80)
        logger.info("Starting Backtest Replay Loop")
        logger.info("=" * 80)
        logger.info(f"Dataset: {len(self.gc_df)} candles")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Buffer phase: {self.market_state.get('buffer_phase')}")
        logger.info(f"Tier active: {self.market_state.get('tier_active')}")

        candle_count = 0
        signal_count = 0
        entry_count = 0

        # Main loop: iterate through candles with entry context
        for (
            features,
            validation_context,
            next_candle,
        ) in self._processor.iterate_with_entry_context(self.gc_df, self.dxy_df):
            candle_count += 1
            current_timestamp = features["timestamp"]

            # Skip candles before execution_start (warmup period)
            # These candles are still processed to update HTF features
            # but signals are not recorded
            if self.execution_start is not None:
                # Convert timestamp for comparison
                if hasattr(current_timestamp, "to_pydatetime"):
                    ts_dt = current_timestamp.to_pydatetime()
                else:
                    ts_dt = current_timestamp
                
                # Make both timezone-aware or naive for comparison
                exec_start = self.execution_start
                if ts_dt.tzinfo is None and exec_start.tzinfo is not None:
                    exec_start = exec_start.replace(tzinfo=None)
                elif ts_dt.tzinfo is not None and exec_start.tzinfo is None:
                    from datetime import timezone
                    exec_start = exec_start.replace(tzinfo=timezone.utc)
                
                if ts_dt < exec_start:
                    # Skip signal recording but continue processing for HTF warmup
                    continue

            # Process this candle
            execution = self._process_candle(
                features, validation_context, next_candle, current_timestamp
            )

            if execution is not None:
                signal_count += 1
                self._all_executions.append(execution)

                if execution.executed:
                    entry_count += 1

        # Close any remaining active trades at end of dataset
        self._close_remaining_trades()

        # Calculate final results
        results = self._calculate_results()

        logger.info("=" * 80)
        logger.info("Backtest Replay Loop Complete")
        logger.info("=" * 80)
        logger.info(f"Candles processed: {candle_count}")
        logger.info(f"Signals generated: {signal_count}")
        logger.info(f"Entries executed: {entry_count}")
        logger.info(f"Trades completed: {results.total_trades}")
        logger.info(f"Win rate: {results.win_rate:.1f}%")
        logger.info(f"Total PnL: {results.total_pnl:.2f} points")
        if results.total_pnl_dollars is not None:
            logger.info(f"Total PnL (dollars): ${results.total_pnl_dollars:.2f}")
        logger.info(f"Average R: {results.average_r:.2f}R")
        logger.info(f"Max consecutive losses: {results.max_consecutive_losses}")
        logger.info(f"PDLL hits: {results.pdll_hits}")
        logger.info(f"Session resets: {results.session_resets}")
        logger.info("=" * 80)
        logger.info("Signal Flow Diagnostics")
        logger.info("=" * 80)
        logger.info(f"Setup candidates detected: {results.setup_candidates}")
        logger.info(f"Rejected at scoring (score too low): {results.rejected_at_scoring}")
        logger.info(f"Rejected at execution (expansion gate): {results.rejected_at_execution}")
        logger.info(f"Executed trades: {results.executed_trades}")
        if results.setup_candidates > 0:
            execution_rate = (results.executed_trades / results.setup_candidates) * 100
            logger.info(f"Execution rate: {execution_rate:.1f}% (executed / candidates)")
        logger.info("=" * 80)

        return results

    def _process_candle(
        self,
        features: pd.Series,
        validation_context: dict,
        next_candle: Candle | None,
        current_timestamp: datetime,
    ) -> EntryExecution | None:
        """Process a single candle through the complete trading pipeline.

        This method implements the core loop logic:
        1. Check session boundaries and reset state if needed
        2. Update active trades (check for exits)
        3. Compute HTF bias (must run on every bar for structure warmup)
        4. Check if active trade exists (skip signal generation if true)
        5. Check guardrails before allowing new entries
        6. Generate signal (if guardrails pass)
        7. Execute entry (if signal is A+)
        8. Create trade (if entry executed)
        9. Update state after trade closes

        Args:
            features: Feature series for current candle
            validation_context: Validation context from BacktestProcessor
            next_candle: Next candle for entry execution (None if end of data)
            current_timestamp: Current candle timestamp

        Returns:
            EntryExecution if signal was generated, None otherwise
        """
        # Step 1: Check session boundaries and reset if needed
        current_date = current_timestamp.date()
        if self._session_date is None or current_date != self._session_date:
            self._reset_session(current_timestamp)

        # Step 2: Update active trades (check exits on current candle)
        # Create current candle from features
        try:
            current_candle = Candle(
                timestamp=current_timestamp,
                open=float(features["open"]),
                high=float(features["high"]),
                low=float(features["low"]),
                close=float(features["close"]),
                volume=float(features["volume"]),
                symbol="GC",
                timeframe=self.timeframe,
                source="BACKTEST",
            )
            self._update_active_trades(current_candle, features)
        except (KeyError, ValueError) as e:
            logger.warning(
                f"Failed to create candle from features at {current_timestamp}: {e}"
            )
            return None

        # Step 3: Compute HTF bias FIRST (must happen every bar to accumulate HTF data)
        # This must run BEFORE active trade check AND guardrails check so streaming
        # HTF processor gets updated even when trades are active or outside trading
        # hours - needed for structure detection warmup
        try:
            htf_bias = self._htf_bias_func(features, validation_context)
        except Exception as e:
            logger.warning(
                f"Failed to compute HTF bias at {current_timestamp}: {e}",
                exc_info=True,
            )
            return None

        # Track structure label statistics for diagnostics
        structure_label = features.get("structure_label", "NA")
        if structure_label is None or (
            isinstance(structure_label, float) and pd.isna(structure_label)
        ):
            structure_label = "NA"
        self._structure_stats[str(structure_label)] += 1

        # Step 4: Check if we can take new entries (max concurrent trades limit)
        max_concurrent = self.config.get("backtest", {}).get("max_concurrent_trades", 1)
        if len(self._active_trades) >= max_concurrent:
            logger.debug(
                f"Max concurrent trades limit reached ({len(self._active_trades)}/{max_concurrent}) "
                f"at {current_timestamp}, skipping signal generation"
            )
            return None

        # Step 5: Check guardrails before generating signal
        guardrails_allowed, blocking_reasons = self._check_guardrails(
            validation_context, current_timestamp, features
        )

        if not guardrails_allowed:
            logger.debug(
                f"Guardrails blocked entry at {current_timestamp}: {blocking_reasons}"
            )
            return None

        # Step 6: Generate signal
        session_constraints = validation_context.get("session_constraints")
        guardrail_result = validation_context.get("guardrail_result")

        try:
            signal = process_features_with_validation(
                features=features,
                htf_bias=htf_bias,
                market_state=self.market_state,
                session_constraints=session_constraints,
                guardrail_result=guardrail_result,
                log_signals=self.log_signals,
                log_dir=self.log_dir,
            )
        except Exception as e:
            logger.warning(
                f"Failed to generate signal at {current_timestamp}: {e}",
                exc_info=True,
            )
            return None

        # Track setup candidates (setup_type != "REJECTED")
        if signal.setup_type != "REJECTED":
            self._setup_candidates += 1
            logger.debug(
                f"Setup candidate detected: {signal.setup_type} "
                f"(score={signal.score}, confidence={signal.confidence})"
            )
        
        # Track rejection at scoring (score too low, confidence not A+)
        if signal.setup_type != "REJECTED" and signal.confidence != "A+":
            self._rejected_at_scoring += 1
            logger.debug(
                f"Rejected at scoring: {signal.setup_type} "
                f"(score={signal.score}, confidence={signal.confidence})"
            )

        # Step 7: Execute entry at next bar open
        execution = execute_entry_at_next_open(signal, next_candle)
        
        # Track rejection at execution (A+ but expansion gate failed)
        if not execution.executed and signal.confidence == "A+":
            if "expansion" in execution.rejection_reason.lower():
                self._rejected_at_execution += 1
                logger.debug(
                    f"Rejected at execution: {signal.setup_type} "
                    f"(reason={execution.rejection_reason})"
                )
        
        # Track executed trades
        if execution.executed:
            self._executed_trades += 1
            logger.debug(
                f"Trade executed: {signal.setup_type} "
                f"(score={signal.score}, entry_price={execution.entry_price})"
            )

        # Step 8: If entry executed, create trade and add to active trades
        if execution.executed and next_candle is not None:
            try:
                # Extract structure candles from HTF bias
                # Priority: Use HTF-provided candles, fallback to entry candle
                bos_candle = htf_bias.bos_candle if htf_bias.bos_candle else None

                # For confirmation candle, use HTF-provided if available,
                # otherwise use entry candle
                if htf_bias.confirmation_candle:
                    confirmation_candle = htf_bias.confirmation_candle
                else:
                    # Fallback: Use entry candle as confirmation
                    entry_idx = self.gc_df.index.get_loc(execution.entry_timestamp)
                    confirmation_candle_row = self.gc_df.iloc[entry_idx]

                    confirmation_candle = Candle(
                        timestamp=confirmation_candle_row.name,
                        open=confirmation_candle_row["open"],
                        high=confirmation_candle_row["high"],
                        low=confirmation_candle_row["low"],
                        close=confirmation_candle_row["close"],
                        volume=confirmation_candle_row["volume"],
                        symbol=execution.signal.symbol,
                        timeframe=execution.signal.timeframe,
                        source="BACKTEST",
                    )

                # Determine HTF alignment for R-multiple calculation
                htf_aligned = self._is_htf_aligned(
                    execution.signal.direction, htf_bias.bias
                )

                # Determine DXY alignment from HTF bias
                dxy_aligned = htf_bias.dxy_alignment

                market_context = {
                    "month": execution.entry_timestamp.month,
                    "htf_aligned": htf_aligned,
                    "dxy_aligned": dxy_aligned,
                }

                trade = create_trade_from_entry(
                    entry_execution=execution,
                    confirmation_candle=confirmation_candle,
                    bos_candle=bos_candle,
                    risk_config=self.risk_config,
                    market_context=market_context,
                    config=self.config,
                )

                # Add diagnostic context at entry
                from backtester.diagnostics import add_nested_diag

                # Get features for entry candle
                if features is not None:
                    # Structure features
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "structure_label",
                        features.get("structure_label"),
                    )
                    add_nested_diag(
                        trade, "entry_context", "micro_bos", features.get("micro_bos")
                    )
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "liquidity_sweep",
                        features.get("liquidity_sweep"),
                    )

                    # VWAP features
                    add_nested_diag(
                        trade, "entry_context", "vwap", features.get("vwap")
                    )
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "vwap_deviation",
                        features.get("vwap_deviation"),
                    )
                    add_nested_diag(
                        trade, "entry_context", "vwap_slope", features.get("vwap_slope")
                    )

                    # Indicators
                    add_nested_diag(trade, "entry_context", "rsi", features.get("rsi"))
                    add_nested_diag(
                        trade, "entry_context", "atr_5", features.get("atr_5")
                    )

                    # Volume
                    add_nested_diag(
                        trade, "entry_context", "volume", features.get("volume")
                    )
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "volume_sma_20",
                        features.get("volume_sma_20"),
                    )

                    # Rejection candle raw components (if available)
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "rejection_candle_raw",
                        {
                            "wick_penetration": features.get("wick_penetration"),
                            "close_vs_vwap_diff": features.get("close_vs_vwap_diff"),
                            "direction_valid": features.get(
                                "rejection_direction_valid"
                            ),
                        },
                    )

                # Log factor-level scoring if available on the signal object
                if hasattr(execution.signal, "factors") and execution.signal.factors:
                    add_nested_diag(
                        trade,
                        "entry_context",
                        "scoring_factors",
                        execution.signal.factors,
                    )

                # Add to active trades and initialize bar counter
                self._active_trades[trade.trade_id] = trade
                self._trade_bar_counts[trade.trade_id] = 0  # Initialize counter at 0
                self._trades_today += 1

                logger.info(
                    f"Trade opened: {trade.trade_id} {trade.direction} "
                    f"{trade.symbol} @ {trade.entry_price} "
                    f"(SL={trade.stop_loss}, TP={trade.take_profit}, "
                    f"R={trade.r_multiple})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to create trade from entry at "
                    f"{execution.entry_timestamp}: {e}",
                    exc_info=True,
                )

        return execution

    def _is_htf_aligned(self, direction: str, bias_value: str | None) -> bool:
        """Check if trade direction aligns with HTF bias.

        Args:
            direction: Trade direction ("long" or "short")
            bias_value: HTF bias string ("bullish", "bearish", "neutral", None)

        Returns:
            True if aligned, False otherwise
        """
        if bias_value is None:
            return False

        return (bias_value == "bullish" and direction == "long") or (
            bias_value == "bearish" and direction == "short"
        )

    def _check_guardrails(
        self,
        validation_context: dict,
        current_timestamp: datetime,
        features: pd.Series | None = None,
    ) -> tuple[bool, list[str]]:
        """Check all SOP guardrails before allowing entry.

        This method enforces all SOP guardrails:
        - PDLL enforcement: stop trading when daily loss limit hit
        - Loss streak halt: block after 2 consecutive losses
        - Maximum concurrent trades: enforce configurable limit (default: 1)
        - Maximum trades per day: enforce daily trade limits
        - Session resets: reset state at day boundaries, enforce 10:00–13:00 ILT
        - Seasonality rules: Sept conservative, Nov–Dec trend allowed
        - CEO Directives: (Early Mild) tier overrides when active
        - DXY availability: block signals if DXY feed missing
        - Phase-aware Risk Ladder: enforce contract size + max risk per trade

        Args:
            validation_context: Validation context from BacktestProcessor
            current_timestamp: Current candle timestamp
            features: Feature series for current candle (optional, for DXY check)

        Returns:
            Tuple of (allowed, reasons) where allowed is True if all guardrails pass,
            and reasons is a list of blocking reasons if not allowed
        """
        blocking_reasons: list[str] = []

        # Guardrail 1: PDLL (Per Day Loss Limit) enforcement
        if self._pdll_hit:
            blocking_reasons.append("PDLL hit - no further trading today")
            logger.debug(f"PDLL guardrail blocked at {current_timestamp}")

        # Guardrail 2: Check PDLL based on current daily PnL
        pdll_limit = self.config.get("backtest", {}).get("pdll_limit", 600.0)
        if self._daily_pnl <= -pdll_limit:
            if not self._pdll_hit:
                self._pdll_hit = True
                self._pdll_hit_count += 1
                logger.warning(
                    f"PDLL limit hit at {current_timestamp}: "
                    f"daily_pnl={self._daily_pnl:.2f}, limit={pdll_limit}"
                )
            blocking_reasons.append(
                f"PDLL limit reached: daily_pnl={self._daily_pnl:.2f} <= -{pdll_limit}"
            )

        # Guardrail 3: Maximum trades per day (default: 2)
        max_trades_per_day = self.config.get("backtest", {}).get(
            "max_trades_per_day", 2
        )
        if self._trades_today >= max_trades_per_day:
            blocking_reasons.append(
                f"Daily trade limit reached: {self._trades_today}/{max_trades_per_day}"
            )
            logger.debug(f"Daily trade limit guardrail blocked at {current_timestamp}")

        # Guardrail 4: Session time check (from validation_context)
        session_ok = validation_context.get("session_ok", False)
        if not session_ok:
            blocking_reasons.append("Outside trading session hours (10:00-13:00 ILT)")
            logger.debug(f"Session time guardrail blocked at {current_timestamp}")

        # Guardrail 5: Behavior guardrails (loss streak, fatigue, session extension)
        behavior_state = validation_context.get("behavior_state")
        session_constraints = validation_context.get("session_constraints")

        if behavior_state and session_constraints:
            guardrail_result = self._behavior_guardrails.evaluate(
                behavior_state, session_constraints
            )

            if not guardrail_result.allowed:
                blocking_reasons.extend(guardrail_result.reasons)
                logger.debug(
                    f"Behavior guardrails blocked at {current_timestamp}: "
                    f"{guardrail_result.reasons}"
                )

        # Guardrail 6: DXY availability check
        # Check if DXY data is missing or invalid
        if features is not None and "dxy_corr" in features.index:
            dxy_corr = features.get("dxy_corr")
            if dxy_corr is None or (isinstance(dxy_corr, float) and pd.isna(dxy_corr)):
                blocking_reasons.append("DXY data not available")
                logger.debug(
                    f"DXY availability guardrail blocked at {current_timestamp}"
                )

        # Guardrail 7: Seasonality rules
        # (already handled by ValidationEngine in signal generation)
        # This is enforced through session_constraints and market_state

        # Guardrail 8: CEO Directive check
        # (already handled by market_state in signal generation)
        # This is enforced through market_state passed to
        # process_features_with_validation

        # Guardrail 9: Phase-aware Risk Ladder (contract size + max risk per trade)
        # This is enforced in trade creation (create_trade_from_entry)
        # But we can add an early check here
        buffer_phase = self.risk_config.get("buffer_phase", "startup")
        max_contracts = self.risk_config.get("max_contracts", 1)

        if max_contracts <= 0:
            blocking_reasons.append(
                f"Risk ladder constraint: max_contracts={max_contracts} "
                f"for phase={buffer_phase}"
            )
            logger.debug(f"Risk ladder guardrail blocked at {current_timestamp}")

        # Return result
        allowed = len(blocking_reasons) == 0

        if allowed:
            logger.debug(f"All guardrails passed at {current_timestamp}")
        else:
            logger.info(
                f"Guardrails blocked entry at {current_timestamp}: "
                f"{blocking_reasons}"
            )

        return allowed, blocking_reasons

    def _update_active_trades(
        self, current_candle: Candle, features: pd.Series
    ) -> None:
        """Update active trades and check for exits (single-bar approach).

        This method checks each active trade against the current candle only,
        matching live trading behavior where you only know the current bar.

        For each active trade:
        1. Increment bar counter
        2. Check current candle for exit conditions (SL, TP, invalidation, timeout)
        3. If exit hit, close trade and update state
        4. If no exit, continue to next bar

        Args:
            current_candle: Current candle to check against active trades
            features: Feature series for current candle (for invalidation checks)
        """
        if not self._active_trades:
            return

        # Import single-bar checker
        from backtester.simulator import check_trade_exit_single_bar

        # Process each active trade
        # (make copy of dict keys since we may modify during iteration)
        for trade_id in list(self._active_trades.keys()):
            trade = self._active_trades[trade_id]

            # Check if current candle is after entry (trade should be active)
            if current_candle.timestamp <= trade.entry_timestamp:
                continue

            # Increment bar counter for this trade
            if trade_id not in self._trade_bar_counts:
                self._trade_bar_counts[trade_id] = 0
            self._trade_bar_counts[trade_id] += 1
            bars_elapsed = self._trade_bar_counts[trade_id]

            # Get features for current candle (for invalidation checks)
            candle_features = features.to_dict() if features is not None else None

            # Check single bar for exit
            updated_trade = check_trade_exit_single_bar(
                trade=trade,
                candle=current_candle,
                bars_elapsed=bars_elapsed,
                invalidation_checker=self._invalidation_checker,
                config=self.config,
                candle_features=candle_features,
            )

            # If trade closed, update state
            if updated_trade.status != "OPEN":
                pnl_str = (
                    f"{updated_trade.pnl:.2f}"
                    if updated_trade.pnl is not None
                    else "None"
                )
                r_str = (
                    f"{updated_trade.r_realized:.2f}"
                    if updated_trade.r_realized is not None
                    else "None"
                )
                logger.info(
                    f"Trade {trade_id} closed at "
                    f"{updated_trade.exit_timestamp}: "
                    f"exit_reason={updated_trade.exit_reason}, "
                    f"PnL={pnl_str}, "
                    f"R={r_str}"
                )

                # Remove from active trades and bar counts
                del self._active_trades[trade_id]
                del self._trade_bar_counts[trade_id]

                # Add to completed trades
                self._all_trades.append(updated_trade)

                # Update state (PnL, loss streak, etc.)
                self._update_state(updated_trade)

    def _update_state(self, closed_trade: Trade) -> None:
        """Update state after trade closes.

        Updates:
        - Daily PnL (accumulated for the session)
        - Loss streak tracking (for guardrails)
        - Trade count
        - Max consecutive losses tracking
        - Behavior tracker state (for loss streak guardrails)
        - Invalidation checker state (for PDLL checks)

        Args:
            closed_trade: Trade that just closed
        """
        # Update daily PnL
        if closed_trade.pnl is not None:
            self._daily_pnl += closed_trade.pnl
            # pnl is guaranteed to be not None here, but r_realized might be
            pnl_str = f"{closed_trade.pnl:.2f}"
            r_str = (
                f"{closed_trade.r_realized:.2f}"
                if closed_trade.r_realized is not None
                else "None"
            )
            logger.info(
                f"Trade {closed_trade.trade_id} closed: "
                f"PnL={pnl_str}, "
                f"R={r_str}, "
                f"exit_reason={closed_trade.exit_reason}, "
                f"daily_pnl={self._daily_pnl:.2f}"
            )

        # Determine trade outcome for loss streak tracking
        # won=True: pnl > 0 (actual profit)
        # won=False: pnl < 0 (actual loss)
        # won=None: pnl == 0 (breakeven, no capital lost)
        if closed_trade.pnl is None:
            won = None
        elif closed_trade.pnl > 0:
            won = True
        elif closed_trade.pnl < 0:
            won = False
        else:  # pnl == 0
            won = None

        # Update behavior tracker (for loss streak guardrails before entry)
        if self._processor and hasattr(self._processor, "record_trade_outcome"):
            self._processor.record_trade_outcome(won)

        # Update invalidation checker daily state
        # (for PDLL checks during trade simulation)
        self._invalidation_checker.record_trade_outcome(closed_trade, won=won)

        # Track max consecutive losses for reporting
        current_state = (
            self._processor._behavior_tracker.state
            if hasattr(self._processor, "_behavior_tracker")
            else None
        )
        if current_state:
            self._max_consecutive_losses = max(
                self._max_consecutive_losses, current_state.consecutive_losses
            )

        logger.debug(
            f"State updated: daily_pnl={self._daily_pnl:.2f}, "
            f"trades_today={self._trades_today}, "
            f"pdll_hit={self._pdll_hit}"
        )

    def _reset_session(self, current_timestamp: datetime) -> None:
        """Reset state at session boundary.

        Resets:
        - Daily PnL (starts fresh for new session)
        - PDLL hit flag (new session, new PDLL allowance)
        - Trades today counter
        - Session date tracking
        - Behavior tracker (loss streak resets at session start per SOP)

        Args:
            current_timestamp: Current timestamp (for tracking session date)
        """
        current_date = current_timestamp.date()

        # Only reset if this is a new session
        if self._session_date is not None and current_date == self._session_date:
            return

        logger.info("=" * 60)
        logger.info(f"Session reset at {current_timestamp}")
        logger.info(f"Previous session date: {self._session_date}")
        logger.info(f"Previous daily PnL: {self._daily_pnl:.2f}")
        logger.info(f"Previous trades today: {self._trades_today}")

        # Log structure label distribution from previous session
        if self._session_date is not None and self._structure_stats:
            total_candles = sum(self._structure_stats.values())
            logger.info(
                f"Session {self._session_date} structure distribution "
                f"(total: {total_candles} candles):"
            )
            for label in ["HH", "HL", "LH", "LL", "NA"]:
                count = self._structure_stats.get(label, 0)
                pct = (count / total_candles * 100) if total_candles > 0 else 0
                logger.info(f"  {label}: {count} ({pct:.1f}%)")

        logger.info("=" * 60)

        # Reset daily state
        self._daily_pnl = 0.0
        self._pdll_hit = False
        self._trades_today = 0
        self._session_date = current_date
        self._session_reset_count += 1

        # Reset structure statistics for new session
        self._structure_stats.clear()

        # Reset behavior tracker (loss streak resets at session start per SOP)
        if self._processor and hasattr(self._processor, "_behavior_tracker"):
            self._processor._behavior_tracker.reset_for_session(current_timestamp)

        # Reset invalidation checker daily state
        self._invalidation_checker._daily_state = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": current_date,
        }

        logger.info(
            "Session state reset complete: "
            "daily_pnl=0.0, pdll_hit=False, trades_today=0"
        )

    def _close_remaining_trades(self) -> None:
        """Close any remaining active trades at end of dataset.

        This method is called at the end of the backtest loop to ensure
        all active trades are closed, even if they haven't hit SL/TP or
        timed out. Trades are closed at the last candle's close price
        with exit_reason="end_of_data".
        """
        if not self._active_trades:
            return

        logger.info(
            f"Closing {len(self._active_trades)} remaining active trades "
            "at end of dataset"
        )

        # Get last candle from dataset
        if len(self.gc_df) == 0:
            logger.warning("No candles in dataset to close remaining trades")
            return

        last_candle_row = self.gc_df.iloc[-1]
        last_timestamp = self.gc_df.index[-1]

        last_candle = Candle(
            timestamp=last_timestamp,
            open=last_candle_row["open"],
            high=last_candle_row["high"],
            low=last_candle_row["low"],
            close=last_candle_row["close"],
            volume=last_candle_row["volume"],
            symbol="GC",
            timeframe=self.timeframe,
            source="BACKTEST",
        )

        # Close each remaining trade
        for trade_id, trade in list(self._active_trades.items()):
            logger.warning(
                f"Closing trade {trade_id} at end of dataset: "
                f"entry={trade.entry_timestamp}, last_candle={last_timestamp}"
            )

            # Import close_trade function
            from backtester.trade import close_trade

            # Close trade at last candle
            closed_trade = close_trade(trade, last_candle, "end_of_data", self.config)

            # Remove from active trades and bar counts
            del self._active_trades[trade_id]
            if trade_id in self._trade_bar_counts:
                del self._trade_bar_counts[trade_id]

            # Add to completed trades
            self._all_trades.append(closed_trade)

            # Update state
            self._update_state(closed_trade)

            pnl_str = (
                f"{closed_trade.pnl:.2f}" if closed_trade.pnl is not None else "None"
            )
            r_str = (
                f"{closed_trade.r_realized:.2f}"
                if closed_trade.r_realized is not None
                else "None"
            )
            logger.info(
                f"Trade {trade_id} closed at end of dataset: "
                f"PnL={pnl_str}, R={r_str}"
            )

    def _calculate_results(self) -> BacktestResults:
        """Calculate final backtest results and metrics.

        Returns:
            BacktestResults object with all trades and metrics
        """
        # Calculate basic metrics
        total_trades = len(self._all_trades)
        winning_trades = len([t for t in self._all_trades if t.pnl and t.pnl > 0])
        losing_trades = len([t for t in self._all_trades if t.pnl and t.pnl < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Calculate PnL (ensure float type)
        total_pnl = float(sum(t.pnl for t in self._all_trades if t.pnl is not None))
        total_pnl_dollars = None
        if any(t.pnl_net is not None for t in self._all_trades):
            total_pnl_dollars = float(
                sum(t.pnl_net for t in self._all_trades if t.pnl_net is not None)
            )

        # Calculate average R
        r_values = [t.r_realized for t in self._all_trades if t.r_realized is not None]
        average_r = float(sum(r_values) / len(r_values)) if r_values else 0.0

        # Calculate chop diagnostics
        chop_diagnostics = self._calculate_chop_diagnostics()

        return BacktestResults(
            trades=self._all_trades,
            executions=self._all_executions,
            total_pnl=total_pnl,
            total_pnl_dollars=total_pnl_dollars,
            win_rate=win_rate,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            average_r=average_r,
            max_consecutive_losses=self._max_consecutive_losses,
            pdll_hits=self._pdll_hit_count,
            session_resets=self._session_reset_count,
            chop_diagnostics=chop_diagnostics,
            structure_stats=dict(self._structure_stats),
            setup_candidates=self._setup_candidates,
            rejected_at_scoring=self._rejected_at_scoring,
            rejected_at_execution=self._rejected_at_execution,
            executed_trades=self._executed_trades,
        )

    def _calculate_chop_diagnostics(self) -> dict:
        """Calculate chop-related statistics from all executions.
        
        Returns:
            Dict containing:
            - signals_evaluated_during_chop: Total signals evaluated during chop
            - signals_blocked_by_chop: Signals rejected due to chop
            - fades_allowed_during_chop: VWAP_FADE signals allowed during chop
            - reclaims_penalized_by_chop: VWAP_RECLAIM signals penalized by chop
            - continuations_blocked_by_chop: DXY_CONTINUATION signals blocked by chop
            - chop_severity_distribution: Count of signals by chop severity
        """
        signals_evaluated_during_chop = 0
        signals_blocked_by_chop = 0
        fades_allowed_during_chop = 0
        reclaims_penalized_by_chop = 0
        continuations_blocked_by_chop = 0
        chop_severity_distribution = {"none": 0, "soft": 0, "hard": 0}
        
        for execution in self._all_executions:
            validation_flags = execution.signal.validation_flags
            chop_detected = validation_flags.get("chop_detected", False)
            chop_severity = validation_flags.get("chop_severity", "none")
            setup_type = execution.signal.setup_type
            
            # Track severity distribution
            chop_severity_distribution[chop_severity] = (
                chop_severity_distribution.get(chop_severity, 0) + 1
            )
            
            if chop_detected:
                signals_evaluated_during_chop += 1
                
                # Check if rejected due to chop
                rejection_reason = execution.rejection_reason or ""
                if "chop" in rejection_reason.lower():
                    signals_blocked_by_chop += 1
                    
                    # Track by setup type
                    if setup_type == "DXY_CONTINUATION":
                        continuations_blocked_by_chop += 1
                
                # Track fades allowed during chop
                if setup_type == "VWAP_FADE" and execution.executed:
                    fades_allowed_during_chop += 1
                
                # Track reclaims penalized (soft chop, not blocked)
                if (
                    setup_type == "VWAP_RECLAIM"
                    and chop_severity == "soft"
                    and not ("chop" in rejection_reason.lower())
                ):
                    reclaims_penalized_by_chop += 1
        
        return {
            "signals_evaluated_during_chop": signals_evaluated_during_chop,
            "signals_blocked_by_chop": signals_blocked_by_chop,
            "fades_allowed_during_chop": fades_allowed_during_chop,
            "reclaims_penalized_by_chop": reclaims_penalized_by_chop,
            "continuations_blocked_by_chop": continuations_blocked_by_chop,
            "chop_severity_distribution": chop_severity_distribution,
        }
