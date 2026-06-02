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

cd /nveil/backend/file_service

export KEDRO_LOGGING_CONFIG=/nveil/backend/tools/logger/logging_config.yaml

/opt/venv/bin/python3 -B -m uvicorn file_server:app --host 0.0.0.0 --port 8200 \
    --ssl-keyfile /certs/ma_cle_privee.key \
    --ssl-certfile /certs/mon_certificat.crt \
    --log-level warning \
    --log-config /nveil/backend/tools/logger/logging_config.yaml --reload
