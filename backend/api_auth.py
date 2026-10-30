"""Authentification HTTP partagée par les endpoints sensibles d'Ada."""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status


_bearer = HTTPBearer(auto_error=False)
_ADA_TOKEN = os.getenv("ADA_API_TOKEN", "")


def require_token(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """Échoue fermé si le secret serveur manque ou si le Bearer est invalide."""

    if not _ADA_TOKEN:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ADA_API_TOKEN non configuré",
        )
    if not creds or creds.credentials != _ADA_TOKEN:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token invalide ou manquant",
        )
