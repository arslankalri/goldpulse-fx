#!/bin/bash
# ============================================================================
# Gold App — one-time server install (bot-server, next to Malang).
#
# HOW TO USE: open Oracle Cloud Shell, SSH to the server
# (ssh ubuntu@138.2.54.27), then paste this whole script and run it.
# It is idempotent — safe to paste twice. It installs NO code: the first
# code deploy lands afterwards via the OCI API + gold-app-deploy helper.
# ============================================================================
set -eu

echo "== gold-app install =="
sudo mkdir -p /opt/gold-app/data
sudo chown -R ubuntu:ubuntu /opt/gold-app

echo "-- systemd unit -> /etc/systemd/system/gold-app.service"
sudo tee /etc/systemd/system/gold-app.service > /dev/null <<'GOLDAPP_UNIT_EOF'
[Unit]
Description=Gold App — PAXG signal engine + web dashboard (decision-support only)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/gold-app
Environment=TZ=Asia/Tokyo
Environment=GOLDAPP_DATA_DIR=/opt/gold-app/data
Environment=GOLDAPP_PORT=8791
ExecStart=/opt/gold-app/run.sh
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
GOLDAPP_UNIT_EOF

echo "-- deploy helper -> /usr/local/bin/gold-app-deploy"
sudo tee /usr/local/bin/gold-app-deploy > /dev/null <<'GOLDAPP_HELPER_EOF'
#!/bin/bash
# gold-app-deploy — root deploy helper for the Gold App (PAXG signals).
# Mirrors /usr/local/bin/malang-deploy's behaviour, gold-app paths only.
# Invoked by ocarun via passwordless sudo (/etc/sudoers.d/gold-app-deploy).
# With a staged tarball at /var/tmp/gold-app-deploy/incoming.tar.gz it
# deploys; with none staged it prints status only and changes nothing.
set -u
APP=/opt/gold-app
STAGE_DIR=/var/tmp/gold-app-deploy
STAGE=$STAGE_DIR/incoming.tar.gz
PATHS="gold_app dashboard tests deploy events.json run.sh README.md RESEARCH_AND_DESIGN.md"
TS=$(date +%Y%m%d%H%M%S)

version_line() { grep -m1 '__version__' "$APP/gold_app/__init__.py" 2>/dev/null || echo "version unknown"; }

if [ ! -f "$STAGE" ]; then
  echo "STATUS: no staged tarball"
  systemctl is-active gold-app 2>/dev/null || true
  version_line
  exit 0
fi

echo "DEPLOY gold-app $TS"
systemctl stop gold-app 2>/dev/null || true

BACKUP=/opt/gold-app-code-backup-$TS
mkdir -p "$BACKUP"
for p in $PATHS; do
  [ -e "$APP/$p" ] && cp -a "$APP/$p" "$BACKUP/"
done
# The live dashboard state survives code swaps (the service rewrites it on
# its next scan anyway, but never serve a stale sample in between).
[ -f "$APP/dashboard/state.json" ] && cp -a "$APP/dashboard/state.json" /tmp/gold-app-state.json.bak

TMP=$(mktemp -d)
if ! tar -xzf "$STAGE" -C "$TMP"; then
  echo "EXTRACT FAILED — code untouched"
  systemctl start gold-app 2>/dev/null || true
  rm -rf "$TMP"
  exit 1
fi

for p in $PATHS; do
  if [ -e "$TMP/$p" ]; then
    rm -rf "$APP/$p"
    cp -a "$TMP/$p" "$APP/$p"
  fi
done
rm -rf "$TMP"
[ -f /tmp/gold-app-state.json.bak ] && cp -a /tmp/gold-app-state.json.bak "$APP/dashboard/state.json"
chown -R ubuntu:ubuntu "$APP" 2>/dev/null || true
chmod +x "$APP/run.sh" 2>/dev/null || true

if ! (cd "$APP" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . > /tmp/gold-app-tests.log 2>&1); then
  echo "TESTS FAILED — restoring backup $BACKUP"
  tail -5 /tmp/gold-app-tests.log || true
  for p in $PATHS; do
    rm -rf "$APP/$p"
    [ -e "$BACKUP/$p" ] && cp -a "$BACKUP/$p" "$APP/$p"
  done
  chown -R ubuntu:ubuntu "$APP" 2>/dev/null || true
  systemctl start gold-app 2>/dev/null || true
  exit 1
fi
tail -3 /tmp/gold-app-tests.log

mv "$STAGE" "$STAGE_DIR/processed-$TS.tar.gz"
systemctl start gold-app
sleep 2
systemctl is-active gold-app
version_line
echo "DEPLOY OK $TS"
GOLDAPP_HELPER_EOF
sudo chown root:root /usr/local/bin/gold-app-deploy
sudo chmod 755 /usr/local/bin/gold-app-deploy

echo "-- sudoers: ocarun may run ONLY the gold-app deploy helper"
echo 'ocarun ALL=(root) NOPASSWD: /usr/local/bin/gold-app-deploy' | sudo tee /etc/sudoers.d/gold-app-deploy > /dev/null
sudo chmod 440 /etc/sudoers.d/gold-app-deploy
sudo visudo -cf /etc/sudoers.d/gold-app-deploy

echo "-- staging dir for OCI-API deploys"
sudo mkdir -p /var/tmp/gold-app-deploy
sudo chown ocarun:snap_daemon /var/tmp/gold-app-deploy
sudo chmod 775 /var/tmp/gold-app-deploy

sudo systemctl daemon-reload
sudo systemctl enable gold-app || true
echo ""
echo "GOLD-APP INSTALL DONE"
echo "The service is enabled and will start once the first code deploy lands"
echo "via the OCI API (gold-app-deploy). Dashboard port: 8791."
