# Shir Capital Trading System — Operations Dashboard (Grafana)

> **Primary Question (≤10s):**  
> **“Is the system safe to trade right now?”**
>
> Operator / Enforcer dashboard — not analytics, not performance vanity.

---

## Core Principles (Non‑Negotiable)

- **Top → Bottom = Risk Gradient**
- **Any RED above the fold = STOP TRADING**
- **No scrolling during incidents**
- **One dashboard for all environments**
- **Dashboard mirrors SOP enforcement logic**
- **What is not visible is not enforced**

---

## Global Variables

```
$mode    = dev | test | replay | paper | live
$service = all (default) | <service_name>
```

All panels **must filter by `$mode`**.

---

# ROW 1 — GLOBAL SAFETY STATUS (ALWAYS VISIBLE)

> **If anything here is red, do not look further.**

---

## 1. Trading Enabled

- **Type:** Stat  
- **Metric:**
```
scp_trading_enabled{mode="$mode"}
```
- **Thresholds:**
  - `0` → 🟢 DISABLED
  - `1` → 🔴 ENABLED

Notes:
- `live`: enabled is expected
- `paper/dev/test`: enabled = incident

---

## 2. Unsafe State (Kill Switch)

- **Type:** Stat  
- **Metric:**
```
sum(scp_unsafe_state{mode="$mode"})
```
- **Thresholds:**
  - `0` → 🟢 SAFE
  - `>0` → 🔴 UNSAFE

Rule: Unsafe = trading must be disabled immediately.

---

## 3. Execution Service Up

- **Type:** Stat  
- **Metric:**
```
up{instance="execution:8005"}
```
- **Thresholds:**
  - `1` → 🟢 UP
  - `0` → 🔴 DOWN (CRITICAL)

---

## 4. Trading Halt Reason (SOP Enforcer)

- **Type:** Stat  
- **Metric:**
```
scp_trading_halt_reason{mode="$mode"}
```

Enum values:
- `NONE`
- `PDLL`
- `LOSS_STREAK`
- `FATIGUE`
- `UNSAFE_STATE`
- `CEO_OVERRIDE`

Rule: Any value ≠ `NONE` → **STOP TRADING**

---

## 5. Enforcer Tier (Mandatory)

- **Type:** Stat  
- **Metric:**
```
scp_enforcer_tier{mode="$mode"}
```

Expected values:
- Conservative
- Early Mild
- Mild
- Offensive

Alert if:
- Early Mild active without CEO directive
- Tier incompatible with equity buffer

---

# ROW 2 — MARKET DATA HEALTH

> Most trading incidents start here.

---

## 6. Market Data Lag

- **Type:** Time Series  
- **Metric:**
```
scp_market_data_lag_seconds{mode="$mode"}
```
- **Thresholds:**
  - Paper: `> 1.0s` → 🔴
  - Live: `> 0.5s` → 🔴

Interpretation:
- Flat rising line → feed stalled
- Spikes → provider instability

---

## 7. Data Provider Connected

- **Type:** Stat (repeat by provider)  
- **Metric:**
```
scp_data_provider_connected{mode="$mode"}
```
- **Thresholds:**
  - `1` → 🟢
  - `0` → 🔴

---

## 8. Data Gaps (Last 5m)

- **Type:** Stat  
- **Metric:**
```
increase(scp_data_gaps_detected_total{mode="$mode"}[5m])
```
- **Thresholds:**
  - `0` → 🟢
  - `>0` → 🔴

Rule: Any gap in `live` → immediate trading stop.

---

# ROW 3 — SIGNAL FLOW & SOP QUALITY

> Is the strategy alive and producing A+ setups?

---

## 9. Signals Generated Rate

- **Type:** Time Series  
- **Metric:**
```
rate(scp_signals_generated_total{mode="$mode"}[1m])
```
- **Unit:** signals/min

---

## 10. Signal Rejection Reasons

- **Type:** Stacked Bar  
- **Metric:**
```
increase(scp_signals_rejected_total{mode="$mode"}[5m])
```
- **Stack by:** reason

---

## 11. A+ Quality Gate (Mandatory)

- **Type:** Stat  
- **Metric:**
```
avg(scp_signal_score{mode="$mode"})
```
- **Thresholds:**
  - `>= 8.0` → 🟢 A+
  - `< 8.0` → 🔴 NOT A+

Rule: Below threshold → **do not trade**.

---

## 12. Signal Generation Latency (p95)

- **Type:** Time Series  
- **Metric:**
```
histogram_quantile(
  0.95,
  rate(scp_signal_generation_seconds_bucket{mode="$mode"}[5m])
)
```

---

# ROW 4 — EXECUTION & ORDERS (MONEY ZONE)

> This row decides if you lose money.

---

