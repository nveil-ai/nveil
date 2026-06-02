# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

# Charge le fichier .env en cherchant automatiquement dans les dossiers parents
load_dotenv(find_dotenv())

def get_secret(key: str, default: str = None) -> str:
    """
    Récupère une configuration ou un secret depuis :
    1. Un volume de secret K8s (/etc/secrets/{key})
    2. Les variables d'environnement (K8s env, Docker ou .env local)
    """
    # 1. Priorité aux secrets montés comme fichiers (K8s volume mount)
    path = Path(f"/etc/secrets/{key}")
    if path.exists():
        try:
            return path.read_text().strip()
        except OSError:
            # En cas d'erreur de lecture, on tente via l'environnement
            pass
    
    # 2. Sinon, on cherche dans les variables d'environnement
    return os.getenv(key, default)
