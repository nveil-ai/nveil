# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from pydantic import BaseModel


class ChangePasswordRequest(BaseModel):
    email: str
    current_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    """Requête pour demander un email de réinitialisation de mot de passe."""
    email: str

class ResetPasswordRequest(BaseModel):
    """Requête pour réinitialiser le mot de passe avec le code reçu par email."""
    email: str
    code: str
    new_password: str
