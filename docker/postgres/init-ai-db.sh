#!/bin/bash
# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e

AI_DB_PASSWORD="${AI_DB_PASSWORD:-ai_secret}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER ai_user WITH PASSWORD '${AI_DB_PASSWORD}';
    CREATE DATABASE state OWNER ai_user;
    GRANT ALL PRIVILEGES ON DATABASE state TO ai_user;
EOSQL
