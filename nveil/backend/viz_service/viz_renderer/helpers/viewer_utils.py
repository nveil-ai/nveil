# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import os
from shared.secrets import get_secret
from logger import logger, DEBUG, INFO, WARNING, ERROR
from typing import Optional

LOCAL = get_secret("LOCAL")

import httpx
import psutil
from shared.service_client import ServiceClient

_default_client = ServiceClient(verify=True)

GCP = get_secret("GCP")


# -- Logging Configuration --
class LogpHandler(logging.Handler):
    def emit(self, record):
        # Map Python logging levels to logp levels
        level_map = {
            logging.DEBUG: DEBUG,
            logging.INFO: INFO,
            logging.WARNING: WARNING,
            logging.ERROR: ERROR,
            logging.CRITICAL: "ERROR",
        }
        # Get the log level as string
        logp_level = level_map.get(record.levelno, "ERROR")
        # Format the message
        msg = self.format(record)
        # Call your logp function
        logger().logp(logp_level, msg)


def setup_logging():
    # Remove other handlers and add your custom handler
    logging.root.handlers = []
    handler = LogpHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.WARNING)
    
def file_exists(filepath):
    return os.path.isfile(filepath)

def find_available_port(port: int) -> int:
    logger().logp(DEBUG, f"Trying port {port}...")
    used_ports = {conn.laddr.port for conn in psutil.net_connections() if conn.laddr}
    if port not in used_ports:
        return port
    return find_available_port(port + 1)


async def notify_host(server_host, room_token, message, details=None, local=False, client=None):
    try:
        c = client or _default_client
        if isinstance(c, ServiceClient):
            await c.post(
                f"https://{server_host}:8000/viz/notify",
                json={
                    "event": message,
                    "details": details or {},
                    "room_token": room_token,
                },
                timeout=5.0,
            )
        else:
            await c.post(
                f"https://{server_host}:8000/viz/notify",
                json={
                    "event": message,
                    "details": details or {},
                    "room_token": room_token,
                },
                timeout=5,
            )
    except Exception as e:
        logger().logp(ERROR, f"[Notify] Failed to send notification: {e}")


async def get_container_ip_async(container_name_or_id: str, client=None) -> Optional[str]:
    if LOCAL == "1":
        return None
    elif GCP == "1":
        metada_url = "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip"
        headers = {"Metadata-Flavor": "Google"}
        c = client or _default_client
        if isinstance(c, ServiceClient):
            resp = await c.get(metada_url, headers=headers, timeout=5.0)
            internal_ip = str(resp.data).strip() if resp.ok else ""
        else:
            resp = await c.get(metada_url, headers=headers, timeout=5)
            internal_ip = resp.text.strip()
        logger().logp(INFO, f"ip: {internal_ip}")
        return internal_ip
    return container_name_or_id[:20]


def get_container_ip(container_name_or_id: str) -> Optional[str]:
    """Sync wrapper — kept for backward compatibility."""
    if LOCAL == "1":
        return None
    elif GCP == "1":
        metada_url = "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip"
        headers = {"Metadata-Flavor": "Google"}
        response = httpx.get(metada_url, headers=headers)
        internal_ip = response.text.strip()
        logger().logp(INFO, f"ip: {internal_ip}")
        return internal_ip
    return container_name_or_id[:20]
