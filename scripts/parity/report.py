"""Divergence reporting for parity testing."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Divergence:
    """Represents a single divergence between backtester and microservices.

    Attributes:
        bar_index: Index of the bar where divergence occurred
        timestamp: Timestamp of the diverging bar
        stage: Stage where divergence occurred
              (features, scoring, guardrails, execution)
        component: Specific component that diverged
                  (e.g., "rsi", "score", "confidence")
        backtester_value: Value from backtester implementation
        microservices_value: Value from microservices implementation
        delta: Numeric difference (if applicable)
        context: Additional context about the divergence
    """

    bar_index: int
    timestamp: datetime
    stage: str
    component: str
    backtester_value: Any
    microservices_value: Any
    delta: float | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        result = asdict(self)
        # Convert datetime to ISO string
        if isinstance(result["timestamp"], datetime):
            result["timestamp"] = result["timestamp"].isoformat()
        return result

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Bar {self.bar_index} ({self.timestamp})",
            f"Stage: {self.stage}",
            f"Component: {self.component}",
            f"  Backtester: {self.backtester_value}",
            f"  Microservices: {self.microservices_value}",
        ]

        if self.delta is not None:
            lines.append(f"  Delta: {self.delta:.6f}")

        if self.context:
            lines.append("  Context:")
            for key, value in self.context.items():
                lines.append(f"    {key}: {value}")

        return "\n".join(lines)


@dataclass
class DivergenceReport:
    """Complete report of divergences found during parity testing.

    Attributes:
        total_bars: Total number of bars processed
        divergences: List of all divergences found
        first_divergence_bar: Bar index of first divergence (None if no divergences)
        summary: Aggregated statistics
        start_time: When the comparison started
        end_time: When the comparison finished
        stopped_early: Whether comparison stopped on first divergence
    """

    total_bars: int = 0
    divergences: list[Divergence] = field(default_factory=list)
    first_divergence_bar: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None
    stopped_early: bool = False

    def add_divergence(
        self,
        bar_index: int,
        timestamp: datetime,
        stage: str,
        component: str,
        backtester_value: Any,
        microservices_value: Any,
        delta: float | None = None,
        context: dict | None = None,
    ) -> None:
        """Add a divergence to the report.

        Args:
            bar_index: Index of the diverging bar
            timestamp: Timestamp of the diverging bar
            stage: Processing stage (features, scoring, etc.)
            component: Component that diverged
            backtester_value: Backtester value
            microservices_value: Microservices value
            delta: Numeric difference (optional)
            context: Additional context (optional)
        """
        divergence = Divergence(
            bar_index=bar_index,
            timestamp=timestamp,
            stage=stage,
            component=component,
            backtester_value=backtester_value,
            microservices_value=microservices_value,
            delta=delta,
            context=context or {},
        )

        self.divergences.append(divergence)

        # Track first divergence
        if self.first_divergence_bar is None:
            self.first_divergence_bar = bar_index

        logger.info(f"Divergence detected: {divergence.summary()}")

    def calculate_summary(self) -> None:
        """Calculate summary statistics."""
        self.summary = {
            "total_bars_processed": self.total_bars,
            "total_divergences": len(self.divergences),
            "first_divergence_at_bar": self.first_divergence_bar,
            "divergences_by_stage": {},
            "divergences_by_component": {},
            "stopped_early": self.stopped_early,
        }

        # Count by stage
        for div in self.divergences:
            stage = div.stage
            self.summary["divergences_by_stage"][stage] = (
                self.summary["divergences_by_stage"].get(stage, 0) + 1
            )

            component = div.component
            self.summary["divergences_by_component"][component] = (
                self.summary["divergences_by_component"].get(component, 0) + 1
            )

        # Calculate success metrics
        if self.total_bars > 0:
            bars_until_divergence = (
                self.first_divergence_bar
                if self.first_divergence_bar is not None
                else self.total_bars
            )
            self.summary["bars_until_divergence"] = bars_until_divergence
            self.summary["success_rate_pct"] = (
                bars_until_divergence / self.total_bars
            ) * 100

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        self.calculate_summary()

        return {
            "total_bars": self.total_bars,
            "divergences": [div.to_dict() for div in self.divergences],
            "first_divergence_bar": self.first_divergence_bar,
            "summary": self.summary,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "stopped_early": self.stopped_early,
        }

    def save(self, output_path: Path) -> None:
        """Save report to JSON file.

        Args:
            output_path: Path to save the report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info(f"Report saved to {output_path}")

    def print_summary(self) -> None:
        """Print human-readable summary to console."""
        self.calculate_summary()

        print("=" * 80)
        print("PARITY TEST SUMMARY")
        print("=" * 80)
        print(f"Total bars processed: {self.total_bars}")
        print(f"Total divergences: {len(self.divergences)}")

        if self.first_divergence_bar is not None:
            print(f"First divergence at bar: {self.first_divergence_bar}")
            print(f"Success rate: {self.summary['success_rate_pct']:.1f}%")
        else:
            print("✓ No divergences found - implementations match perfectly!")

        if self.stopped_early:
            print("\n⚠ Comparison stopped on first divergence")

        if self.summary["divergences_by_stage"]:
            print("\nDivergences by stage:")
            for stage, count in self.summary["divergences_by_stage"].items():
                print(f"  {stage}: {count}")

        if self.summary["divergences_by_component"]:
            print("\nDivergences by component:")
            for component, count in sorted(
                self.summary["divergences_by_component"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]:
                print(f"  {component}: {count}")

        print("=" * 80)

        # Print first divergence details
        if self.divergences:
            print("\nFIRST DIVERGENCE DETAILS:")
            print("-" * 80)
            print(self.divergences[0].summary())
            print("-" * 80)
