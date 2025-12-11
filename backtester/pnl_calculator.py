"""PnL calculator - converts point-based PnL to dollar amounts with costs.

This module provides functions to calculate profit and loss in dollar terms,
including:
- Gross PnL (before costs)
- Slippage costs (simulated market impact)
- Commission costs (broker fees)
- Net PnL (after all costs)

Following Shir Capital SOP requirements for realistic backtesting.
"""

from common.logger import get_logger

logger = get_logger(__name__)


def compute_slippage(atr: float | None = None, order_type: str = "market") -> int:
    """PATCH PART 5: Compute slippage based on volatility with realistic ATR thresholds.
    
    This function provides dynamic slippage estimation based on ATR (Average True Range)
    using thresholds calibrated for realistic market impact. Replaces unrealistic fixed
    slippage values.
    
    Args:
        atr: Average True Range in price points (e.g., 0.8 = 8 ticks for GC).
             If None, uses default for normal conditions.
        order_type: Order type ("market" or "limit"). Limit orders have no slippage.
        
    Returns:
        Slippage in ticks (0-4 range)
        
    Example:
        >>> # Calm market: ATR = 0.7 points
        >>> slippage = compute_slippage(0.7, order_type="market")
        >>> print(slippage)  # 1 tick
        >>> 
        >>> # Normal market: ATR = 1.2 points
        >>> slippage = compute_slippage(1.2, order_type="market")
        >>> print(slippage)  # 2 ticks
        >>> 
        >>> # High volatility: ATR = 2.0 points
        >>> slippage = compute_slippage(2.0, order_type="market")
        >>> print(slippage)  # 4 ticks
        >>>
        >>> # Limit orders: no slippage
        >>> slippage = compute_slippage(1.0, order_type="limit")
        >>> print(slippage)  # 0 ticks
    """
    if order_type == "limit":
        return 0
    
    if atr is None:
        # Default: 2 ticks in normal conditions when ATR not available
        return 2
    
    # PATCH PART 5: Updated ATR thresholds for realistic slippage
    if atr < 0.8:       # Calm market (< 8 ticks)
        return 1
    elif atr < 1.6:     # Normal market (< 16 ticks)
        return 2
    else:               # High volatility (>= 16 ticks)
        return 4


def compute_slippage_ticks(atr_5: float | None = None, tick_size: float = 0.1) -> int:
    """Compute slippage based on market volatility.
    
    Provides dynamic slippage estimation based on ATR (Average True Range) to
    simulate realistic market impact. In calm markets, slippage is minimal (1 tick),
    while in volatile markets it can be up to 4-5 ticks.
    
    Args:
        atr_5: 5-period ATR (Average True Range) in price points.
               If None, uses default slippage for normal conditions.
        tick_size: Tick size for the instrument (e.g., 0.1 for GC)
        
    Returns:
        Slippage in ticks (1-5 range)
        
    Example:
        >>> # Calm market: ATR = 2.0 points = 20 ticks
        >>> slippage = compute_slippage_ticks(2.0, 0.1)
        >>> print(slippage)  # 1 tick
        >>> 
        >>> # Normal market: ATR = 5.0 points = 50 ticks
        >>> slippage = compute_slippage_ticks(5.0, 0.1)
        >>> print(slippage)  # 2 ticks
        >>> 
        >>> # Volatile market: ATR = 10.0 points = 100 ticks
        >>> slippage = compute_slippage_ticks(10.0, 0.1)
        >>> print(slippage)  # 4 ticks
    """
    if atr_5 is None:
        # Default: 2 ticks in normal conditions when ATR not available
        return 2
    
    # Convert ATR from price points to ticks
    atr_ticks = atr_5 / tick_size
    
    # Dynamic slippage based on volatility bands
    if atr_ticks < 30:      # Calm market (ATR < 3.0 points for GC)
        return 1
    elif atr_ticks < 80:    # Normal market (ATR < 8.0 points for GC)
        return 2
    else:                   # High volatility (ATR >= 8.0 points for GC)
        return 4


def calculate_gross_pnl(
    entry_price: float,
    exit_price: float,
    direction: str,
    contracts: int,
    tick_value: float,
    tick_size: float,
) -> float:
    """Calculate gross PnL in dollars before costs.

    Converts point-based price movement to dollar amounts using symbol-specific
    tick values. This represents theoretical PnL before slippage and commission.

    Args:
        entry_price: Entry price
        exit_price: Exit price
        direction: Trade direction ("long" or "short")
        contracts: Number of contracts traded
        tick_value: Dollar value per tick (e.g., $10 for GC)
        tick_size: Minimum price increment (e.g., 0.1 for GC)

    Returns:
        Gross PnL in dollars (positive for profit, negative for loss)

    Example:
        >>> # Long trade: bought at 2650, sold at 2665
        >>> gross_pnl = calculate_gross_pnl(2650.0, 2665.0, "long", 1, 10.0, 0.1)
        >>> print(gross_pnl)  # $1,500
    """
    if contracts == 0:
        return 0.0

    # Calculate price movement in points
    if direction == "long":
        price_change = exit_price - entry_price
    else:  # short
        price_change = entry_price - exit_price

    # Convert points to dollars
    # Formula: price_change_in_points × (tick_value / tick_size) × contracts
    points = price_change
    gross_pnl = points * (tick_value / tick_size) * contracts

    logger.debug(
        f"Gross PnL calculated: {gross_pnl:.2f} "
        f"(direction={direction}, points={points:.1f}, contracts={contracts})"
    )

    return gross_pnl


