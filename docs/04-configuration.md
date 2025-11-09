# Configuration

## Overview

All system parameters are defined in `config/core.yaml`. This centralized configuration allows for:

- Version-controlled parameter management
- Environment-specific overrides
- Governance and auditability
- Easy tuning without code changes

## Configuration File

**Location:** `config/core.yaml`

**Format:** YAML

**Validation:** Future integration with pydantic for type-safe loading

## Configuration Sections

### System Configuration

```yaml
system:
  data_path: "./data/"           # Base folder for market data
  log_path: "./logs/"            # Location for runtime & audit logs
  db_path: "sqlite:///db/core.db" # Database connection string
  timezone: "UTC"                # Default timezone for alignment
  timeframes: ["1m", "5m", "15m"] # Active resolutions
```

**Purpose:** Core system paths and settings.

**Notes:**
- `data_path` and `log_path` are relative to project root
- `db_path` uses SQLAlchemy-style connection strings
- `timeframes` list defines which resolutions to process

### Assets Configuration

```yaml
assets:
  symbols: ["GC", "DXY"]         # Tracked instruments
  broker: "SIMULATION"           # Placeholder for API source
  start_date: "2022-01-01"       # Back-test start
  end_date: "2025-12-31"         # Back-test end
```

**Purpose:** Market data and asset settings.

**Symbols:**
- `GC` - Gold futures (COMEX)
- `DXY` - U.S. Dollar Index

**Notes:**
- `broker` is a placeholder (no live API in Phase 1)
- Date range used for backtesting simulations

### Risk Framework

```yaml
risk:
  phases: ["Startup", "Growth", "Scaling", "Institutional"]
  startup_risk_per_trade: 350    # USD value placeholder
  growth_risk_per_trade: 600     # USD value placeholder
  daily_drawdown_limit: 600      # PDLL stub
  rr_target: 3.0                 # Default R:R goal
```

**Purpose:** Risk management parameters aligned with SOP.

**Risk Phases:**
- **Startup:** 0-5K buffer, $350/trade, $600 daily max
- **Growth:** 5-15K buffer, $450-600/trade, $900-1K daily max
- **Scaling:** 15-40K buffer, $700-1K/trade, $1.5-2K daily max
- **Institutional:** 40K+ buffer, $1.2K+/trade, $2.5K+ daily max

**Notes:**
- All values are placeholders (no live trading in Phase 1)
- `rr_target` represents the minimum Risk:Reward ratio (3:1)

### Governance Tiers

```yaml
governance:
  tiers:
    - name: "Conservative"
      max_contracts: 1
      max_trades_per_day: 2
      mode: "Baseline"
    - name: "Early Mild"
      max_contracts: 1
      max_trades_per_day: 2
      mode: "CEO Directive"
    - name: "Mild"
      max_contracts: 2
      max_trades_per_day: 3
      mode: "Standard"
    - name: "Offensive"
      max_contracts: 3
      max_trades_per_day: 4
      mode: "Advanced"
```

**Purpose:** Enforcer tier definitions for capital discipline.

**Tier Descriptions:**
- **Conservative:** Baseline safety mode
- **Early Mild:** CEO Directive activation (≥62% win rate required)
- **Mild:** Standard operational mode
- **Offensive:** Advanced/aggressive mode

**Notes:**
- Tiers control maximum position size and daily trade limits
- Mode field indicates operational context

### Backtest Configuration

```yaml
backtest:
  initial_balance: 100000        # Starting equity for simulation
  commission_per_trade: 5        # Mock commission
  slippage_points: 0.5           # Artificial slippage for testing
  mock_strategy: true            # Dummy logic switch
```

**Purpose:** Backtesting simulation parameters.

**Notes:**
- `initial_balance` in USD
- `commission_per_trade` in USD per round trip
- `slippage_points` in price points (simulated execution cost)
- `mock_strategy` flag for placeholder logic (Phase 1)

## Loading Configuration

### Current Status (Phase 1)

Configuration file exists but no loader implemented yet. Future implementation will:

1. Load YAML file
2. Validate with pydantic models
3. Provide type-safe access to parameters
4. Support environment variable overrides

### Future Implementation Example

```python
from scp.common.config import load_config

config = load_config("config/core.yaml")
print(config.system.data_path)  # Type-safe access
```

## Environment Variables (Future)

Planned support for environment variable overrides:

```bash
export SCP_DATA_PATH="/custom/data/path"
export SCP_LOG_LEVEL="DEBUG"
export SCP_DB_PATH="postgresql://user:pass@host/db"
```

## Configuration Validation

Future validation will ensure:
- Required parameters present
- Type correctness (numbers, strings, lists)
- Value ranges (e.g., positive numbers, valid dates)
- Cross-parameter consistency

## Version Control

Configuration files are version-controlled to:
- Track parameter changes over time
- Enable rollback to previous settings
- Audit parameter modifications
- Support configuration branching for experiments

## Best Practices

1. **Never commit secrets:** Use environment variables for sensitive data
2. **Document changes:** Update configuration docs when adding parameters
3. **Test changes:** Validate configuration before committing
4. **Use defaults:** Provide sensible defaults for all parameters
5. **Version parameters:** Consider versioning config schema for migrations

## Next Steps

- Implement configuration loader with pydantic validation
- Add environment variable support
- Create configuration schema documentation
- Add configuration validation tests

