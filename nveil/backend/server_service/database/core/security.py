# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Security functions around the password encrypt"""
import bcrypt

def	hash_password(password: str) -> str:
    """Hash the original password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def	verify_password(password: str, hashed_password: str) -> bool:
    """Verify the password given against the hashed password stored"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
