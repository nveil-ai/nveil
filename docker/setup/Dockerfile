# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

FROM python:3.12.13-slim-trixie

WORKDIR /app

COPY docker/setup/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY docker/setup/compose_utils.py .
COPY docker/setup/app.py .

EXPOSE 3000
CMD ["python", "app.py"]
