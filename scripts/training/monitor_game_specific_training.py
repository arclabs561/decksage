#!/usr/bin/env python3
"""Monitor game-specific training progress using structured log parsing."""
import sys
import time
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

try:
    from ml.utils.log_monitor import LocalLogMonitor, format_status
    HAS_STRUCTURED = True
except ImportError:
    HAS_STRUCTURED = False

def check_training_status(game, use_structured=True):
    """Check training status for a game, using structured logs if available."""
    log = Path(f"{game}_game_specific_training.log")
    emb = Path(f"data/embeddings/{game}_game_specific.wv")
    
    status = {"game": game, "running": False, "complete": False, "error": False, "progress": "", "size_mb": 0.0}
    
    # Check if embeddings exist (training complete)
    if emb.exists():
        status["complete"] = True
        status["size_mb"] = emb.stat().st_size / (1024 * 1024)
        return status
    
    # Use structured log parsing if available
    if use_structured and HAS_STRUCTURED and log.exists():
        try:
            monitor = LocalLogMonitor(log)
            structured_status = monitor.get_status(last_n_lines=50)
            
            status["running"] = True
            if structured_status.stage:
                status["progress"] = f"{structured_status.stage}"
                if structured_status.progress:
                    status["progress"] += f": {structured_status.progress}"
            elif structured_status.last_metric:
                status["progress"] = f"Metrics: {', '.join(f'{k}={v}' for k, v in list(structured_status.last_metric.items())[:2])}"
            
            if structured_status.errors:
                status["error"] = True
                status["progress"] = structured_status.errors[-1][:80]
            
            if structured_status.is_complete:
                status["complete"] = True
            
            return status
        except Exception:
            # Fall back to old method if structured parsing fails
            pass
    
    # Fallback: old string-matching method
    if not log.exists():
        return status
    
    status["running"] = True
    with open(log) as f:
        lines = f.readlines()
        recent_lines = lines[-10:] if len(lines) >= 10 else lines
    
    # Check for errors
    for line in recent_lines:
        if "ERROR" in line or "Error" in line or "Traceback" in line:
            status["error"] = True
            status["progress"] = line.strip()[:80]
            return status
    
    # Check for completion
    for line in recent_lines:
        if "[CHECKPOINT]" in line or "[PROGRESS]" in line and "complete" in line.lower():
            status["complete"] = True
            status["progress"] = line.strip()[:80]
            return status
    
    # Check for progress indicators
    for line in reversed(recent_lines):
        if "[PROGRESS]" in line:
            status["progress"] = line.strip()[:80]
            break
        elif "EPOCH" in line:
            status["progress"] = line.strip()[:80]
            break
        elif "Generating random walks" in line:
            status["progress"] = "Generating walks..."
            break
    
    if not status["progress"]:
        status["progress"] = recent_lines[-1].strip()[:80] if recent_lines else "Starting..."
    
    return status

games = ["magic", "pokemon", "yugioh"]
iteration = 0

try:
    while True:
        iteration += 1
        print(f"\n[{iteration}] {datetime.now().strftime('%H:%M:%S')} - Status")
        print("-" * 70)
        
        all_complete = True
        for game in games:
            status = check_training_status(game)
            if status["complete"]:
                print(f"{game.upper():10s}: Complete ({status['size_mb']:.1f} MB)")
            elif status["error"]:
                print(f"ERROR: {game.upper():10s}: ERROR - {status['progress']}")
                all_complete = False
            elif status["running"]:
                print(f"RUNNING: {game.upper():10s}: {status['progress']}")
                all_complete = False
            else:
                print(f"{game.upper():10s}: Not started")
                all_complete = False
        
        if all_complete:
            print("\nALL COMPLETE!")
            break
        
        time.sleep(30)
except KeyboardInterrupt:
    print("\n\nWARNING: Monitoring stopped")



