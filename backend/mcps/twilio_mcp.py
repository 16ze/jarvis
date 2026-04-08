import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Variables d'environnement Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "") # Le numéro Twilio "from_"

class TwilioMCP:
    def __init__(self):
        self._client = None
        self._ensure_connected()

    def _ensure_connected(self) -> bool:
        """
        Tente de se connecter au client Twilio.
        Retourne False si les identifiants sont manquants ou si la connexion échoue.
        """
        if self._client:
            return True
        
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
            print("[TWILIO] Erreur: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN ou TWILIO_PHONE_NUMBER manquant.")
            return False
        
        try:
            self._client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            return True
        except Exception as e:
            print(f"[TWILIO] Erreur lors de l'initialisation du client Twilio: {e}")
            self._client = None # S'assurer que le client est None en cas d'échec
            return False

    def send_sms(self, to: str, body: str) -> str:
        """
        Envoie un message SMS via Twilio.

        Args:
            to (str): Le numéro de téléphone du destinataire au format international (ex: +33612345678).
            body (str): Le contenu du message SMS à envoyer.

        Returns:
            str: Un message de succès avec le SID du message, ou un message d'erreur.
        """
        if not self._ensure_connected():
            return "Erreur: Le client Twilio n'est pas configuré ou connecté. Vérifiez les variables d'environnement."

        try:
            message = self._client.messages.create(
                to=to,
                from_=TWILIO_PHONE_NUMBER,
                body=body
            )
            return f"SMS envoyé avec succès. SID: {message.sid}"
        except TwilioRestException as e:
            # Gérer les erreurs spécifiques de l'API Twilio
            return f"Erreur Twilio lors de l'envoi du SMS: {e.msg} (Code: {e.code})"
        except Exception as e:
            # Gérer toute autre erreur inattendue
            return f"Une erreur inattendue est survenue lors de l'envoi du SMS: {e}"