## 13. Orders Sent vs Filled

- **Type:** Time Series  
- **Metrics:**
```
rate(scp_orders_sent_total{mode="$mode"}[1m])
rate(scp_orders_filled_total{mode="$mode"}[1m])
```

---

## 14. Order Rejections

- **Type:** Bar Chart  
- **Metric:**
```
increase(scp_orders_rejected_total{mode="$mode"}[5m])
```
- **Stack by:** reason

Rule: Any non‑zero in `live` → investigate immediately.

---

## 15. Execution Latency (p95)

- **Type:** Time Series  
- **Metrics:**
```
histogram_quantile(0.95, rate(scp_order_ack_seconds_bucket[5m]))
histogram_quantile(0.95, rate(scp_order_fill_seconds_bucket[5m]))
```

---

# ROW 5 — POSITIONS & RISK

---

## 16. Open Positions

- **Type:** Stat  
- **Metric:**
```
scp_open_positions{mode="$mode"}
```
- **Thresholds:**
  - `<= MAX_ACTIVE_TRADES` → 🟢
  - `> MAX_ACTIVE_TRADES` → 🔴

---

## 17. Daily PnL

- **Type:** Time Series + Stat  
- **Metric:**
```
scp_daily_pnl{mode="$mode"}
```

Annotations:
- Session open
- First trade
- Kill switch activation

---

## 18. Daily Drawdown

- **Type:** Gauge  
- **Metric:**
```
scp_daily_drawdown{mode="$mode"}
```
- **Thresholds:**
  - `< 50% PDLL` → 🟢
  - `50–80%` → 🟠
  - `> 80%` → 🔴

---

# ROW 6 — DEBUG / SECONDARY (COLLAPSED)

> Infrastructure and pipeline diagnostics. Collapsed by default, expand during deep investigations.

---

## 19. HTF Bias Current

- **Type:** Gauge  
- **Metric:**
```
scp_htf_bias_current{mode="$mode"}
```
- **Value mapping:**
  - `1.0` → Bullish
  - `0.0` → Neutral
  - `-1.0` → Bearish

---

## 20. HTF Bias Change Frequency

- **Type:** Stat  
- **Metric:**
```
increase(scp_htf_bias_changes_total{mode="$mode"}[1h])
```
- **Interpretation:**  
  - High frequency (>4/hour) → choppy market
  - Low frequency (<2/hour) → trending market

---

## 21. Loss Streak Current

- **Type:** Stat  
- **Metric:**
```
scp_loss_streak_current{mode="$mode"}
```
- **Thresholds:**
  - `0` → 🟢
  - `1` → 🟠
  - `>= 2` → 🔴

---

## 22. Redis Connectivity

- **Type:** Stat  
- **Metric:**
```
scp_redis_connected{mode="$mode"}
```
- **Thresholds:**
  - `1` → 🟢 CONNECTED
  - `0` → 🔴 DISCONNECTED

---

## 23. Event Processing Latency (p95)

- **Type:** Time Series  
- **Metric:**
```
histogram_quantile(
  0.95,
  rate(scp_event_processing_seconds_bucket{mode="$mode"}[5m])
) by (service)
```
- **Services:** feature-engine, htf-bias, bot-core

---

## 24. Database Query Latency (p95)

- **Type:** Time Series  
- **Metric:**
```
histogram_quantile(
  0.95,
  rate(scp_db_query_seconds_bucket{mode="$mode"}[5m])
) by (service, operation)
```
- **Alert threshold:** `> 1.0s`

---

## 25. Feature Queue Depth

- **Type:** Gauge  
- **Metric:**
```
scp_feature_queue_depth{mode="$mode"}
```
- **Interpretation:**  
  - `0-10` → 🟢 Normal
  - `10-50` → 🟠 Backlog building
  - `> 50` → 🔴 Processing bottleneck

---

## Visual Rules

- 🔴 Red = STOP TRADING
- 🟠 Orange = WATCH
- 🟢 Green = IGNORE
- No pie charts
- Max 3 metrics per panel
- No blue for critical panels

---

## Operator Playbook (Embedded Notes)

- Market data lag breach → disable trading
- Unsafe state ≠ 0 → disable trading
- Signals below A+ → **This is not A+**
- Order rejection spike → broker & risk review
- 2 consecutive losses → halt session
- PDLL hit → liquidate & block

---

## Definition of Done

- [ ] All panels filtered by `$mode`
- [ ] Enforcer tier visible
- [ ] A+ quality gate enforced
- [ ] Halt reasons explicit
- [ ] Live tested via paper
- [ ] Alerts mirror dashboard logic 1:1
- [ ] Reviewed before enabling live trading

---

**Mantra**

> Follow the SOP — nothing changed structurally.  
> If it’s not visible, it’s not enforced.

