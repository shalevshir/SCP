#!/usr/bin/env python3
"""
Analyze trade results from the PostgreSQL database.
Calculates win rate, average R-multiple, total PnL, and other statistics.
"""

import asyncio
import os
from typing import Any

import asyncpg


async def get_trade_statistics() -> dict[str, Any]:
    """Query database and calculate trade statistics."""
    
    # Get connection details from environment or use defaults
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name = os.getenv("POSTGRES_DB", "scp")
    db_user = os.getenv("POSTGRES_USER", "scp")
    db_password = os.getenv("POSTGRES_PASSWORD", "scp_dev_password")
    
    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password,
    )
    
    try:
        # Get overall statistics
        overall_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE state = 'CLOSED') as closed_trades,
                COUNT(*) FILTER (WHERE state = 'OPEN') as open_trades,
                COUNT(*) FILTER (WHERE state = 'INVALIDATED') as invalidated_trades,
                COUNT(*) FILTER (WHERE exit_reason = 'TP_HIT') as wins,
                COUNT(*) FILTER (WHERE exit_reason = 'SL_HIT') as losses,
                COUNT(*) FILTER (WHERE exit_reason NOT IN ('TP_HIT', 'SL_HIT') AND state = 'CLOSED') as other_exits,
                SUM(pnl_points) as total_pnl_points,
                SUM(pnl_dollars) as total_pnl_dollars,
                AVG(pnl_points) as avg_pnl_points,
                AVG(pnl_dollars) as avg_pnl_dollars,
                AVG(r_multiple) as avg_r_multiple,
                MAX(pnl_points) as max_win_points,
                MIN(pnl_points) as max_loss_points,
                MAX(r_multiple) as max_r_multiple,
                MIN(r_multiple) as min_r_multiple
            FROM trades
            WHERE state IN ('CLOSED', 'INVALIDATED')
        """)
        
        # Get statistics by direction
        direction_stats = await conn.fetch("""
            SELECT 
                direction,
                COUNT(*) as trades,
                COUNT(*) FILTER (WHERE exit_reason = 'TP_HIT') as wins,
                COUNT(*) FILTER (WHERE exit_reason = 'SL_HIT') as losses,
                SUM(pnl_points) as total_pnl_points,
                AVG(pnl_points) as avg_pnl_points,
                AVG(r_multiple) as avg_r_multiple
            FROM trades
            WHERE state IN ('CLOSED', 'INVALIDATED')
            GROUP BY direction
            ORDER BY direction
        """)
        
        # Get statistics by setup type
        setup_stats = await conn.fetch("""
            SELECT 
                setup_type,
                COUNT(*) as trades,
                COUNT(*) FILTER (WHERE exit_reason = 'TP_HIT') as wins,
                COUNT(*) FILTER (WHERE exit_reason = 'SL_HIT') as losses,
                SUM(pnl_points) as total_pnl_points,
                AVG(pnl_points) as avg_pnl_points,
                AVG(r_multiple) as avg_r_multiple
            FROM trades
            WHERE state IN ('CLOSED', 'INVALIDATED')
            GROUP BY setup_type
            ORDER BY trades DESC
        """)
        
        # Get statistics by exit reason
        exit_reason_stats = await conn.fetch("""
            SELECT 
                exit_reason,
                COUNT(*) as count,
                AVG(pnl_points) as avg_pnl_points,
                AVG(r_multiple) as avg_r_multiple
            FROM trades
            WHERE state = 'CLOSED' AND exit_reason IS NOT NULL
            GROUP BY exit_reason
            ORDER BY count DESC
        """)
        
        # Get recent trades
        recent_trades = await conn.fetch("""
            SELECT 
                opened_at,
                closed_at,
                direction,
                setup_type,
                entry_price,
                exit_price,
                pnl_points,
                pnl_dollars,
                r_multiple,
                exit_reason
            FROM trades
            WHERE state IN ('CLOSED', 'INVALIDATED')
            ORDER BY opened_at DESC
            LIMIT 20
        """)
        
        return {
            "overall": dict(overall_stats) if overall_stats else {},
            "by_direction": [dict(row) for row in direction_stats],
            "by_setup": [dict(row) for row in setup_stats],
            "by_exit_reason": [dict(row) for row in exit_reason_stats],
            "recent_trades": [dict(row) for row in recent_trades],
        }
    
    finally:
        await conn.close()


def print_results(stats: dict[str, Any]) -> None:
    """Print formatted trade statistics."""
    
    overall = stats["overall"]
    
    if not overall or overall.get("total_trades", 0) == 0:
        print("\n❌ No trades found in database\n")
        return
    
    print("\n" + "=" * 80)
    print("📊 TRADE RESULTS SUMMARY")
    print("=" * 80)
    
    # Overall statistics
    print("\n🎯 OVERALL PERFORMANCE")
    print("-" * 80)
    
    total_trades = overall["total_trades"]
    closed_trades = overall["closed_trades"]
    wins = overall["wins"] or 0
    losses = overall["losses"] or 0
    win_rate = (wins / closed_trades * 100) if closed_trades > 0 else 0
    
    print(f"Total Trades:              {total_trades}")
    print(f"Closed Trades:             {closed_trades}")
    print(f"Open Trades:               {overall['open_trades']}")
    print(f"Invalidated Trades:        {overall['invalidated_trades']}")
    print()
    print(f"Wins (TP Hit):             {wins} ({win_rate:.1f}%)")
    print(f"Losses (SL Hit):           {losses} ({100-win_rate:.1f}%)" if closed_trades > 0 else f"Losses (SL Hit):           {losses}")
    print(f"Other Exits:               {overall['other_exits']}")
    print()
    print(f"Total PnL (Points):        {overall['total_pnl_points']:.2f}" if overall['total_pnl_points'] else "Total PnL (Points):        N/A")
    print(f"Total PnL ($):             ${overall['total_pnl_dollars']:.2f}" if overall['total_pnl_dollars'] else "Total PnL ($):             N/A")
    print(f"Average PnL (Points):      {overall['avg_pnl_points']:.2f}" if overall['avg_pnl_points'] else "Average PnL (Points):      N/A")
    print(f"Average PnL ($):           ${overall['avg_pnl_dollars']:.2f}" if overall['avg_pnl_dollars'] else "Average PnL ($):           N/A")
    print()
    print(f"Average R-Multiple:        {overall['avg_r_multiple']:.2f}R" if overall['avg_r_multiple'] else "Average R-Multiple:        N/A")
    print(f"Best Trade (R):            {overall['max_r_multiple']:.2f}R" if overall['max_r_multiple'] else "Best Trade (R):            N/A")
    print(f"Worst Trade (R):           {overall['min_r_multiple']:.2f}R" if overall['min_r_multiple'] else "Worst Trade (R):           N/A")
    print(f"Best Trade (Points):       {overall['max_win_points']:.2f}" if overall['max_win_points'] else "Best Trade (Points):       N/A")
    print(f"Worst Trade (Points):      {overall['max_loss_points']:.2f}" if overall['max_loss_points'] else "Worst Trade (Points):      N/A")
    
    # Statistics by direction
    if stats["by_direction"]:
        print("\n📈 PERFORMANCE BY DIRECTION")
        print("-" * 80)
        print(f"{'Direction':<12} {'Trades':<8} {'Wins':<15} {'Losses':<8} {'Total PnL':<12} {'Avg PnL':<10} {'Avg R':<10}")
        print("-" * 80)
        for row in stats["by_direction"]:
            trades = row["trades"]
            wins = row["wins"] or 0
            win_rate = (wins / trades * 100) if trades > 0 else 0
            print(
                f"{row['direction'].upper():<12} "
                f"{trades:<8} "
                f"{wins} ({win_rate:.1f}%)"[:15] + " " * (15 - min(15, len(f"{wins} ({win_rate:.1f}%)"))) +
                f"{row['losses'] or 0:<8} "
                f"{row['total_pnl_points']:.2f}"[:12] if row['total_pnl_points'] else "0.00        " +
                f"{row['avg_pnl_points']:.2f}"[:10] if row['avg_pnl_points'] else "0.00      " +
                f"{row['avg_r_multiple']:.2f}R" if row['avg_r_multiple'] else "N/A"
            )
    
    # Statistics by setup type
    if stats["by_setup"]:
        print("\n🎲 PERFORMANCE BY SETUP TYPE")
        print("-" * 80)
        print(f"{'Setup Type':<20} {'Trades':<8} {'Wins':<15} {'Losses':<8} {'Total PnL':<12} {'Avg PnL':<10} {'Avg R':<10}")
        print("-" * 80)
        for row in stats["by_setup"]:
            trades = row["trades"]
            wins = row["wins"] or 0
            win_rate = (wins / trades * 100) if trades > 0 else 0
            setup_type = (row["setup_type"] or "Unknown")[:20]
            total_pnl = f"{row['total_pnl_points']:.2f}" if row['total_pnl_points'] else "0.00"
            avg_pnl = f"{row['avg_pnl_points']:.2f}" if row['avg_pnl_points'] else "0.00"
            avg_r = f"{row['avg_r_multiple']:.2f}R" if row['avg_r_multiple'] else "N/A"
            print(
                f"{setup_type:<20} "
                f"{trades:<8} "
                f"{wins} ({win_rate:.1f}%)"[:15].ljust(15) +
                f"{row['losses'] or 0:<8} "
                f"{total_pnl:<12} "
                f"{avg_pnl:<10} "
                f"{avg_r:<10}"
            )
    
    # Statistics by exit reason
    if stats["by_exit_reason"]:
        print("\n🚪 EXIT REASONS")
        print("-" * 80)
        print(f"{'Exit Reason':<25} {'Count':<8} {'Avg PnL':<12} {'Avg R':<10}")
        print("-" * 80)
        for row in stats["by_exit_reason"]:
            exit_reason = (row["exit_reason"] or "Unknown")[:25]
            avg_pnl = f"{row['avg_pnl_points']:.2f}" if row['avg_pnl_points'] else "0.00"
            avg_r = f"{row['avg_r_multiple']:.2f}R" if row['avg_r_multiple'] else "N/A"
            print(
                f"{exit_reason:<25} "
                f"{row['count']:<8} "
                f"{avg_pnl:<12} "
                f"{avg_r:<10}"
            )
    
    # Recent trades
    if stats["recent_trades"]:
        print("\n📋 RECENT TRADES (Last 20)")
        print("-" * 80)
        print(f"{'Opened':<17} {'Dir':<6} {'Setup':<20} {'Entry':<10} {'Exit':<10} {'PnL':<10} {'R':<8} {'Reason':<15}")
        print("-" * 80)
        for row in stats["recent_trades"]:
            opened = row["opened_at"].strftime("%Y-%m-%d %H:%M") if row["opened_at"] else "N/A"
            direction = (row["direction"].upper() if row["direction"] else "N/A")[:6]
            setup = (row["setup_type"] or "N/A")[:20]
            entry = f"{row['entry_price']:.2f}" if row['entry_price'] else "N/A"
            exit_price = f"{row['exit_price']:.2f}" if row['exit_price'] else "N/A"
            pnl = f"{row['pnl_points']:.2f}" if row['pnl_points'] else "0.00"
            r_mult = f"{row['r_multiple']:.2f}R" if row['r_multiple'] else "N/A"
            reason = (row["exit_reason"] or "N/A")[:15]
            print(
                f"{opened:<17} "
                f"{direction:<6} "
                f"{setup:<20} "
                f"{entry:<10} "
                f"{exit_price:<10} "
                f"{pnl:<10} "
                f"{r_mult:<8} "
                f"{reason:<15}"
            )
    
    print("\n" + "=" * 80 + "\n")


async def main():
    """Main entry point."""
    try:
        print("\n🔍 Analyzing trade results from database...")
        stats = await get_trade_statistics()
        print_results(stats)
    except Exception as e:
        print(f"\n❌ Error analyzing trades: {e}\n")
        raise


if __name__ == "__main__":
    asyncio.run(main())
