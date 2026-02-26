#!/usr/bin/env bash
# install.sh — One-command installer for OSS Radar daemon
# Usage: bash install.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$INSTALL_DIR/logs"
PLIST_NAME="com.dubsopenhub.oss-radar"
PLIST_SRC="$INSTALL_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
VENV_DIR="$INSTALL_DIR/.venv"

echo "🛰  OSS Radar — Installer"
echo "──────────────────────────────────────"

# 1. Create directories
echo "📁  Creating directories..."
mkdir -p "$LOGS_DIR"
mkdir -p "$HOME/.radar"

# 2. Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
  echo "🐍  Creating Python virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# 3. Install dependencies
echo "📦  Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# 4. Copy .env.example → .env if not exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
  echo "📝  Creating .env from template (configure before first run)..."
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo "    ⚠️  Edit $INSTALL_DIR/.env with your API keys and SMTP settings"
fi

# 5. Init database
echo "🗄️   Initializing database..."
"$VENV_DIR/bin/radar" validate 2>/dev/null || echo "    (validate skipped — configure .env first)"

# 6. Install launchd plist
echo "⚙️   Installing launchd agent..."
mkdir -p "$HOME/Library/LaunchAgents"

# Unload existing if present
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
  echo "    Unloading existing agent..."
  launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
fi

# Update plist with actual paths
sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"

# Load
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
echo "    ✅  Agent loaded: $PLIST_NAME"

# 7. Smoke test
echo "🧪  Smoke test..."
"$VENV_DIR/bin/radar" synth --dry-run --count 3 2>/dev/null && echo "    ✅  Smoke test passed" || echo "    ⚠️  Smoke test failed (configure .env)"

echo ""
echo "──────────────────────────────────────"
echo "✅  Installation complete!"
echo ""
echo "  Config:   $INSTALL_DIR/.env"
echo "  Database: ~/.radar/catalog.db"
echo "  Logs:     $LOGS_DIR/"
echo "  Schedule: 2x daily (6 AM + 6 PM PST) + Friday weekly digest"
echo ""
echo "  View logs:   tail -f $LOGS_DIR/radar-stdout.log"
echo "  Manual run:  $VENV_DIR/bin/radar daily --force"
echo "  Stop agent:  launchctl bootout gui/\$(id -u)/$PLIST_NAME"
echo ""
