"""Agentic quality assurance for annotations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


class AnnotationQualityAgent:
    """Agentic system for annotation quality assurance."""
    
    def __init__(self, annotations_dir: Path | None = None):
        """Initialize annotation QA agent."""
        self.annotations_dir = annotations_dir or Path("annotations")
        self.issues: list[dict[str, Any]] = []
    
    def check_annotation_quality(self, annotation_file: Path) -> dict[str, Any]:
        """Check quality of annotations in a file."""
        logger.info(f"Checking annotation quality: {annotation_file}")
        
        annotations = []
        errors = []
        
        with open(annotation_file) as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    ann = json.loads(line)
                    annotations.append(ann)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
        
        # Quality checks
        quality_report = {
            "file": str(annotation_file),
            "total_annotations": len(annotations),
            "errors": errors,
            "issues": [],
            "warnings": [],
            "statistics": {},
        }
        
        if not annotations:
            quality_report["issues"].append("No valid annotations found")
            return quality_report
        
        # Check required fields
        required_fields = ["card1", "card2", "similarity_score"]
        for i, ann in enumerate(annotations):
            for field in required_fields:
                if field not in ann or ann[field] is None:
                    quality_report["issues"].append(f"Annotation {i} missing {field}")
        
        # Check score validity
        invalid_scores = []
        for i, ann in enumerate(annotations):
            score = ann.get("similarity_score")
            if score is None or not (0.0 <= score <= 1.0):
                invalid_scores.append(i)
        
        if invalid_scores:
            quality_report["issues"].append(f"{len(invalid_scores)} annotations have invalid similarity scores")
        
        # Check for graph enrichment
        enriched_count = sum(1 for ann in annotations if ann.get("graph_features"))
        enrichment_rate = enriched_count / len(annotations) if annotations else 0
        
        if enrichment_rate < 0.5:
            quality_report["warnings"].append(
                f"Only {enrichment_rate:.1%} of annotations have graph features"
            )
        
        # Statistics
        scores = [ann.get("similarity_score", 0) for ann in annotations if ann.get("similarity_score") is not None]
        quality_report["statistics"] = {
            "total": len(annotations),
            "enriched": enriched_count,
            "enrichment_rate": enrichment_rate,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
        }
        
        return quality_report
    
    def check_all_annotations(self) -> dict[str, Any]:
        """Check quality of all annotation files."""
        logger.info("Checking all annotation files...")
        
        annotation_files = list(self.annotations_dir.glob("*.jsonl"))
        
        reports = []
        for ann_file in annotation_files:
            report = self.check_annotation_quality(ann_file)
            reports.append(report)
        
        # Aggregate report
        total_annotations = sum(r["total_annotations"] for r in reports)
        total_errors = sum(len(r["errors"]) for r in reports)
        total_issues = sum(len(r["issues"]) for r in reports)
        total_warnings = sum(len(r["warnings"]) for r in reports)
        
        return {
            "total_files": len(annotation_files),
            "total_annotations": total_annotations,
            "total_errors": total_errors,
            "total_issues": total_issues,
            "total_warnings": total_warnings,
            "file_reports": reports,
        }


