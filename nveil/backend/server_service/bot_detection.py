# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
from device_detector import DeviceDetector

# Headless browsers and HTTP libraries that device_detector doesn't cover
_HEADLESS_PATTERN = re.compile(
    r"(headlesschrom|lighthouse|pagespeed|phantomjs|selenium|puppeteer|playwright"
    r"|curl|wget|python-requests|aiohttp|httpx|scrapy)",
    re.IGNORECASE,
)


def is_bot(user_agent: str, cf_client_bot: str = "") -> bool:
    # Cloudflare's Transform Rule sets x-is-bot: "true"/"false" from cf.client.bot,
    # their continuously-maintained verified-crawler classifier (IP + reverse-DNS).
    # When true, trust it unconditionally — catches crawlers whose UA DeviceDetector
    # hasn't been updated to recognize (prevents serving SPA shell to Googlebot).
    if cf_client_bot == "true":
        return True
    if not user_agent:
        return False
    if _HEADLESS_PATTERN.search(user_agent):
        return True
    return DeviceDetector(user_agent).parse().is_bot()
