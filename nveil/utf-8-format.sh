#!/bin/bash
# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later


find . -type f -name "*.py" -exec dos2unix {} \;
find . -type f -name "*.tf" -exec dos2unix {} \;

echo "✅ Conversion terminée : tous les fichiers sont maintenant en format Unix (LF, sans BOM)."