def calculate_slippage_cost(
    direction: str,
    contracts: int,
    slippage_ticks: float,
    tick_value: float,
) -> float:
    """Calculate slippage cost in dollars.

    Slippage represents the difference between expected and actual execution price
    due to market conditions. Applied on both entry and exit.

    Slippage is ALWAYS a cost (negative value).

    Args:
        direction: Trade direction ("long" or "short")
        contracts: Number of contracts traded
        slippage_ticks: Number of ticks of slippage (e.g., 1.5)
        tick_value: Dollar value per tick (e.g., $10 for GC)

    Returns:
        Slippage cost in dollars (always negative or zero)

    Example:
        >>> # 1.5 ticks of slippage on GC
        >>> slippage = calculate_slippage_cost("long", 1, 1.5, 10.0)
        >>> print(slippage)  # -$15
    """
    if contracts == 0 or slippage_ticks == 0:
        return 0.0

    # Slippage applies on both entry and exit, but we model it as single value
    # Slippage is always a cost (negative)
    slippage_cost = -abs(slippage_ticks * tick_value * contracts)

    logger.debug(
        f"Slippage cost calculated: {slippage_cost:.2f} "
        f"(ticks={slippage_ticks}, contracts={contracts})"
    )

    return slippage_cost


def calculate_commission_cost(
    contracts: int,
    commission_per_contract: float,
) -> float:
    """Calculate total commission cost.

    Commission is charged by the broker on both entry and exit trades.
    Total commission = commission_per_contract × 2 (entry + exit) × contracts.

    Args:
        contracts: Number of contracts traded
        commission_per_contract: Commission per contract per side (e.g., $5)

    Returns:
        Total commission cost (always negative or zero)

    Example:
        >>> # $5 per contract, 1 contract
        >>> commission = calculate_commission_cost(1, 5.0)
        >>> print(commission)  # -$10 (entry + exit)
    """
    if contracts == 0:
        return 0.0

    # Commission on both entry and exit
    total_commission = -(commission_per_contract * 2 * contracts)

    logger.debug(
        f"Commission cost calculated: {total_commission:.2f} "
        f"(rate=${commission_per_contract}/contract, contracts={contracts})"
    )

    return total_commission


def calculate_net_pnl(
    entry_price: float,
    exit_price: float,
    direction: str,
    contracts: int,
    tick_value: float,
    tick_size: float,
    slippage_ticks: float,
    commission_per_contract: float,
) -> dict:
    """Calculate complete PnL breakdown with all costs.

    This is the main function that computes:
    1. Gross PnL (theoretical profit/loss)
    2. Slippage cost (market impact)
    3. Commission cost (broker fees)
    4. Net PnL (actual realized profit/loss)

    Args:
        entry_price: Entry price
        exit_price: Exit price
        direction: Trade direction ("long" or "short")
        contracts: Number of contracts traded
        tick_value: Dollar value per tick (e.g., $10 for GC)
        tick_size: Minimum price increment (e.g., 0.1 for GC)
        slippage_ticks: Number of ticks of slippage (e.g., 1.5)
        commission_per_contract: Commission per contract (e.g., $5)

    Returns:
        Dictionary containing:
        - gross_pnl: Gross PnL in dollars
        - slippage_cost: Slippage cost (negative)
        - commission_cost: Commission cost (negative)
        - net_pnl: Net PnL after all costs
        - pnl_per_contract: Net PnL divided by number of contracts

    Example:
        >>> # Winning long trade: 2650 → 2665
        >>> pnl = calculate_net_pnl(2650.0, 2665.0, "long", 1, 10.0, 0.1, 1.5, 5.0)
        >>> print(f"Gross: ${pnl['gross_pnl']}")  # $1,500
        >>> print(f"Net: ${pnl['net_pnl']}")  # $1,475
    """
    # Calculate components
    gross_pnl = calculate_gross_pnl(
        entry_price, exit_price, direction, contracts, tick_value, tick_size
    )

    slippage_cost = calculate_slippage_cost(
        direction, contracts, slippage_ticks, tick_value
    )

    commission_cost = calculate_commission_cost(contracts, commission_per_contract)

    # Calculate net PnL
    net_pnl = gross_pnl + slippage_cost + commission_cost

    # Calculate per-contract PnL
    pnl_per_contract = net_pnl / contracts if contracts > 0 else 0.0

    logger.info(
        f"PnL breakdown: gross=${gross_pnl:.2f}, slippage={slippage_cost:.2f}, "
        f"commission={commission_cost:.2f}, net=${net_pnl:.2f} "
        f"(direction={direction}, contracts={contracts})"
    )

    return {
        "gross_pnl": gross_pnl,
        "slippage_cost": slippage_cost,
        "commission_cost": commission_cost,
        "net_pnl": net_pnl,
        "pnl_per_contract": pnl_per_contract,
    }
