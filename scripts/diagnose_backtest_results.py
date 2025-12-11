#!/usr/bin/env python3
"""
Diagnostic script to analyze backtest results and answer critical questions about signal generation.

Questions addressed:
1. How many candles per session have structure_label == 'NA'? Is structure too sparse?
2. Is DXY chop detection setting htf_bias = neutral too often?
3. Is min_score being applied before or after factor normalization?
4. Does VWAP_FADE scoring correctly compute rejection_candle and volume_spike?
5. Is seasonality gating blocking setups incorrectly?
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd


def load_results(filepath: Path) -> Dict[str, Any]:
    """Load backtest results JSON."""
    with open(filepath, "r") as f:
        return json.load(f)


def analyze_structure_labels(data_dir: Path, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Question 1: Analyze structure_label distribution across sessions.
    
    Returns statistics on NA vs valid structure labels per session.
    """
    print("\n" + "=" * 80)
    print("QUESTION 1: Structure Label Analysis")
    print("=" * 80)
    
    # Load the raw OHLCV data to check structure labels
    gc_files = sorted((data_dir / "gc").glob("*.parquet"))
    
    if not gc_files:
        return {"error": "No GC data files found"}
    
    structure_stats = []
    
    for file in gc_files:
        df = pd.read_parquet(file)
        
        if "structure_label" not in df.columns:
            print(f"⚠️  WARNING: structure_label column not found in {file.name}")
            continue
        
        # Filter by date range
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df[(df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)]
        
        if df.empty:
            continue
        
        # Group by session (day)
        df["date"] = df["timestamp"].dt.date
        
        for date, group in df.groupby("date"):
            total = len(group)
            na_count = (group["structure_label"] == "NA").sum() + group["structure_label"].isna().sum()
            na_percent = (na_count / total * 100) if total > 0 else 0
            
            structure_stats.append({
                "date": str(date),
                "total_candles": total,
                "na_count": na_count,
                "valid_count": total - na_count,
                "na_percent": na_percent
            })
    
    if not structure_stats:
        print("⚠️  No structure data found in date range")
        return {"error": "No data in range"}
    
    df_stats = pd.DataFrame(structure_stats)
    
    avg_na_percent = df_stats["na_percent"].mean()
    max_na_percent = df_stats["na_percent"].max()
    min_na_percent = df_stats["na_percent"].min()
    
    print(f"\n📊 Structure Label Statistics:")
    print(f"   Average NA%: {avg_na_percent:.1f}%")
    print(f"   Max NA%: {max_na_percent:.1f}%")
    print(f"   Min NA%: {min_na_percent:.1f}%")
    print(f"   Sessions analyzed: {len(structure_stats)}")
    
    if avg_na_percent > 30:
        print(f"\n🚨 CRITICAL: Average NA% ({avg_na_percent:.1f}%) exceeds 30% threshold!")
        print("   This will cause signals to drop to zero.")
    else:
        print(f"\n✅ Average NA% ({avg_na_percent:.1f}%) is within acceptable range (<30%)")
    
    # Show worst days
    print("\n📉 Days with highest NA% (top 5):")
    worst_days = df_stats.nlargest(5, "na_percent")
    for _, row in worst_days.iterrows():
        print(f"   {row['date']}: {row['na_percent']:.1f}% NA ({row['na_count']}/{row['total_candles']} candles)")
    
    return {
        "avg_na_percent": avg_na_percent,
        "max_na_percent": max_na_percent,
        "min_na_percent": min_na_percent,
        "sessions": structure_stats
    }


