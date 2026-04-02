import os
import json
import io
import warnings

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents.readonly",
]

_BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
CREDENTIALS_FILE = os.path.join(_BACKEND_DIR, "google_credentials.json")
TOKEN_FILE = os.path.join(_BACKEND_DIR, "google_token.json")


def _get_google_services():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials introuvables. Placez le fichier OAuth2 ici: {CREDENTIALS_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    return drive, sheets, docs


class DriveMCP:
    def __init__(self):
        self._drive = None
        self._sheets = None
        self._docs = None
        if not _GOOGLE_AVAILABLE:
            warnings.warn("[DriveMCP] google-api-python-client non installé.", stacklevel=2)

    def _ensure_connected(self):
        if not _GOOGLE_AVAILABLE:
            raise RuntimeError("google-api-python-client non installé. Lancer: pip install google-api-python-client google-auth-oauthlib")
        if not self._drive or not self._sheets or not self._docs:
            self._drive, self._sheets, self._docs = _get_google_services()

    def list_files(self, query: str = "", limit: int = 10) -> str:
        try:
            self._ensure_connected()
            q = query if query else "trashed = false"
            results = self._drive.files().list(
                q=q,
                pageSize=limit,
                fields="files(id, name, mimeType, modifiedTime, size)",
            ).execute()
            files = results.get("files", [])
            if not files:
                return "Aucun fichier trouvé."
            lines = []
            for f in files:
                size = f.get("size", "?")
                size_str = f"{int(size) // 1024} Ko" if size != "?" else "?"
                lines.append(
                    f"{f.get('name', '?')} | {f.get('mimeType', '?')} | "
                    f"modifié: {f.get('modifiedTime', '?')[:10]} | "
                    f"taille: {size_str} | id: {f.get('id')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Drive: {str(e)}"

    def read_file(self, file_id: str) -> str:
        try:
            self._ensure_connected()
            file_meta = self._drive.files().get(
                fileId=file_id, fields="name, mimeType"
            ).execute()
            mime_type = file_meta.get("mimeType", "")

            # Google Docs → export en texte
            if mime_type == "application/vnd.google-apps.document":
                return self.read_doc(file_id)

            # Fichiers texte standards
            export_types = [
                "text/plain",
                "text/csv",
                "text/html",
                "application/json",
            ]
            if any(mime_type.startswith(t) for t in export_types):
                request = self._drive.files().get_media(fileId=file_id)
                buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                return buffer.getvalue().decode("utf-8", errors="ignore")[:3000]

            return f"Type MIME '{mime_type}' non lisible en texte brut. Utilisez read_doc pour les Google Docs."
        except Exception as e:
            return f"Erreur Drive: {str(e)}"

    def upload_file(self, local_path: str, folder_id: str = "") -> str:
        try:
            self._ensure_connected()
            if not os.path.exists(local_path):
                return f"Erreur Drive: fichier introuvable: {local_path}"
            file_name = os.path.basename(local_path)
            file_metadata = {"name": file_name}
            if folder_id:
                file_metadata["parents"] = [folder_id]
            media = MediaFileUpload(local_path, resumable=True)
            uploaded = self._drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
            ).execute()
            return (
                f"Fichier '{uploaded.get('name')}' uploadé. "
                f"id: {uploaded.get('id')} | lien: {uploaded.get('webViewLink', '?')}"
            )
        except Exception as e:
            return f"Erreur Drive: {str(e)}"

    def read_sheet(self, spreadsheet_id: str, range: str = "Sheet1!A1:Z100") -> str:
        try:
            self._ensure_connected()
            result = self._sheets.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range,
            ).execute()
            values = result.get("values", [])
            if not values:
                return "Plage vide ou aucune donnée."
            lines = []
            for row in values:
                lines.append(" | ".join(str(cell) for cell in row))
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Sheets: {str(e)}"

    def write_sheet(self, spreadsheet_id: str, range: str, values_json: str) -> str:
        try:
            self._ensure_connected()
            values = json.loads(values_json)
            body = {"values": values}
            result = self._sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()
            updated = result.get("updatedCells", 0)
            return f"{updated} cellule(s) mises à jour dans {range}."
        except Exception as e:
            return f"Erreur Sheets: {str(e)}"

    def append_sheet(self, spreadsheet_id: str, range: str, values_json: str) -> str:
        try:
            self._ensure_connected()
            values = json.loads(values_json)
            body = {"values": values}
            result = self._sheets.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            updates = result.get("updates", {})
            updated = updates.get("updatedCells", 0)
            return f"{updated} cellule(s) ajoutées dans {range}."
        except Exception as e:
            return f"Erreur Sheets: {str(e)}"

    def read_doc(self, doc_id: str) -> str:
        try:
            self._ensure_connected()
            document = self._docs.documents().get(documentId=doc_id).execute()
            title = document.get("title", "?")
            content = document.get("body", {}).get("content", [])
            lines = [f"Titre: {title}\n"]
            for element in content:
                paragraph = element.get("paragraph")
                if not paragraph:
                    continue
                para_elements = paragraph.get("elements", [])
                text = "".join(
                    el.get("textRun", {}).get("content", "")
                    for el in para_elements
                )
                text = text.rstrip("\n")
                if text:
                    lines.append(text)
            return "\n".join(lines)[:4000]
        except Exception as e:
            return f"Erreur Docs: {str(e)}"
