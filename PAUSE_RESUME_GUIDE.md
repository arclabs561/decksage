# Pause/Resume Guide

## ✅ All Machines Resumed!

### AWS EC2 Instance
- **Instance**: `i-0388197edd52b11f2` (g4dn.xlarge)
- **Status**: Running
- **Resumed**: Successfully started

### Local Background Processes
- **PIDs**: 21447, 27958, 27942, 21405 (card enrichment)
- **Status**: Running (resumed with SIGCONT)
- **State**: Continuing from where they paused

## Resume Commands

### Resume AWS Instance
```bash
aws ec2 start-instances --instance-ids i-0388197edd52b11f2
```

### Resume Local Processes
```bash
for pid in 21447 27958 27942 21405; do kill -CONT "$pid" 2>/dev/null && echo "✅ Resumed PID $pid"; done
```

### Check Status
```bash
# AWS instances
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running,stopped"

# Local processes
ps aux | grep -E "(enrich|label|export)" | grep -v grep
```

## Manual Commands

### AWS
```bash
# Stop instance (preserves state)
aws ec2 stop-instances --instance-ids i-xxxxx

# Start instance
aws ec2 start-instances --instance-ids i-xxxxx

# Terminate instance (deletes - can't resume)
aws ec2 terminate-instances --instance-ids i-xxxxx
```

### Local Processes
```bash
# Pause (SIGSTOP)
kill -STOP <PID>

# Resume (SIGCONT)
kill -CONT <PID>

# Kill (if needed)
kill <PID>
```

**Sleep well! 😴**
