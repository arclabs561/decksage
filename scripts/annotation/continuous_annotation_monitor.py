#!/usr/bin/env python3
"""
Continuous annotation monitoring.

Monitors annotation system for changes, new annotations, and quality issues.
Can run as a daemon or be called periodically.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class AnnotationMonitor:
    """Monitor annotation system for changes."""
    
    def __init__(self, annotations_dir: Path, state_file: Path | None = None):
        self.annotations_dir = annotations_dir
        self.state_file = state_file or annotations_dir / ".monitor_state.json"
        self.last_state = self._load_state()
    
    def _load_state(self) -> dict[str, Any]:
        """Load last known state."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_check": None,
            "file_sizes": {},
            "file_counts": {},
        }
    
    def _save_state(self, state: dict[str, Any]) -> None:
        """Save current state."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def check_changes(self) -> dict[str, Any]:
        """Check for changes since last check."""
        current_state = {
            "last_check": datetime.now().isoformat(),
            "file_sizes": {},
            "file_counts": {},
        }
        
        changes = {
            "new_files": [],
            "modified_files": [],
            "deleted_files": [],
            "size_changes": [],
        }
        
        # Check annotation files
        annotation_files = list(self.annotations_dir.glob("*.jsonl"))
        annotation_files.extend(list(self.annotations_dir.glob("*.json")))
        annotation_files.extend(list(self.annotations_dir.glob("hand_batch_*.yaml")))
        
        last_files = set(self.last_state.get("file_sizes", {}).keys())
        current_files = {str(f) for f in annotation_files}
        
        # New files
        for f in annotation_files:
            file_str = str(f)
            size = f.stat().st_size if f.exists() else 0
            
            # Count entries for JSONL
            count = 0
            if f.suffix == ".jsonl" and f.exists():
                count = sum(1 for _ in open(f))
            
            current_state["file_sizes"][file_str] = size
            current_state["file_counts"][file_str] = count
            
            if file_str not in last_files:
                changes["new_files"].append({
                    "file": file_str,
                    "size": size,
                    "count": count,
                })
            else:
                last_size = self.last_state["file_sizes"].get(file_str, 0)
                if size != last_size:
                    changes["modified_files"].append({
                        "file": file_str,
                        "old_size": last_size,
                        "new_size": size,
                        "old_count": self.last_state["file_counts"].get(file_str, 0),
                        "new_count": count,
                    })
        
        # Deleted files
        for file_str in last_files:
            if file_str not in current_files:
                changes["deleted_files"].append({"file": file_str})
        
        # Save state
        self._save_state(current_state)
        self.last_state = current_state
        
        return changes
    
    def monitor(self, interval: int = 60, max_iterations: int | None = None) -> None:
        """Monitor continuously."""
        print("=" * 80)
        print("CONTINUOUS ANNOTATION MONITORING")
        print("=" * 80)
        print(f"Monitoring: {self.annotations_dir}")
        print(f"Interval: {interval} seconds")
        print(f"State file: {self.state_file}")
        print()
        
        iteration = 0
        try:
            while True:
                iteration += 1
                if max_iterations and iteration > max_iterations:
                    break
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Check {iteration}...")
                changes = self.check_changes()
                
                if any(changes.values()):
                    print("  Changes detected:")
                    if changes["new_files"]:
                        print(f"    New files: {len(changes['new_files'])}")
                        for f in changes["new_files"][:3]:
                            print(f"      + {Path(f['file']).name} ({f['count']} entries)")
                    if changes["modified_files"]:
                        print(f"    Modified files: {len(changes['modified_files'])}")
                        for f in changes["modified_files"][:3]:
                            print(f"      ~ {Path(f['file']).name} ({f['old_count']} → {f['new_count']} entries)")
                    if changes["deleted_files"]:
                        print(f"    Deleted files: {len(changes['deleted_files'])}")
                else:
                    print("  No changes")
                
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor annotation system")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory to monitor",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        help="State file for tracking changes",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't monitor continuously)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Maximum iterations (for testing)",
    )
    
    args = parser.parse_args()
    
    monitor = AnnotationMonitor(args.annotations_dir, args.state_file)
    
    if args.once:
        changes = monitor.check_changes()
        print("Changes detected:")
        print(json.dumps(changes, indent=2))
    else:
        monitor.monitor(args.interval, args.max_iterations)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


