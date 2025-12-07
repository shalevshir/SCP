"""Simulation Engine - Core orchestrator for dashboard simulation.

This module provides SimulationEngine that coordinates streaming data processing,
feature calculation, HTF bias computation, signal generation, and state updates.

Architecture:
- Pure Python, no Dash dependencies
- Thread-safe state updates
- Warmup as first-class concept
- Auto-pause on A+ signals
"""

import threading
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from common.logger import get_logger
from common.types import Candle
from dashboard.core.data_stream import DataStream
from dashboard.core.state import DashboardState, PriceBar
from rule_engine.htf.streaming import StreamingHTFBiasCalculator
from rule_engine.scoring import score_signal
from rule_engine.signal import Signal
from validation.engine import ValidationEngine
from validation.session_validator import SessionValidator

logger = get_logger(__name__)


class SimulationEngine:
    """Core simulation engine for dashboard.

    Orchestrates data streaming, feature calculation, HTF bias computation,
    signal scoring, and state management. Runs in background thread.

    Features:
    - Multi-day warmup support
    - Auto-pause on A+ signals
    - Thread-safe state access
    - Single tick() method for testability

    Attributes:
        data_stream: Historical data iterator
        htf_calculator: Streaming HTF bias calculator
        validation_engine: Signal validation engine
        session_validator: Session constraints validator
        state: Current dashboard state (immutable)
        auto_pause_on_a_plus: Whether to pause on A+ signals
        speed_multiplier: Simulation speed (default: 1.0)
    """

    def __init__(
        self,
        data_stream: DataStream,
        validation_engine: ValidationEngine,
        session_validator: SessionValidator,
        auto_pause_on_a_plus: bool = True,
        speed_multiplier: float = 1.0,
    ):
        """Initialize simulation engine.

        Args:
            data_stream: Configured data stream with loaded data
            validation_engine: Configured validation engine
            session_validator: Configured session validator
            auto_pause_on_a_plus: Auto-pause on A+ signals (default: True)
            speed_multiplier: Simulation speed multiplier (default: 1.0)
        """
        self.data_stream = data_stream
        self.htf_calculator = StreamingHTFBiasCalculator()
        self.validation_engine = validation_engine
        self.session_validator = session_validator

        # Configuration
        self.auto_pause_on_a_plus = auto_pause_on_a_plus
        self.speed_multiplier = speed_multiplier

        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # State (immutable, replaced atomically)
        self._state = DashboardState.create_empty()
        self._state = self._state.update(simulation_speed=speed_multiplier)

        logger.info(
            f"SimulationEngine initialized | "
            f"auto_pause={auto_pause_on_a_plus} | "
            f"speed={speed_multiplier}x"
        )

    @property
    def state(self) -> DashboardState:
        """Get current state (thread-safe read)."""
        with self._lock:
            return self._state

    def _update_state(self, **kwargs: object) -> None:
        """Update state atomically (thread-safe write)."""
        with self._lock:
            self._state = self._state.update(**kwargs)

    def warmup(self) -> None:
        """Run warmup phase synchronously.

        Processes all candles before stream_start_index to fill indicator
        buffers (RSI, DXY correlation, structure, VWAP) with historical context.

        This should be called before starting the dashboard to ensure
        HTF bias is populated when dashboard first renders.
        """
        warmup_count = self.data_stream.warmup_bars
        if warmup_count == 0:
            logger.info("No warmup bars available, starting from beginning")
            return

        logger.info(
            f"Starting warmup with {warmup_count:,} bars "
            f"({warmup_count / 60:.1f} hours of data)..."
        )

        # Track boundaries during warmup
        h1_boundaries = 0
        m15_boundaries = 0
        log_interval = max(100, warmup_count // 10)

        for i, (gc_candle, dxy_candle) in enumerate(self.data_stream.get_warmup_candles()):
            # Track boundaries
            if gc_candle.timestamp.minute == 59:
                h1_boundaries += 1
            if gc_candle.timestamp.minute % 15 == 14:
                m15_boundaries += 1

            # Feed to HTF calculator
            self.htf_calculator.update(gc_candle, dxy_candle)

            # Log progress
            if (i + 1) % log_interval == 0:
                progress_pct = ((i + 1) / warmup_count) * 100
                logger.info(f"Warmup progress: {progress_pct:.0f}% ({i + 1:,}/{warmup_count:,} bars)")

        logger.info(
            f"Warmup complete | "
            f"1H bars: {h1_boundaries} | "
            f"15M bars: {m15_boundaries}"
        )

        # Populate initial state with HTF bias from warmup
        htf_bias = self.htf_calculator.get_current_bias()
        features_15m = self.htf_calculator.get_current_features_15m()

        # Get last warmup candle timestamp
        last_idx = self.data_stream.stream_start_index - 1
        if last_idx >= 0:
            last_gc, _ = self.data_stream.get_candle_at(last_idx)
            timestamp = last_gc.timestamp
        else:
            timestamp = None

        self._update_state(
            timestamp=timestamp,
            htf_bias=htf_bias,
            features=features_15m,
        )

        if htf_bias:
            logger.info(
                f"HTF bias ready: {htf_bias.bias} "
                f"(score: {htf_bias.score:.1f}, confidence: {htf_bias.confidence})"
            )
        else:
            logger.warning("HTF bias not available after warmup")

    def start(self) -> None:
        """Start simulation in background thread."""
        if self._running:
            logger.warning("Engine already running")
            return

        self._running = True
        self._update_state(is_simulation_running=True, is_paused=False)

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info("Simulation engine started")

    def stop(self) -> None:
        """Stop simulation."""
        self._running = False
        self._update_state(is_simulation_running=False)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        logger.info("Simulation engine stopped")

    def _run_loop(self) -> None:
        """Main simulation loop (runs in background thread)."""
        base_delay = 60.0  # 1 minute candles

        try:
            while self._running and self.data_stream.has_more():
                # Check if paused
                if self.state.is_paused:
                    time.sleep(0.1)
                    continue

                # Process one tick
                self.tick()

                # Sleep between bars (speed-adjusted)
                if self.data_stream.has_more():
                    delay = base_delay / self.speed_multiplier
                    time.sleep(delay)

        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
        finally:
            self._update_state(is_simulation_running=False)
            self._running = False
            logger.info("Simulation loop ended")

    def tick(self) -> Optional[Signal]:
        """Process one candle and update state.

        This is the core processing method. Can be called directly for
        testing or step-by-step simulation.

        Returns:
            Generated signal (if any), or None
        """
        # Get next candle pair
        candle_pair = self.data_stream.advance()
        if candle_pair is None:
            return None

        gc_candle, dxy_candle = candle_pair

        # Update HTF calculator
        htf_bias = self.htf_calculator.update(gc_candle, dxy_candle)

        # Get current features
        features_15m = self.htf_calculator.get_current_features_15m()

        # Use persisted HTF bias if not updated at this bar
        current_htf_bias = htf_bias or self.state.htf_bias

        # Evaluate session constraints
        session_result = self.session_validator.evaluate(gc_candle.timestamp)

        # Generate signal
        current_signal = None
        if not features_15m.empty and current_htf_bias:
            current_signal = self._generate_signal(
                gc_candle, features_15m, current_htf_bias, session_result.constraints
            )

        # Create price bars
        gc_bar = PriceBar(
            timestamp=gc_candle.timestamp,
            open=gc_candle.open,
            high=gc_candle.high,
            low=gc_candle.low,
            close=gc_candle.close,
            volume=gc_candle.volume,
        )
        dxy_bar = PriceBar(
            timestamp=dxy_candle.timestamp,
            open=dxy_candle.open,
            high=dxy_candle.high,
            low=dxy_candle.low,
            close=dxy_candle.close,
            volume=0.0,
        )

        # Build new state
        new_state = self.state.with_price_bars(gc_bar, dxy_bar)
        new_state = new_state.update(
            timestamp=gc_candle.timestamp,
            features=features_15m,
            htf_bias=current_htf_bias,
            current_signal=current_signal,
            session_constraints={
                "name": session_result.constraints.name if session_result.constraints else None,
                "min_signal_score": getattr(
                    session_result.constraints, "min_signal_score", 0.0
                ) if session_result.constraints else 0.0,
            } if session_result.constraints else None,
            is_session_active=session_result.session_ok,
            simulation_progress=self.data_stream.get_progress(),
        )

        # Check auto-pause condition
        if self._should_auto_pause(current_signal):
            new_state = new_state.update(
                is_paused=True,
                pause_reason="A+ signal detected",
                paused_at_signal=current_signal,
            )
            logger.info(
                f"Auto-pause triggered: A+ {current_signal.direction} signal "
                f"(score={current_signal.score:.1f}, setup={current_signal.setup_type})"
            )

        # Commit state update
        with self._lock:
            self._state = new_state

        return current_signal

    def _should_auto_pause(self, signal: Optional[Signal]) -> bool:
        """Check if should auto-pause on this signal.

        Args:
            signal: Current signal (if any)

        Returns:
            True if should pause
        """
        if not self.auto_pause_on_a_plus:
            return False
        if not signal:
            return False
        if signal.confidence != "A+":
            return False
        if self.state.is_paused:
            return False  # Already paused
        return True

    def _generate_signal(
        self,
        candle: Candle,
        features: pd.Series,
        htf_bias: object,
        constraints: object,
    ) -> Optional[Signal]:
        """Generate trade signal using rule engine.

        Args:
            candle: Current candle
            features: Current features
            htf_bias: Current HTF bias
            constraints: Session constraints

        Returns:
            Signal object or None if no signal
        """
        try:
            # Create a copy to avoid mutating the calculator's internal state
            # get_current_features_15m() returns a reference to self.features_15m
            features = features.copy()
            
            # Ensure required fields
            if "timestamp" not in features:
                features["timestamp"] = candle.timestamp
            if "symbol" not in features:
                features["symbol"] = candle.symbol
            if "timeframe" not in features:
                features["timeframe"] = candle.timeframe

            # Build context
            context = {
                "session_ok": True,
                "enforcer_tier": constraints.name if constraints else "Conservative",
            }

            # Score signal
            signal = score_signal(features, htf_bias, context)

            # Return non-neutral signals only
            if signal and signal.direction != "neutral":
                return signal

        except Exception as e:
            logger.warning(f"Signal generation failed: {e}", exc_info=True)

        return None

    def pause(self, reason: str = "Manual pause") -> None:
        """Pause simulation.

        Args:
            reason: Reason for pause (for logging/display)
        """
        self._update_state(is_paused=True, pause_reason=reason)
        logger.info(f"Simulation paused: {reason}")

    def resume(self) -> None:
        """Resume simulation from pause."""
        was_paused = self.state.is_paused
        self._update_state(is_paused=False, pause_reason=None, paused_at_signal=None)
        if was_paused:
            logger.info("Simulation resumed")

    def step(self) -> Optional[Signal]:
        """Process single step (even when paused).

        Useful for step-through debugging or manual control.

        Returns:
            Generated signal (if any)
        """
        return self.tick()

    def is_running(self) -> bool:
        """Check if engine is running.

        Returns:
            True if simulation thread is active
        """
        return self._running and self.state.is_simulation_running

    def set_speed(self, multiplier: float) -> None:
        """Set simulation speed.

        Args:
            multiplier: Speed multiplier (e.g., 10.0 = 10x speed)
        """
        if multiplier <= 0:
            raise ValueError("Speed multiplier must be positive")
        self.speed_multiplier = multiplier
        self._update_state(simulation_speed=multiplier)
        logger.info(f"Simulation speed set to {multiplier}x")

