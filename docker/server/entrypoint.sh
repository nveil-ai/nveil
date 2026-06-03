#!/bin/sh
# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later


export PYTHONWARNINGS="ignore:::requests"

# ====================================== #
# TLS Certificate Setup (runtime)
# ====================================== #
for f in /certs/*.crt /certs/*.pem; do
    [ -f "$f" ] && cp "$f" /usr/local/share/ca-certificates/"$(basename $f)" 2>/dev/null
done
update-ca-certificates 2>/dev/null
/opt/venv/bin/python3 -c "
import certifi, glob
ca_path = certifi.where()
for f in sorted(glob.glob('/certs/*.crt') + glob.glob('/certs/*.pem')):
    with open(ca_path, 'a') as ca, open(f) as cert:
        ca.write(cert.read())
" 2>/dev/null || true

# ====================================== #
# Frontend
# ====================================== #
cat > /nveil/frontend/.env <<EOF
VITE_GOOGLE_AUTH_API_KEY=$GOOGLE_AUTH_API_KEY
VITE_URL_LOCAL_APP=
VITE_DEV=
EOF

# Cloud mode: install cloud-frontend extension and rebuild with cloud env vars.
# Community mode: dist is baked into the image at build time, no rebuild needed.
if [ -f "/nveil/cloud-frontend/package.json" ]; then
    mkdir -p /nveil/frontend/node_modules/@nveil
    ln -sf /nveil/cloud-frontend /nveil/frontend/node_modules/@nveil/cloud-frontend
    NVEIL_CLOUD=1 make -C /nveil/frontend build
fi

# ====================================== #
# Database + Server
# ====================================== #
export PYTHONPATH=/nveil/backend
cd /nveil/backend/server_service

/opt/venv/bin/alembic -c /nveil/backend/server_service/database/models/alembic.ini upgrade head

/opt/venv/bin/python3 -B -m uvicorn server:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile /certs/ma_cle_privee.key \
  --ssl-certfile /certs/mon_certificat.crt \
  --log-level warning \
  --reload --reload-dir /nveil/backend/server_service \
  --reload-dir /nveil/backend/shared \
  --reload-dir /nveil/backend/tools  &
UVICORN_PID=$!

# Prerender (cloud only — needs Puppeteer + running server)
if [ -f "/nveil/cloud-frontend/package.json" ]; then
    echo "Waiting for server to start..."
    for i in $(seq 1 30); do
      if curl -sk https://localhost:8000/ > /dev/null 2>&1; then
        echo "Server ready, starting prerender..."
        make -C /nveil/frontend prerender > /var/log/prerender.log 2>&1 || echo "Prerender failed, continuing..."
        break
      fi
      sleep 2
    done
fi

wait $UVICORN_PID
