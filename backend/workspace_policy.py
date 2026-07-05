"""Policy centrale pour les actions ADA OS Environment."""

from __future__ import annotations


class WorkspacePolicy:
    CONFIRM_KEYWORDS = {
        "send",
        "email",
        "message",
        "publish",
        "post",
        "delete",
        "remove",
        "overwrite",
        "payment",
        "purchase",
        "subscribe",
        "credential",
        "secret",
        "env",
        "execute_pc_task",
        "shell",
    }
    DENY_KEYWORDS = {"rm -rf /", "format disk", "erase disk"}

    def classify(self, action: dict) -> str:
        text = f"{action.get('type', '')} {action.get('name', '')} {action.get('description', '')}".lower()
        if any(keyword in text for keyword in self.DENY_KEYWORDS):
            return "deny"
        if any(keyword in text for keyword in self.CONFIRM_KEYWORDS):
            return "confirm"
        return "allow"
