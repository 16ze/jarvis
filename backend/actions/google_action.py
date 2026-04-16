"""
Module d'actions Google (Gmail + Calendar).
Expose handle(tool_name, args, google_agent) pour dispatcher les outils Gmail/Calendar.

Confirmation obligatoire pour send_email et delete_event :
  - Si args["confirmed"] is True  → exécution directe
  - Sinon → retourne un message de confirmation à soumettre à l'utilisateur
"""

from typing import Any


async def handle(tool_name: str, args: dict[str, Any], google_agent: Any) -> str:
    """
    Dispatche les actions Google (Gmail + Calendar) vers google_agent.

    Outils supportés :
    - read_emails(query, max_results)
    - send_email(to, subject, body)          — confirmation requise
    - get_email_body(message_id)
    - list_events(max_results)
    - create_event(title, start, end, description, attendees)
    - find_event(query, max_results)
    - delete_event(event_id)                 — confirmation requise
    """
    try:
        # ── GMAIL ─────────────────────────────────────────────────────────────
        if tool_name == "read_emails":
            return google_agent.read_emails(
                max_results=int(args.get("max_results", 5)),
                query=args.get("query", "in:inbox"),
            )

        elif tool_name == "send_email":
            if not args.get("confirmed"):
                to = args.get("to", "")
                subject = args.get("subject", "")
                return (
                    f"Confirmation requise avant envoi.\n"
                    f"À : {to}\n"
                    f"Objet : {subject}\n"
                    f"Réponds 'oui' ou rappelle l'outil avec confirmed=true pour envoyer."
                )
            return google_agent.send_email(
                to=args["to"],
                subject=args["subject"],
                body=args["body"],
            )

        elif tool_name == "get_email_body":
            return google_agent.get_email_body(args["message_id"])

        # ── CALENDAR ──────────────────────────────────────────────────────────
        elif tool_name == "list_events":
            return google_agent.list_events(
                max_results=int(args.get("max_results", 10))
            )

        elif tool_name == "create_event":
            return google_agent.create_event(
                title=args["title"],
                start=args["start"],
                end=args["end"],
                description=args.get("description", ""),
                attendees=args.get("attendees", []),
            )

        elif tool_name == "find_event":
            return google_agent.find_event(
                query=args["query"],
                max_results=int(args.get("max_results", 5)),
            )

        elif tool_name == "delete_event":
            if not args.get("confirmed"):
                event_id = args.get("event_id", "")
                return (
                    f"Confirmation requise avant suppression de l'événement '{event_id}'.\n"
                    f"Rappelle l'outil avec confirmed=true pour confirmer la suppression."
                )
            return google_agent.delete_event(args["event_id"])

        return f"Outil Google inconnu : {tool_name}"

    except KeyError as e:
        return f"Erreur {tool_name} : paramètre manquant {e}"
    except Exception as e:
        return f"Erreur {tool_name} : {e}"
