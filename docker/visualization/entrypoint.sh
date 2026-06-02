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

export KEDRO_DISABLE_TELEMETRY=true
export KEDRO_LOGGING_CONFIG=/nveil/backend/tools/logger/logging_config.yaml

# Start virtual X server for headless GLX rendering.
# VTK uses GLX (X11 OpenGL) → Mesa picks the best available driver:
#   WSL2: D3D12 Gallium (GPU via DirectX translation)
#   Native Linux + NVIDIA: NVIDIA GLX driver
#   No GPU: llvmpipe (software)
Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX &
export DISPLAY=:99
sleep 1

# Use software rendering (llvmpipe + EGL surfaceless) only when no EGL driver is available.
eglinfo -B >/dev/null 2>&1
if [ $? -eq 5 ]; then
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export EGL_PLATFORM=surfaceless
fi

/opt/venv/bin/python3 -Bu -m nveil_viewer --server
