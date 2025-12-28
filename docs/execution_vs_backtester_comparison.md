# Execution Microservice vs. Legacy Backtester Replay Loop

Scope: Compare the live execution microservice pipeline under `services/execution/` with the legacy monolithic replay loop in `backtester/replay_loop.py`, focusing on logic, behavior, sequencing, and assumptions that can change outputs, signals, state transitions, timing, and trading outcomes.

## 1) Data Flow & Ordering
- **Legacy**: Single-process, deterministic loop over synchronized GC/DXY DataFrames; HTF bias, guardrails, scoring, and entry all run in one synchronous pass with the “next candle” already known. No message loss, no reordering.
- **Microservice**: Asynchronous consumers on three Redis streams (`signals.pending`, `candles.1m.gc`, `features.1m`). Candles and features are merged and sorted by timestamp, paired with a 5-minute data-time timeout, and periodically cleaned. Unpaired messages can be dropped; ordering depends on arrival and batching. Execution processes only paired candle+features, so missing/late messages can skip exits or executions.
- **Impact**: Divergent fills/exits when messages delay or drop; replay speed or network jitter can change which bars get processed and when confirmations occur.

## 2) Guardrails & Validation
- **Legacy**: Enforces many guardrails locally before scoring/entry (session window, PDLL, daily trade cap, loss-streak/fatigue, DXY availability, seasonality, CEO directives, max concurrent trades, risk ladder sanity). Signals blocked here never reach execution.
- **Microservice**: Execution layer re-checks only PDLL/daily trade limits and max active trades. All other guardrails are assumed enforced upstream by Bot Core; DXY/session/fatigue/seasonality are not revalidated here.
- **Impact**: Any upstream guardrail gap yields trades that the monolith would have blocked, altering trade counts and PDLL timing.

## 3) Entry Execution
- **Legacy**: Executes at the provided `next_candle` open with slippage/commission applied, risk ladder sizing, expansion gates, and VWAP reclaim re-entry protection driven by the streaming structure state machine. Uses HTF/dataset bar indices for gating.
- **Microservice**: Executes all buffered signals at the current paired candle’s open; quantity fixed to 1; no slippage/commission. Confirmation auto-approves on the next bar via service state machine; execution_count gating lives there. Uses a global bar counter (not strict data index).
- **Impact**: Different entry price treatment, sizing, and gating can change fills, PnL, and whether re-entries are blocked.

## 4) Exit & Invalidation
- **Legacy**: Per-bar exit check with full feature context; bars_elapsed tied to actual dataset sequencing; invalidation uses rich feature set. Behavior/invalidation trackers update on every close.
- **Microservice**: Exit checks use `InvalidationChecker.check_all` with bars_elapsed from a global bar counter minus entry snapshot; feature context passed is limited (vwap, rsi, structure_label). No behavior tracker updates here.
- **Impact**: Timing of SL/TP/invalidations can differ when bar counter diverges from true data gaps or when missing feature fields change invalidation logic.

## 5) State Management & Recovery
- **Legacy**: Pure in-memory; deterministic for one run; no restart recovery. Supports `execution_start` warmup (process HTF/structures but block signals before a start time).
- **Microservice**: Persists trades and state machines to DB; on startup restores open trades, daily PnL/trade counts, bar indices (if saved), and reconciles broker positions. Entry timestamps use wall-clock (`datetime.utcnow()`), not data time.
- **Impact**: Post-restart behavior can diverge (orphaned trades, PDLL state restored differently). Wall-clock timestamps affect audits and any time-based analytics.

## 6) Session & Daily Resets
- **Legacy**: Resets daily PnL, PDLL flag, trades_today, structure stats, behavior tracker, and invalidation state on date change; session hours enforced before signals.
- **Microservice**: Resets only PDLL/trade counters on date change via `DailyStateTracker`; no session-hour enforcement here; structure/behavior state not reset at execution layer.
- **Impact**: Trades may execute outside intended hours; daily-limit enforcement around boundaries can differ.

## 7) Defaults & Assumptions
- **Legacy defaults**: Slippage 0.5, commission 5.0, tick_sizes/values applied; PDLL 600; max trades/day 2; sizing via risk ladder; `max_concurrent_trades` default 1.
- **Microservice defaults**: Quantity 1; PDLL 600 points; max trades/day 2; max_active_trades 1; SL buffer 5 ticks; no commission/slippage applied.
- **Impact**: PnL, R-multiples, and PDLL hits will differ due to sizing and fee/slippage treatment.

## 8) VWAP Reclaim State Machine
- **Legacy**: Uses streaming structure tracker; gating and stop-out notifications use dataset bar indices and HTF context; execution_count blocks additional entries.
- **Microservice**: Creates a state machine per signal (`max_confirm_window=10`); auto-confirms on the next bar; expiration/confirmation keyed to a global bar counter; execution_count persisted.
- **Impact**: Confirmation/expiration depends on bar-counter increments and message pairing, so delayed/early messages can flip between execute vs. expire compared to deterministic monolith behavior.

## 9) Data/Time Handling
- **Legacy**: Uses data-time exclusively; bars_elapsed derived from dataset order; warmup supported via `execution_start` (HTF updates but no signals before start).
- **Microservice**: Mixes data-time (for pairing) with wall-clock for entry timestamps; bar counter increments per processed candle, independent of actual time gaps.
- **Impact**: Time-based rules tied to real data gaps or absolute timestamps can diverge (timeouts, expirations, audit timelines).

## 10) Explicit Risks to Trading/Backtest Outcomes
- Dropped or delayed stream messages change which bars are processed, affecting confirmations and exits.
- Missing execution-layer guardrails (session/DXY/fatigue/seasonality) allow trades the monolith blocks.
- Fixed quantity + no slippage/commission alters PnL, R, and PDLL timing.
- Bar-counter timing vs. true data gaps can shift invalidations, SL/TP hits, and expirations.
- Restart recovery (DB + broker reconciliation) introduces states absent in backtests, potentially adding or removing trades after restart.
- Auto-confirmation vs. structured confirmation in the monolith can allow or block VWAP reclaims differently.

## 11) Why Same Inputs Can Diverge
Even with identical input candles/features/signals, asynchronous delivery, reduced guardrail coverage, different pricing/sizing assumptions, bar-counter timing, and restart recovery can produce different entries, exits, and PDLL trajectories, leading to divergent trade counts and PnL between the microservice and the legacy backtester.

