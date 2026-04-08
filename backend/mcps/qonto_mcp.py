import os
import httpx

QONTO_LOGIN = os.getenv("QONTO_LOGIN")
QONTO_SECRET_KEY = os.getenv("QONTO_SECRET_KEY")
QONTO_ORGANIZATION_SLUG = os.getenv("QONTO_ORGANIZATION_SLUG")
QONTO_BASE_URL = "https://thirdparty.qonto.com/v2"


class QontoMCP:
    def __init__(self):
        self._login = QONTO_LOGIN
        self._secret_key = QONTO_SECRET_KEY
        self._organization_slug = QONTO_ORGANIZATION_SLUG

    def _check_config(self) -> str | None:
        if not self._login or not self._secret_key or not self._organization_slug:
            missing = [
                k for k, v in {
                    "QONTO_LOGIN": self._login,
                    "QONTO_SECRET_KEY": self._secret_key,
                    "QONTO_ORGANIZATION_SLUG": self._organization_slug,
                }.items() if not v
            ]
            return f"Erreur Qonto: variables manquantes: {', '.join(missing)}"
        return None

    def _headers(self) -> dict:
        return {
            "Authorization": f"{self._login}:{self._secret_key}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        response = httpx.get(
            f"{QONTO_BASE_URL}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_balance(self) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            data = self._get(f"/organizations/{self._organization_slug}")
            organization = data.get("organization", {})
            bank_accounts = organization.get("bank_accounts", [])
            if not bank_accounts:
                return "Aucun compte bancaire trouvé."
            lines = ["Soldes des comptes Qonto:"]
            for account in bank_accounts:
                balance = account.get("balance", 0)
                currency = account.get("currency", "EUR")
                iban = account.get("iban", "?")
                slug = account.get("slug", "?")
                lines.append(f"  [{slug}] IBAN: {iban} | Solde: {balance:.2f} {currency}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Qonto: {str(e)}"

    def list_transactions(self, iban: str = "", limit: int = 25, status: str = "completed") -> str:
        err = self._check_config()
        if err:
            return err
        try:
            params = {
                "slug": self._organization_slug,
                "status[]": status,
                "per_page": limit,
            }
            if iban:
                params["iban"] = iban
            data = self._get("/transactions", params=params)
            transactions = data.get("transactions", [])
            if not transactions:
                return "Aucune transaction trouvée."
            lines = []
            for t in transactions:
                amount = t.get("amount", 0)
                currency = t.get("currency", "EUR")
                side = t.get("side", "?")
                label = t.get("label", "(sans libellé)")
                emitted_at = t.get("emitted_at", "?")
                sign = "+" if side == "credit" else "-"
                lines.append(
                    f"{emitted_at[:10] if emitted_at != '?' else '?'} | "
                    f"{sign}{amount:.2f} {currency} | {label} | statut: {t.get('status', '?')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Qonto: {str(e)}"

    def get_organization(self) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            data = self._get(f"/organizations/{self._organization_slug}")
            org = data.get("organization", {})
            bank_accounts = org.get("bank_accounts", [])
            lines = [
                f"Slug: {org.get('slug', '?')}",
                f"Comptes bancaires: {len(bank_accounts)}",
            ]
            for account in bank_accounts:
                lines.append(
                    f"  - IBAN: {account.get('iban', '?')} | "
                    f"BIC: {account.get('bic', '?')} | "
                    f"Devise: {account.get('currency', '?')} | "
                    f"Solde: {account.get('balance', 0):.2f}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Qonto: {str(e)}"

    def list_memberships(self) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            data = self._get("/memberships")
            memberships = data.get("memberships", [])
            if not memberships:
                return "Aucun membre trouvé."
            lines = []
            for m in memberships:
                first = m.get("first_name", "")
                last = m.get("last_name", "")
                email = m.get("email", "?")
                role = m.get("role", "?")
                lines.append(f"{first} {last} | {email} | rôle: {role}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Qonto: {str(e)}"
