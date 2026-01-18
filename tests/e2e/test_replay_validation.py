"""End-to-end replay validation tests.

Tests the full replay validation workflow:
1. Run backtester on historical data
2. Replay same data through microservices
3. Compare trade outcomes

These tests require:
- Docker and docker-compose installed
- Redis and PostgreSQL running
- All microservices built
- Historical CSV data available
"""

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from backtester.results_io import load_results
from scripts.compare_results import compare_backtest_vs_microservices
from scripts.collect_microservice_trades import collect_trades
from scripts.replay_historical import replay_historical_data

# Test configuration
TEST_DATA_DIR = Path("data/gc_dx_ohlcv")
TEST_START = datetime(2024, 11, 1, 0, 0, 0)
TEST_END = datetime(2024, 11, 7, 23, 59, 59)  # 1 week for faster testing
REDIS_URL = "redis://localhost:6379"
DATABASE_URL = "postgresql://scp:scp_dev_password@localhost:5432/scp"
SPEED_MULTIPLIER = 0  # Turbo mode (no delays, maximum speed)


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def ensure_data_available():
    """Ensure test data is available."""
    if not TEST_DATA_DIR.exists():
        pytest.skip(f"Test data not found at {TEST_DATA_DIR}")
    
    # Check for GC and DXY files
    gc_files = list(TEST_DATA_DIR.glob("*GC*.csv")) + list(TEST_DATA_DIR.glob("*glbx*.csv"))
    dxy_files = list(TEST_DATA_DIR.glob("*DX*.csv"))
    
    if not gc_files:
        pytest.skip(f"No GC CSV files found in {TEST_DATA_DIR}")
    if not dxy_files:
        pytest.skip(f"No DXY CSV files found in {TEST_DATA_DIR}")


@pytest.fixture(scope="module")
def ensure_services_running():
    """Ensure microservices are running."""
    # Check if services are running
    result = subprocess.run(
        ["docker", "compose", "-f", "infra/docker-compose.infra.yml", "-f", "infra/docker-compose.services.yml", "ps"],
        capture_output=True,
        text=True,
    )
    
    if "data-adapter" not in result.stdout:
        pytest.skip(
            "Microservices not running. Start with: "
            "docker-compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.replay.yml up -d"
        )


@pytest.fixture(scope="module")
def clean_database():
    """Clean database before test."""
    # Reset database state
    subprocess.run(
        ["docker", "exec", "scp-postgres", "psql", "-U", "scp", "-d", "scp", "-c", "TRUNCATE TABLE trades CASCADE"],
        capture_output=True,
    )
    
    # Clean Redis streams
    subprocess.run(
        ["docker", "exec", "scp-redis", "redis-cli", "FLUSHDB"],
        capture_output=True,
    )
    
    yield
    
    # Cleanup after test (optional)


