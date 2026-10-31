#!/usr/bin/env bash
# Install a daily LaunchAgent that runs scripts/ops/refresh_all.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="$(pwd)"
LABEL="com.decksage.refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.agents/logs"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$REPO/scripts/ops/refresh_all.sh</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$HOME/.agents/logs/decksage-refresh.log</string>
  <key>StandardErrorPath</key><string>$HOME/.agents/logs/decksage-refresh.log</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
PLIST
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "installed $LABEL -> $PLIST"
