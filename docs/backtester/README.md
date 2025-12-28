# Backtester Documentation

This directory contains comprehensive documentation for the Shir Capital backtest system.

---

## Documentation Index

### 📖 [Comprehensive Backtest System Documentation](./comprehensive-backtest-system.md)

**1,225 lines of complete technical documentation covering:**

1. **System Overview** - Architecture, design principles, core components
2. **Architecture & Data Flow** - Pipeline diagrams, data flow visualization
3. **Candle Processing** - BacktestProcessor, incremental feature computation
4. **HTF Bias Calculation** - Multi-timeframe analysis (1H + 15M), streaming vs vectorized
5. **Guardrails & Validation** - Three-layer guardrail system, SOP enforcement
6. **Signal Scoring & Confluence** - Weighted factor model, setup-specific scoring
7. **Risk Management** - Structure-based SL, R-multiple TP, phase-aware Risk Ladder
8. **Trade Simulation & Exits** - Entry execution, exit priority, invalidation rules
9. **State Management** - Session state, behavior tracking, trade-level state
10. **Performance Metrics** - BacktestResults, per-trade metrics, logging

**Read this first** for a deep understanding of how the entire system works.

---

### ⚡ [Quick Reference Guide](./quick-reference.md)

**Condensed reference for rapid lookup:**

- Quick start code examples
- Key thresholds and configuration
- Guardrail rules summary
- Signal scoring factor weights
- Risk management formulas
- Exit priority and invalidations
- HTF bias scoring breakdown
- Common patterns and troubleshooting

**Use this** when you need to quickly look up a specific threshold, formula, or pattern.

---

## Additional Resources

### Component-Specific Documentation

Each major backtester component has its own detailed documentation:

- **[Replay Engine](./replay-engine.md)** - BacktestReplayLoop architecture and flow
- **[Simulator](./simulator.md)** - Trade outcome simulation, exit logic
- **[Trade Object](./trade-object.md)** - Trade lifecycle, SL/TP calculation
- **[Invalidations](./invalidations.md)** - InvalidationChecker rules and logic
- **[Multi-Timeframe Integration](./multi-timeframe-integration.md)** - HTF data sync
- **[Pipeline Integration](./pipeline-integration.md)** - Feature → Signal → Entry → Trade flow

---

## When to Use Which Document

### Scenario 1: First-Time Setup

**Goal**: Understand how to run a backtest from scratch

