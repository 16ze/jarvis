import os

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")


class StripeMCP:
    def __init__(self):
        self._stripe = None

    def _ensure_connected(self) -> bool:
        if not self._stripe:
            if not STRIPE_SECRET_KEY:
                return False
            import stripe as _stripe_lib
            _stripe_lib.api_key = STRIPE_SECRET_KEY
            self._stripe = _stripe_lib
        return True

    def list_customers(self, limit: int = 10, email: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            kwargs = {"limit": limit}
            if email:
                kwargs["email"] = email
            customers = self._stripe.Customer.list(**kwargs)
            if not customers.data:
                return "Aucun client trouvé."
            lines = []
            for c in customers.data:
                lines.append(
                    f"{c.get('name', '(sans nom)')} | {c.get('email', '?')} | "
                    f"id: {c.get('id')} | créé: {c.get('created')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def get_customer(self, customer_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            c = self._stripe.Customer.retrieve(customer_id)
            lines = [
                f"Nom: {c.get('name', '(sans nom)')}",
                f"Email: {c.get('email', '?')}",
                f"id: {c.get('id')}",
                f"Téléphone: {c.get('phone', '?')}",
                f"Devise: {c.get('currency', '?')}",
                f"Solde: {c.get('balance', 0) / 100:.2f}",
                f"Créé: {c.get('created')}",
                f"Description: {c.get('description', '')}",
            ]
            metadata = c.get("metadata", {})
            if metadata:
                lines.append(f"Metadata: {metadata}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def list_payments(self, limit: int = 10, customer_id: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            kwargs = {"limit": limit}
            if customer_id:
                kwargs["customer"] = customer_id
            payments = self._stripe.PaymentIntent.list(**kwargs)
            if not payments.data:
                return "Aucun paiement trouvé."
            lines = []
            for p in payments.data:
                amount = p.get("amount", 0) / 100
                currency = p.get("currency", "?").upper()
                status = p.get("status", "?")
                lines.append(
                    f"{amount:.2f} {currency} | statut: {status} | "
                    f"id: {p.get('id')} | créé: {p.get('created')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def list_invoices(self, limit: int = 10, customer_id: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            kwargs = {"limit": limit}
            if customer_id:
                kwargs["customer"] = customer_id
            invoices = self._stripe.Invoice.list(**kwargs)
            if not invoices.data:
                return "Aucune facture trouvée."
            lines = []
            for inv in invoices.data:
                amount = inv.get("amount_due", 0) / 100
                currency = inv.get("currency", "?").upper()
                status = inv.get("status", "?")
                number = inv.get("number", "?")
                lines.append(
                    f"[{status}] {number} | {amount:.2f} {currency} | "
                    f"id: {inv.get('id')} | créé: {inv.get('created')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def get_balance(self) -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            balance = self._stripe.Balance.retrieve()
            lines = ["Solde Stripe:"]
            for entry in balance.get("available", []):
                amount = entry.get("amount", 0) / 100
                currency = entry.get("currency", "?").upper()
                lines.append(f"  Disponible: {amount:.2f} {currency}")
            for entry in balance.get("pending", []):
                amount = entry.get("amount", 0) / 100
                currency = entry.get("currency", "?").upper()
                lines.append(f"  En attente: {amount:.2f} {currency}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def create_invoice_item(self, customer_id: str, amount_cents: int, currency: str, description: str) -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            item = self._stripe.InvoiceItem.create(
                customer=customer_id,
                amount=amount_cents,
                currency=currency.lower(),
                description=description,
            )
            return (
                f"Item de facture créé: '{description}' | "
                f"{amount_cents / 100:.2f} {currency.upper()} | id: {item.get('id')}"
            )
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"

    def send_invoice(self, invoice_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur Stripe: STRIPE_SECRET_KEY manquant dans les variables d'environnement."
        try:
            invoice = self._stripe.Invoice.finalize_invoice(invoice_id)
            sent = self._stripe.Invoice.send_invoice(invoice_id)
            return (
                f"Facture {invoice_id} finalisée et envoyée. "
                f"Statut: {sent.get('status')} | Numéro: {sent.get('number', '?')}"
            )
        except Exception as e:
            return f"Erreur Stripe: {str(e)}"
