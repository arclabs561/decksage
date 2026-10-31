#!/usr/bin/env bash
# Keep the host MPS embedding bridge alive at login/daily.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="$(pwd)"
UV="$(command -v uv)"
LABEL="com.decksage.mps-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.agents/logs"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>ProgramArguments</key><array>
    <string>$UV</string><string>run</string>
    <string>--with</string><string>fastapi</string><string>--with</string><string>uvicorn</string>
    <string>--with</string><string>sentence-transformers</string><string>--with</string><string>torch</string>
    <string>python</string><string>$REPO/scripts/ops/mps_bridge.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.agents/logs/decksage-mps-bridge.log</string>
  <key>StandardErrorPath</key><string>$HOME/.agents/logs/decksage-mps-bridge.log</string>
</dict></plist>
PLIST
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "installed $LABEL -> $PLIST"
