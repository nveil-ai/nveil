#!/bin/bash
# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

rm -rf node_modules package-lock.json .vite
npm cache clean --force
npm install