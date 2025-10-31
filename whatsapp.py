import os
import mimetypes
from typing import Any, Dict, Optional

import requests


class Whatsapp:
    """Lightweight wrapper for the WhatsApp Business Cloud API.

    Environment variables used by default:
      - WHATSAPP_TOKEN: Meta Graph API access token
      - WHATSAPP_PHONE_NUMBER_ID: Phone number ID from WhatsApp Business
      - WHATSAPP_API_VERSION: Graph API version (default: v20.0)
    """

    def __init__(
        self,
        token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> None:
        self.token = token or os.getenv("WHATSAPP_TOKEN") or ""
        self.phone_number_id = (
            phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID") or ""
        )
        self.api_version = api_version or os.getenv("WHATSAPP_API_VERSION") or "v20.0"

        if not self.token:
            raise ValueError("Missing WHATSAPP_TOKEN")
        if not self.phone_number_id:
            raise ValueError("Missing WHATSAPP_PHONE_NUMBER_ID")

        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    # ---------- Internal helpers ----------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _messages_endpoint(self) -> str:
        return f"{self.base_url}/{self.phone_number_id}/messages"

    # ---------- Public API ----------
    def send_text(self, to: str, body: str) -> Dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        response = requests.post(self._messages_endpoint(), headers=self._headers(), json=payload)
        self._raise_for_error(response)
        return response.json()

    def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[list] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components
        response = requests.post(self._messages_endpoint(), headers=self._headers(), json=payload)
        self._raise_for_error(response)
        return response.json()

    def upload_media(self, file_path: str, mime_type: Optional[str] = None) -> str:
        """Upload media and return media ID."""
        url = f"{self.base_url}/{self.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self.token}"}

        guessed = mime_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, guessed)}
            data = {"messaging_product": "whatsapp"}
            response = requests.post(url, headers=headers, data=data, files=files)
        self._raise_for_error(response)
        media_id = response.json().get("id")
        if not media_id:
            raise RuntimeError("Failed to obtain media ID from upload response")
        return media_id

    def send_image(
        self,
        to: str,
        *,
        image_url: Optional[str] = None,
        media_id: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        image_payload: Dict[str, Any] = {}
        if image_url:
            image_payload["link"] = image_url
        elif media_id:
            image_payload["id"] = media_id
        else:
            raise ValueError("Either image_url or media_id must be provided")
        if caption:
            image_payload["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
        response = requests.post(self._messages_endpoint(), headers=self._headers(), json=payload)
        self._raise_for_error(response)
        return response.json()

    def send_document(
        self,
        to: str,
        *,
        document_url: Optional[str] = None,
        media_id: Optional[str] = None,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc_payload: Dict[str, Any] = {}
        if document_url:
            doc_payload["link"] = document_url
        elif media_id:
            doc_payload["id"] = media_id
        else:
            raise ValueError("Either document_url or media_id must be provided")
        if filename:
            doc_payload["filename"] = filename
        if caption:
            doc_payload["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": doc_payload,
        }
        response = requests.post(self._messages_endpoint(), headers=self._headers(), json=payload)
        self._raise_for_error(response)
        return response.json()

    def mark_read(self, message_id: str) -> Dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        response = requests.post(self._messages_endpoint(), headers=self._headers(), json=payload)
        self._raise_for_error(response)
        return response.json()

    # ---------- Backward-compatible convenience ----------
    def send_message(self, phone: str, content: str, file: Optional[str] = None) -> Dict[str, Any]:
        """Compatibility shim with previous interface.

        - If file is None: sends a text message with content
        - If file is provided and is a local path: uploads and sends as document with caption=content
        - If file looks like a URL (http/https): sends document by link with caption=content
        """
        if not file:
            return self.send_text(phone, content)

        is_url = file.startswith("http://") or file.startswith("https://")
        if is_url:
            return self.send_document(phone, document_url=file, caption=content)

        media_id = self.upload_media(file)
        return self.send_document(phone, media_id=media_id, caption=content)

    # ---------- Error handling ----------
    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            # Try to include Graph API error details if present
            try:
                details = response.json()
            except Exception:
                details = {"raw": response.text}
            raise requests.HTTPError(f"WhatsApp API error: {details}") from exc