**Path**:
1. Read [Quick Reference > Quick Start](./quick-reference.md#quick-start)
2. Review [Comprehensive > System Overview](./comprehensive-backtest-system.md#1-system-overview)
3. Follow code examples to run first backtest

---

### Scenario 2: Understanding Guardrails

**Goal**: Figure out why signals are being blocked

**Path**:
1. Check [Quick Reference > Guardrails](./quick-reference.md#guardrails) for summary
2. Read [Comprehensive > Guardrails & Validation](./comprehensive-backtest-system.md#5-guardrails--validation) for details
3. Review logs to identify specific blocking guardrail

---

### Scenario 3: Debugging Signal Scoring

**Goal**: Understand why a setup scored X/10 instead of Y/10

**Path**:
1. Check [Quick Reference > Signal Scoring](./quick-reference.md#signal-scoring) for factor weights
2. Read [Comprehensive > Signal Scoring & Confluence](./comprehensive-backtest-system.md#6-signal-scoring--confluence) for full logic
3. Enable signal logging: `log_signals=True, log_dir="output/signals"`
4. Review JSONL logs for factor-by-factor breakdown

---

### Scenario 4: Fixing Trade Exits

**Goal**: Understand why trades are exiting at specific points

**Path**:
1. Check [Quick Reference > Trade Exits](./quick-reference.md#trade-exits) for priority order
2. Read [Comprehensive > Trade Simulation & Exits](./comprehensive-backtest-system.md#8-trade-simulation--exits) for detailed logic
3. Review [Invalidations](./invalidations.md) for specific invalidation rules
4. Check trade logs for exit_reason

---

### Scenario 5: Modifying Risk Management

**Goal**: Adjust SL/TP calculations or Risk Ladder

**Path**:
1. Check [Quick Reference > Risk Management](./quick-reference.md#risk-management) for formulas
2. Read [Comprehensive > Risk Management](./comprehensive-backtest-system.md#7-risk-management) for full SOP rules
3. Modify `risk_config` or `backtester/trade.py` as needed

---

### Scenario 6: Understanding HTF Bias

**Goal**: Learn how 1H and 15M analysis drives signal generation

**Path**:
1. Check [Quick Reference > HTF Bias Calculation](./quick-reference.md#htf-bias-calculation) for summary
2. Read [Comprehensive > HTF Bias Calculation](./comprehensive-backtest-system.md#4-higher-timeframe-htf-bias-calculation) for full details
3. Review `rule_engine/htf/` module documentation
4. Compare streaming vs vectorized approaches

---

## Documentation Maintenance

### When to Update

Update these documents when:
1. **Major architecture changes** (e.g., new guardrail layer)
2. **SOP rule changes** (e.g., seasonality adjustments)
3. **Scoring model updates** (e.g., new factor weights)
4. **New invalidation rules** (e.g., HTF structure breaks)
5. **Performance optimization** (e.g., streaming vs vectorized)

### How to Update

1. **Comprehensive Documentation**: Update full section with detailed explanation
2. **Quick Reference**: Update corresponding summary or threshold table
3. **Component Docs**: Update specific module documentation if affected
4. **Version Bump**: Increment version number in comprehensive doc header

---

## Key Concepts

### Zero Lookahead Bias

The backtest system **never looks ahead**. Features are computed incrementally, bar-by-bar, exactly as in live trading. This ensures:
- No future data contamination
- Realistic signal generation
- Reproducible results

### Three-Layer Guardrail System

1. **Pre-Signal Guardrails** (Before Scoring): PDLL, daily limits, session time, DXY availability
2. **Behavior Guardrails** (Before Entry): Loss streaks, fatigue, session extension
3. **Validation Engine** (Signal-Level): HTF alignment, DXY structure, risk budget

### Structure-First Philosophy

All SL/TP calculations are **structure-based**, never arbitrary:
- SL: Min/max of confirmation/BOS candles, or sweep extreme
- TP: R-multiple based (2R or 3R) with seasonality adjustments
- Never inside liquidity (FVG, sweep wick, VWAP reclaim)

### A+ Only Execution

Only signals scoring **≥ 8.0** ("A+" confidence) are executed. This threshold ensures:
- High-quality setups only
- Strong confluence across multiple factors
- HTF alignment (bonus applied)
- SOP compliance (all validations pass)

---

## FAQ

### Q: Why are no signals generated?

**A**: Check guardrails first:
1. PDLL hit? (`_pdll_hit` flag)
2. Loss streak? (consecutive_losses ≥ max_losses)
3. Outside session time? (not 10:00-13:00 ILT)
4. DXY data missing? (dxy_corr is None/NaN)
5. Review logs for specific blocking reason

### Q: Why are A+ signals not executing?

**A**: Check entry execution:
1. Next candle available? (end of data?)
2. Active trade already open? (max 1 at a time)
3. Review EntryExecution list for rejection_reason

### Q: How to increase signal count?

**A**: Adjust market_state or risk_config:
1. Set `tier_active` to "Mild" or "Offensive"
2. Increase `max_trades_per_day`
3. Relax seasonality constraints (if applicable)
4. **Warning**: Only adjust if aligned with CEO directives

### Q: How to debug HTF bias calculation?

**A**: Enable detailed logging:
1. Use `htf_approach="streaming"` for bar-by-bar logs
2. Review `rule_engine/htf/streaming.py` logs
3. Check 1H/15M bar close events
4. Verify structure detection (BOS/CHoCH/swings)

### Q: Why are trades hitting SL immediately?

**A**: Check SL calculation:
1. Are confirmation_candle and bos_candle correct?
2. Is SL too tight (structure too close to entry)?
3. Review `calculate_stop_loss()` logic in `backtester/trade.py`
4. Check if liquidity zones were avoided

---

## Contributing

When contributing to the backtest system:

1. **Follow TDD**: Write failing tests first, then implement
2. **Update Documentation**: Update comprehensive + quick reference docs
3. **Log Extensively**: Add informative log messages for debugging
4. **Maintain SOP Compliance**: Never bypass guardrails without CEO approval
5. **Preserve Determinism**: Ensure reproducible results (no randomness)
6. **Test Edge Cases**: Zero risk, NaN values, end of data, etc.

---

## Version History

- **v2.0** (Dec 2025): Complete rewrite with comprehensive documentation
- **v1.5** (Nov 2025): HTF integration, multi-timeframe sync
- **v1.0** (Oct 2025): Initial backtest system

---

**Need help?** Start with the [Quick Reference](./quick-reference.md) or dive into [Comprehensive Documentation](./comprehensive-backtest-system.md).











