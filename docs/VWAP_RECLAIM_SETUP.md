# VWAP Reclaim Setup - Human Readable Guide

## What is VWAP Reclaim?

A **trend-continuation setup** that triggers when price sweeps away from VWAP (Volume-Weighted Average Price), then returns and "reclaims" it—signaling the prior trend is resuming.

---

## Entry Requirements (ALL must pass)

| Gate | Plain English |
|------|---------------|
| **HTF Structure Available** | The 1-hour structure (HH/HL/LH/LL) must be known—can't trade blind to the bigger picture |
| **HTF Structure Intact** | For longs: 1H must show HH or HL (bullish). For shorts: 1H must show LL or LH (bearish) |
| **Structure Label Exists** | A swing label must be present to manage the trade safely |
| **Prior Excursion from VWAP** | Price must have traveled **0.5–12 ATR away** from VWAP in the last 20 bars—proves this is a real reclaim, not noise |
| **Currently Near VWAP** | Price must now be **within 3 ATR** of VWAP—confirms the reclaim is happening |
| **No Late Reclaim** | If a Break of Structure (BOS) just happened, wait at least 20 bars—avoid entering while structure is still expanding |
| **BOS Direction Alignment** | Any recent BOS must match trade direction, or be old enough (≥20 bars) to ignore |
| **Direction-BOS Alignment** | Recent BOS must agree with trade direction, OR a CHoCH (Change of Character) must override it, OR BOS must be stale (>15 bars) |
| **No HTF Conflict** | Higher-timeframe structure must not be in conflict |
| **VWAP Acceptance** | At least **2 bars** in the last 20 must have been near VWAP—blocks "drive-by" reclaims with no real acceptance |
| **Micro Structure (Longs)** | For longs: micro structure can't be LH or LL (bearish patterns) |
| **Micro Structure (Shorts)** | For shorts: micro structure can't be HH or HL (bullish patterns) |

---

## Scoring Factors (max ~10 points, need 8+ for A+ grade)

| Factor | Weight | What it measures |
|--------|--------|------------------|
| Structure Alignment | 2.5 | How well price structure supports the direction |
| VWAP Relation | 2.0 | Position relative to VWAP |
| RSI State | 1.5 | RSI confirming momentum |
| EMA Stack | 1.5 | Moving averages properly stacked |
| DXY Correlation | 1.0 | Gold-Dollar inverse relationship |
| FVG Alignment | 0.5 | Fair Value Gap support |
| Liquidity Sweep | 0.5 | Liquidity taken before entry |
| HTF Bonus | 0.5 | Extra credit for strong HTF alignment |

---

## In Plain English

> "Enter a VWAP reclaim when price has moved meaningfully away from VWAP (at least 0.5 ATR), then comes back to it (within 3 ATR), while the higher-timeframe trend is still intact. Don't chase late reclaims after a fresh BOS, and make sure price actually spent time accepting VWAP (not just a quick touch). The micro-structure must agree with your direction."

---

## Key Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| BOS Recency Threshold | 15 bars | How old a BOS must be to ignore |
| Clarity High | 0.7 | High structure clarity threshold |
| Clarity Moderate | 0.5 | Moderate structure clarity threshold |
| Clarity Low | 0.4 | Minimum acceptable clarity |
| Range Expansion Ratio | 1.5x | Expansion gate threshold |
| ATR Expansion Threshold | 0.7 | ATR-based expansion detection |
| Displacement Body Ratio | 2.0x | Body size for displacement candles |

---

## Glossary

- **VWAP**: Volume-Weighted Average Price (resets at 08:20 AM ET for Gold futures)
- **ATR**: Average True Range (volatility measure)
- **BOS**: Break of Structure (price breaks a key swing high/low)
- **CHoCH**: Change of Character (trend reversal signal)
- **HTF**: Higher Timeframe (1H in this context)
- **HH/HL**: Higher High / Higher Low (bullish structure)
- **LH/LL**: Lower High / Lower Low (bearish structure)
- **FVG**: Fair Value Gap (imbalance zone)
