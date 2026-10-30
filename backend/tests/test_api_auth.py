"""Tests de non-régression pour l'authentification HTTP Bearer."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import api_auth


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_token_serveur_absent_renvoie_503(monkeypatch):
    monkeypatch.setattr(api_auth, "_ADA_TOKEN", "")

    with pytest.raises(HTTPException) as caught:
        api_auth.require_token(None)

    assert caught.value.status_code == 503


@pytest.mark.parametrize("credentials", [None, _credentials("incorrect")])
def test_bearer_absent_ou_invalide_renvoie_401(monkeypatch, credentials):
    monkeypatch.setattr(api_auth, "_ADA_TOKEN", "secret-test")

    with pytest.raises(HTTPException) as caught:
        api_auth.require_token(credentials)

    assert caught.value.status_code == 401


def test_bearer_valide_est_accepte(monkeypatch):
    monkeypatch.setattr(api_auth, "_ADA_TOKEN", "secret-test")

    assert api_auth.require_token(_credentials("secret-test")) is None