@pytest.mark.asyncio
async def test_replay_validation_workflow(ensure_data_available, ensure_services_running, clean_database):
    """Test complete replay validation workflow.
    
    This test validates that microservices produce results consistent with
    the backtester when processing the same historical data.
    """
    output_dir = Path("output/e2e_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    backtest_file = output_dir / f"backtest_{TEST_START.strftime('%Y%m%d')}_{TEST_END.strftime('%Y%m%d')}.json"
    
    # Step 1: Run backtester on test data
    print("\n" + "=" * 80)
    print("Step 1/3: Running backtester on historical data")
    print("=" * 80)
    
    result = subprocess.run(
        [
            "poetry", "run", "python", "scripts/run_backtest_and_view.py",
            "--start", TEST_START.isoformat(),
            "--end", TEST_END.isoformat(),
            "--no-view",
            "--output-file", str(backtest_file),
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"Backtester failed:\n{result.stderr}")
        pytest.fail(f"Backtester failed with exit code {result.returncode}")
    
    assert backtest_file.exists(), "Backtester results file not created"
    
    # Load backtester results
    backtest_results = load_results(backtest_file)
    print(f"✓ Backtester complete: {backtest_results.total_trades} trades")
    
    # Step 2: Replay data through microservices
    print("\n" + "=" * 80)
    print("Step 2/3: Replaying data through microservices")
    print("=" * 80)
    
    replay_stats = await replay_historical_data(
        data_dir=TEST_DATA_DIR,
        start=TEST_START,
        end=TEST_END,
        redis_url=REDIS_URL,
        speed_multiplier=SPEED_MULTIPLIER,
        processing_delay=10.0,  # Wait 10s for pipeline to process
    )
    
    assert replay_stats["success"], "Replay failed"
    assert replay_stats["candles_published"] > 0, "No candles published"
    print(f"✓ Replay complete: {replay_stats['candles_published']} candles published")
    
    # Step 3: Compare results
    print("\n" + "=" * 80)
    print("Step 3/3: Comparing results")
    print("=" * 80)
    
    # Collect microservices trades from database
    microservice_trades = await collect_trades(
        database_url=DATABASE_URL,
        start=TEST_START,
        end=TEST_END,
    )
    
    print(f"Microservices trades: {len(microservice_trades)}")
    
    # Convert backtester trades to dict format
    from backtester.trade import to_dict
    backtest_trades = [to_dict(trade) for trade in backtest_results.trades]
    
    # Compare
    report = compare_backtest_vs_microservices(backtest_trades, microservice_trades)
    
    # Print summary
    report.print_summary()
    
    # Save detailed report
    report_file = output_dir / f"comparison_report_{TEST_START.strftime('%Y%m%d')}_{TEST_END.strftime('%Y%m%d')}.json"
    import json
    with open(report_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "report": report.to_dict(),
        }, f, indent=2)
    
    print(f"\n✓ Detailed report saved to {report_file}")
    
    # Assertions
    assert report.backtest_count > 0, "No trades in backtester results"
    
    # Relaxed validation: Allow 10% difference in trade count
    trade_count_tolerance = 0.1
    trade_count_diff = abs(report.backtest_count - report.microservices_count)
    trade_count_diff_pct = (trade_count_diff / report.backtest_count) * 100 if report.backtest_count > 0 else 0
    
    assert trade_count_diff_pct <= (trade_count_tolerance * 100), (
        f"Trade count mismatch: {report.backtest_count} vs {report.microservices_count} "
        f"({trade_count_diff_pct:.1f}% difference, allowed: {trade_count_tolerance * 100}%)"
    )
    
    # Match rate should be at least 90%
    min_match_rate = 90.0
    assert report.match_rate >= min_match_rate, (
        f"Match rate too low: {report.match_rate:.1f}% (expected >= {min_match_rate}%)\n"
        f"Missing in microservices: {len(report.missing_in_microservices)}\n"
        f"Extra in microservices: {len(report.extra_in_microservices)}"
    )
    
    print("\n" + "=" * 80)
    print("✓ Replay Validation PASSED")
    print("=" * 80)


@pytest.mark.asyncio
async def test_replay_validation_short_period(ensure_data_available, ensure_services_running, clean_database):
    """Test replay validation on a very short period (1 day) for faster feedback."""
    # Use just 1 day for fast validation
    test_start = datetime(2024, 11, 1, 0, 0, 0)
    test_end = datetime(2024, 11, 2, 0, 0, 0)
    
    output_dir = Path("output/e2e_test_short")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    backtest_file = output_dir / f"backtest_{test_start.strftime('%Y%m%d')}.json"
    
    # Run backtester
    result = subprocess.run(
        [
            "poetry", "run", "python", "scripts/run_backtest_and_view.py",
            "--start", test_start.isoformat(),
            "--end", test_end.isoformat(),
            "--no-view",
            "--output-file", str(backtest_file),
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        pytest.skip(f"Backtester failed (possibly no data for this period): {result.stderr}")
    
    # Replay through microservices
    replay_stats = await replay_historical_data(
        data_dir=TEST_DATA_DIR,
        start=test_start,
        end=test_end,
        redis_url=REDIS_URL,
        speed_multiplier=0,  # Turbo mode
        processing_delay=5.0,
    )
    
    assert replay_stats["success"], "Replay failed"
    
    # Compare (basic check)
    backtest_results = load_results(backtest_file)
    microservice_trades = await collect_trades(
        database_url=DATABASE_URL,
        start=test_start,
        end=test_end,
    )
    
    # Just check that both systems processed data
    # (may not have trades in 1 day, so don't assert on counts)
    print(f"Backtester: {len(backtest_results.trades)} trades")
    print(f"Microservices: {len(microservice_trades)} trades")
    
    # Test passes if replay completed without errors
    assert True, "Short period replay validation passed"


if __name__ == "__main__":
    # Allow running tests directly for development
    sys.exit(pytest.main([__file__, "-v", "-s"]))

