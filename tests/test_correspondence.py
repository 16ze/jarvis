"""Tests de l'assistant de correspondance (backend/correspondence.py).

L'enjeu principal n'est pas la qualité de rédaction : c'est qu'AUCUN message
ne parte sans accord explicite. C'est la parole de Bryan qui est engagée.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from correspondence import (  # noqa: E402
    CorrespondenceAssistant,
    Message,
    _parser_instagram,
    _parser_mails,
)


class FauxGoogle:
    def __init__(self):
        self.envois = []

    def send_email(self, to, subject, body):
        self.envois.append({"to": to, "subject": subject, "body": body})
        return "ok"


def _assistant(reponse="Réponse type.", manque="", google=None):
    class _Client:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**kw):
                    import json
                    import types as t
                    r = t.SimpleNamespace()
                    r.text = json.dumps({"reponse": reponse, "confiance": 0.9,
                                         "manque": manque})
                    return r
    return CorrespondenceAssistant(google_agent=google or FauxGoogle(), client=_Client())


def _messages(n=2):
    return [Message(str(i), "mail", f"exp{i}@test.com", f"Sujet {i}", f"Corps {i}")
            for i in range(1, n + 1)]


# ─── SÛRETÉ : le cœur du sujet ────────────────────────────────────────────────

def test_nothing_is_sent_when_drafting():
    """Rédiger ne doit JAMAIS envoyer."""
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all(_messages()))
    assert google.envois == []


def test_review_states_nothing_was_sent():
    a = _assistant()
    asyncio.run(a.draft_all(_messages()))
    assert "Rien n'est envoyé" in a.to_review()


def test_send_requires_explicit_call():
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all(_messages()))
    assert google.envois == []
    asyncio.run(a.send())
    assert len(google.envois) == 2


def test_only_selected_drafts_are_sent():
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all(_messages(3)))
    asyncio.run(a.send([2]))
    assert len(google.envois) == 1
    assert google.envois[0]["to"] == "exp2@test.com"


def test_incomplete_draft_is_never_sent():
    """Un brouillon avec [À COMPLÉTER] n'engage pas Bryan, même approuvé."""
    google = FauxGoogle()
    a = _assistant(reponse="Le délai est de [À COMPLÉTER : durée].", google=google)
    asyncio.run(a.draft_all(_messages(1)))
    res = asyncio.run(a.send())
    assert google.envois == []
    assert "manque" in res


def test_missing_information_blocks_sending():
    google = FauxGoogle()
    a = _assistant(reponse="Réponse.", manque="le prix exact", google=google)
    asyncio.run(a.draft_all(_messages(1)))
    asyncio.run(a.send())
    assert google.envois == []


def test_discard_sends_nothing():
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all(_messages()))
    res = a.discard()
    assert google.envois == []
    assert "Rien n'a été envoyé" in res
    assert a.pending == []


def test_sent_drafts_are_not_resent():
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all(_messages()))
    asyncio.run(a.send())
    asyncio.run(a.send())
    assert len(google.envois) == 2  # pas 4


# ─── Cycle ────────────────────────────────────────────────────────────────────

def test_review_lists_every_draft():
    a = _assistant()
    asyncio.run(a.draft_all(_messages(3)))
    revue = a.to_review()
    for i in (1, 2, 3):
        assert f"exp{i}@test.com" in revue


def test_reply_subject_is_prefixed():
    google = FauxGoogle()
    a = _assistant(google=google)
    asyncio.run(a.draft_all([Message("1", "mail", "x@y.z", "Question", "corps")]))
    asyncio.run(a.send())
    assert google.envois[0]["subject"].startswith("Re:")


def test_review_without_drafts():
    assert "Aucun brouillon" in _assistant().to_review()


def test_send_without_drafts_is_safe():
    assert "Aucun brouillon" in asyncio.run(_assistant().send())


# ─── Analyse des sources ──────────────────────────────────────────────────────

def test_mail_parsing_extracts_sender_and_subject():
    brut = ("De: client@exemple.com\nObjet: Devis\nBonjour, quel est le prix ?\n"
            "De: ami@exemple.com\nObjet: Salut\nOn se voit ?")
    messages = _parser_mails(brut, 5)
    assert len(messages) == 2
    assert messages[0].expediteur == "client@exemple.com"
    assert messages[0].sujet == "Devis"


def test_mail_parsing_handles_empty_input():
    assert _parser_mails("", 5) == []


def test_instagram_parsing_skips_navigation_labels():
    contenu = "Instagram\nMessages\nMarie Dupont\nSalut, ça va ?\nAccueil\nExplorer"
    messages = _parser_instagram(contenu, 5)
    noms = [m.expediteur for m in messages]
    assert "Marie Dupont" in noms
    assert "Messages" not in noms and "Accueil" not in noms