def analyze_htf_bias_distribution(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Question 2: Analyze HTF bias distribution across all signals.
    
    Check if DXY chop detection is setting htf_bias = neutral too often.
    """
    print("\n" + "=" * 80)
    print("QUESTION 2: HTF Bias Distribution Analysis")
    print("=" * 80)
    
    bias_counter = Counter()
    bias_by_setup = defaultdict(Counter)
    
    # Analyze trades (executed signals)
    for trade in results.get("trades", []):
        signal = trade.get("entry_execution", {}).get("signal", {})
        htf_bias = signal.get("htf_bias", "unknown")
        setup_type = signal.get("setup_type", "unknown")
        
        bias_counter[htf_bias] += 1
        bias_by_setup[setup_type][htf_bias] += 1
    
    total_signals = sum(bias_counter.values())
    
    if total_signals == 0:
        print("⚠️  No signals found in results - checking if this is the problem!")
        print("   This suggests signals are being filtered out before execution.")
        return {"error": "No signals found", "total_signals": 0}
    
    print(f"\n📊 HTF Bias Distribution (from {total_signals} executed signals):")
    
    for bias, count in bias_counter.most_common():
        percent = (count / total_signals * 100) if total_signals > 0 else 0
        print(f"   {bias}: {count} ({percent:.1f}%)")
    
    neutral_percent = (bias_counter["neutral"] / total_signals * 100) if total_signals > 0 else 0
    
    if neutral_percent > 60:
        print(f"\n🚨 CRITICAL: Neutral bias ({neutral_percent:.1f}%) exceeds 60% threshold!")
        print("   DXY chop detection is too aggressive - system will collapse.")
    else:
        print(f"\n✅ Neutral bias ({neutral_percent:.1f}%) is within acceptable range (<60%)")
    
    # Breakdown by setup type
    print("\n📊 HTF Bias by Setup Type:")
    for setup_type, counter in bias_by_setup.items():
        print(f"\n   {setup_type}:")
        for bias, count in counter.most_common():
            percent = (count / sum(counter.values()) * 100) if sum(counter.values()) > 0 else 0
            print(f"      {bias}: {count} ({percent:.1f}%)")
    
    return {
        "bias_distribution": dict(bias_counter),
        "neutral_percent": neutral_percent,
        "total_signals": total_signals,
        "by_setup": {k: dict(v) for k, v in bias_by_setup.items()}
    }


def analyze_scoring_factors(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Question 3 & 4: Analyze scoring factors to detect normalization issues
    and check if rejection_candle and volume_spike are always 0.0.
    """
    print("\n" + "=" * 80)
    print("QUESTION 3 & 4: Scoring Factor Analysis")
    print("=" * 80)
    
    factor_stats = defaultdict(list)
    zero_factors = defaultdict(int)
    
    for trade in results.get("trades", []):
        signal = trade.get("entry_execution", {}).get("signal", {})
        factors = signal.get("factors", {})
        score = signal.get("score", 0)
        setup_type = signal.get("setup_type", "unknown")
        
        for factor_name, factor_value in factors.items():
            factor_stats[factor_name].append(factor_value)
            if factor_value == 0.0:
                zero_factors[factor_name] += 1
    
    if not factor_stats:
        print("⚠️  No factor data found in results")
        return {"error": "No factor data"}
    
    print("\n📊 Factor Statistics:")
    
    for factor_name, values in sorted(factor_stats.items()):
        avg = sum(values) / len(values) if values else 0
        min_val = min(values) if values else 0
        max_val = max(values) if values else 0
        zeros = zero_factors[factor_name]
        zero_percent = (zeros / len(values) * 100) if values else 0
        
        print(f"\n   {factor_name}:")
        print(f"      Range: [{min_val:.2f}, {max_val:.2f}]")
        print(f"      Average: {avg:.2f}")
        print(f"      Zeros: {zeros}/{len(values)} ({zero_percent:.1f}%)")
        
        if zero_percent == 100:
            print(f"      🚨 CRITICAL: {factor_name} is ALWAYS 0.0!")
    
    # Check VWAP_FADE specific factors
    print("\n🔍 VWAP_FADE Critical Factors:")
    rejection_candle_zeros = zero_factors.get("rejection_candle", 0)
    volume_spike_zeros = zero_factors.get("volume_spike", 0)
    total_signals = len(results.get("trades", []))
    
    if total_signals > 0:
        rej_zero_percent = (rejection_candle_zeros / total_signals * 100)
        vol_zero_percent = (volume_spike_zeros / total_signals * 100)
        
        print(f"   rejection_candle: {rejection_candle_zeros}/{total_signals} zeros ({rej_zero_percent:.1f}%)")
        print(f"   volume_spike: {volume_spike_zeros}/{total_signals} zeros ({vol_zero_percent:.1f}%)")
        
        if rej_zero_percent > 80:
            print(f"\n   🚨 CRITICAL: rejection_candle is almost always 0.0!")
            print(f"      This prevents VWAP_FADE scores from exceeding cutoff.")
        
        if vol_zero_percent > 80:
            print(f"\n   🚨 CRITICAL: volume_spike is almost always 0.0!")
            print(f"      This prevents VWAP_FADE scores from exceeding cutoff.")
    
    # Check if factors sum makes sense
    print("\n📊 Score Composition Analysis:")
    for trade in results.get("trades", []):
        signal = trade.get("entry_execution", {}).get("signal", {})
        factors = signal.get("factors", {})
        score = signal.get("score", 0)
        setup_type = signal.get("setup_type", "unknown")
        
        factor_sum = sum(factors.values())
        
        print(f"\n   Signal at {signal.get('timestamp')} ({setup_type}):")
        print(f"      Final score: {score:.1f}")
        print(f"      Factor sum: {factor_sum:.1f}")
        print(f"      Factors: {factors}")
        
        # Only show first few to avoid spam
        if results.get("trades", []).index(trade) >= 2:
            print(f"\n   ... (showing first 3 signals only)")
            break
    
    return {
        "factor_stats": {k: {
            "avg": sum(v) / len(v) if v else 0,
            "min": min(v) if v else 0,
            "max": max(v) if v else 0,
            "zeros": zero_factors[k],
            "zero_percent": (zero_factors[k] / len(v) * 100) if v else 0
        } for k, v in factor_stats.items()},
        "zero_factors": dict(zero_factors)
    }


def analyze_seasonality_gating(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Question 5: Check if seasonality gating is blocking setups incorrectly.
    
    Look at seasonality factor values and setup_allowed_in_season flags.
    """
    print("\n" + "=" * 80)
    print("QUESTION 5: Seasonality Gating Analysis")
    print("=" * 80)
    
    seasonality_stats = []
    blocked_count = 0
    
    for trade in results.get("trades", []):
        signal = trade.get("entry_execution", {}).get("signal", {})
        validation_flags = signal.get("validation_flags", {})
        factors = signal.get("factors", {})
        
        seasonality_factor = factors.get("seasonality", 1.0)
        allowed_in_season = validation_flags.get("setup_allowed_in_season", True)
        timestamp = signal.get("timestamp", "unknown")
        setup_type = signal.get("setup_type", "unknown")
        
        seasonality_stats.append({
            "timestamp": timestamp,
            "setup_type": setup_type,
            "seasonality_factor": seasonality_factor,
            "allowed_in_season": allowed_in_season
        })
        
        if not allowed_in_season:
            blocked_count += 1
    
    if not seasonality_stats:
        print("⚠️  No seasonality data found in results")
        return {"error": "No data"}
    
    df_stats = pd.DataFrame(seasonality_stats)
    
    avg_seasonality = df_stats["seasonality_factor"].mean()
    min_seasonality = df_stats["seasonality_factor"].min()
    blocked_percent = (blocked_count / len(seasonality_stats) * 100) if seasonality_stats else 0
    
    print(f"\n📊 Seasonality Statistics:")
    print(f"   Average seasonality factor: {avg_seasonality:.2f}")
    print(f"   Minimum seasonality factor: {min_seasonality:.2f}")
    print(f"   Blocked by seasonality: {blocked_count}/{len(seasonality_stats)} ({blocked_percent:.1f}%)")
    
    if blocked_percent > 20:
        print(f"\n🚨 CRITICAL: {blocked_percent:.1f}% of signals blocked by seasonality!")
        print("   Seasonality gating may be too restrictive for Nov-Dec window.")
    else:
        print(f"\n✅ Seasonality gating impact ({blocked_percent:.1f}%) is reasonable")
    
    # Show factor distribution
    print("\n📊 Seasonality Factor Distribution:")
    print(f"   < 0.5: {(df_stats['seasonality_factor'] < 0.5).sum()}")
    print(f"   0.5 - 0.7: {((df_stats['seasonality_factor'] >= 0.5) & (df_stats['seasonality_factor'] < 0.7)).sum()}")
    print(f"   0.7 - 0.9: {((df_stats['seasonality_factor'] >= 0.7) & (df_stats['seasonality_factor'] < 0.9)).sum()}")
    print(f"   >= 0.9: {(df_stats['seasonality_factor'] >= 0.9).sum()}")
    
    # Check if low seasonality is causing scores to drop below cutoff
    low_seasonality = df_stats[df_stats["seasonality_factor"] < 0.6]
    if not low_seasonality.empty:
        print(f"\n⚠️  {len(low_seasonality)} signals had seasonality factor < 0.6:")
        for _, row in low_seasonality.head(5).iterrows():
            print(f"      {row['timestamp']} ({row['setup_type']}): {row['seasonality_factor']:.2f}")
    
    return {
        "avg_seasonality": avg_seasonality,
        "min_seasonality": min_seasonality,
        "blocked_count": blocked_count,
        "blocked_percent": blocked_percent,
        "total_signals": len(seasonality_stats)
    }


def main():
    """Run all diagnostic analyses."""
    if len(sys.argv) < 2:
        print("Usage: python diagnose_backtest_results.py <results_json_path> [data_dir] [start_date] [end_date]")
        sys.exit(1)
    
    results_path = Path(sys.argv[1])
    data_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./data/gc_dx_ohlcv")
    start_date = sys.argv[3] if len(sys.argv) > 3 else "2025-11-01"
    end_date = sys.argv[4] if len(sys.argv) > 4 else "2025-11-30"
    
    if not results_path.exists():
        print(f"❌ Results file not found: {results_path}")
        sys.exit(1)
    
    print("🔍 Loading backtest results...")
    results = load_results(results_path)
    
    print(f"\n📈 Backtest Overview:")
    print(f"   Total trades: {results.get('metadata', {}).get('total_trades', 0)}")
    print(f"   Win rate: {results.get('metadata', {}).get('win_rate', 0):.1f}%")
    print(f"   Total PnL: ${results.get('metadata', {}).get('total_pnl_dollars', 0):.2f}")
    
    # Run all analyses
    print("\n" + "=" * 80)
    print("RUNNING DIAGNOSTIC ANALYSES")
    print("=" * 80)
    
    results_dict = {}
    
    # Question 1: Structure labels
    if data_dir.exists():
        results_dict["structure_analysis"] = analyze_structure_labels(data_dir, start_date, end_date)
    else:
        print(f"\n⚠️  Data directory not found: {data_dir}")
        print("   Skipping Question 1 (structure label analysis)")
    
    # Question 2: HTF bias distribution
    results_dict["htf_bias_analysis"] = analyze_htf_bias_distribution(results)
    
    # Questions 3 & 4: Scoring factors
    results_dict["scoring_analysis"] = analyze_scoring_factors(results)
    
    # Question 5: Seasonality gating
    results_dict["seasonality_analysis"] = analyze_seasonality_gating(results)
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    
    critical_issues = []
    
    # Check each analysis for critical issues
    struct_analysis = results_dict.get("structure_analysis", {})
    if struct_analysis.get("avg_na_percent", 0) > 30:
        critical_issues.append(f"Structure NA% too high: {struct_analysis['avg_na_percent']:.1f}%")
    
    htf_analysis = results_dict.get("htf_bias_analysis", {})
    if htf_analysis.get("neutral_percent", 0) > 60:
        critical_issues.append(f"HTF neutral bias too high: {htf_analysis['neutral_percent']:.1f}%")
    
    scoring_analysis = results_dict.get("scoring_analysis", {})
    factor_stats = scoring_analysis.get("factor_stats", {})
    if factor_stats.get("rejection_candle", {}).get("zero_percent", 0) > 80:
        critical_issues.append("rejection_candle is almost always 0.0")
    if factor_stats.get("volume_spike", {}).get("zero_percent", 0) > 80:
        critical_issues.append("volume_spike is almost always 0.0")
    
    season_analysis = results_dict.get("seasonality_analysis", {})
    if season_analysis.get("blocked_percent", 0) > 20:
        critical_issues.append(f"Seasonality blocking too many signals: {season_analysis['blocked_percent']:.1f}%")
    
    if critical_issues:
        print("\n🚨 CRITICAL ISSUES FOUND:")
        for i, issue in enumerate(critical_issues, 1):
            print(f"   {i}. {issue}")
    else:
        print("\n✅ No critical issues detected in executed signals.")
        print("\n⚠️  However, only 8 trades executed in entire month!")
        print("   The problem is likely BEFORE signal execution:")
        print("   - Signals may be rejected during validation")
        print("   - HTF structure may not be validating properly")
        print("   - Score cutoffs may be too high")
        print("\n💡 NEXT STEPS:")
        print("   1. Add logging to replay_loop.py to track rejected signals")
        print("   2. Check htf/integration.py for validation logic")
        print("   3. Review scoring thresholds in config/scoring_config.yaml")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

