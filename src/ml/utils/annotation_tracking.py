"""Source tracking and versioning for annotations.

Tracks metadata about annotation sources, versions, and quality over time.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


class AnnotationTracker:
    """Track annotation sources, versions, and quality metrics."""
    
    def __init__(self, tracking_file: Path | None = None):
        """Initialize tracker.
        
        Args:
            tracking_file: Path to JSON file for persistent tracking
        """
        self.tracking_file = tracking_file
        self.metrics: dict[str, Any] = {
            "sources": Counter(),
            "versions": {},
            "quality_history": [],
            "timestamps": [],
        }
        
        if tracking_file and tracking_file.exists():
            self.load()
    
    def record_annotation(
        self,
        annotation: dict[str, Any],
        version: str | None = None,
        annotator_id: str | None = None,
    ) -> None:
        """Record an annotation with metadata."""
        source = annotation.get("source", "unknown")
        self.metrics["sources"][source] += 1
        
        if version:
            if version not in self.metrics["versions"]:
                self.metrics["versions"][version] = {
                    "count": 0,
                    "sources": Counter(),
                    "first_seen": datetime.now().isoformat(),
                }
            self.metrics["versions"][version]["count"] += 1
            self.metrics["versions"][version]["sources"][source] += 1
        
        if annotator_id:
            if "annotators" not in self.metrics:
                self.metrics["annotators"] = Counter()
            self.metrics["annotators"][annotator_id] += 1
        
        self.metrics["timestamps"].append(datetime.now().isoformat())
    
    def record_quality_metrics(
        self,
        quality_score: float,
        total_annotations: int,
        issues: list[str],
        warnings: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record quality metrics snapshot."""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "quality_score": quality_score,
            "total_annotations": total_annotations,
            "issues_count": len(issues),
            "warnings_count": len(warnings),
            "issues": issues[:10],  # Keep first 10
            "warnings": warnings[:10],  # Keep first 10
        }
        if metadata:
            snapshot["metadata"] = metadata
        
        self.metrics["quality_history"].append(snapshot)
        
        # Keep only last 100 snapshots
        if len(self.metrics["quality_history"]) > 100:
            self.metrics["quality_history"] = self.metrics["quality_history"][-100:]
    
    def get_source_distribution(self) -> dict[str, int]:
        """Get distribution of annotation sources."""
        return dict(self.metrics["sources"])
    
    def get_quality_trend(self) -> list[dict[str, Any]]:
        """Get quality score trend over time."""
        return self.metrics["quality_history"]
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        return {
            "total_sources": len(self.metrics["sources"]),
            "source_distribution": dict(self.metrics["sources"]),
            "total_versions": len(self.metrics["versions"]),
            "quality_snapshots": len(self.metrics["quality_history"]),
            "latest_quality": (
                self.metrics["quality_history"][-1]
                if self.metrics["quality_history"]
                else None
            ),
        }
    
    def save(self) -> None:
        """Save tracking data to file."""
        if not self.tracking_file:
            return
        
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Counter objects to dicts for JSON serialization
        save_data = {
            "sources": dict(self.metrics["sources"]),
            "versions": {
                k: {
                    "count": v["count"],
                    "sources": dict(v["sources"]),
                    "first_seen": v["first_seen"],
                }
                for k, v in self.metrics["versions"].items()
            },
            "quality_history": self.metrics["quality_history"],
            "timestamps": self.metrics["timestamps"][-1000:],  # Keep last 1000
        }
        
        if "annotators" in self.metrics:
            save_data["annotators"] = dict(self.metrics["annotators"])
        
        temp_path = self.tracking_file.with_suffix(self.tracking_file.suffix + ".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(save_data, f, indent=2)
            temp_path.replace(self.tracking_file)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def load(self) -> None:
        """Load tracking data from file."""
        if not self.tracking_file or not self.tracking_file.exists():
            return
        
        try:
            with open(self.tracking_file) as f:
                data = json.load(f)
            
            self.metrics["sources"] = Counter(data.get("sources", {}))
            self.metrics["versions"] = data.get("versions", {})
            self.metrics["quality_history"] = data.get("quality_history", [])
            self.metrics["timestamps"] = data.get("timestamps", [])
            
            if "annotators" in data:
                self.metrics["annotators"] = Counter(data["annotators"])
        except Exception as e:
            # If load fails, start fresh
            pass


