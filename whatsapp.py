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
    
    def _normalize_phone(self, phone: str) -> str:
        """
        Normaliza el número de teléfono para WhatsApp.
        
        Si el número empieza con '549' (Argentina con 9), lo convierte a '54'
        Ejemplo: 5491150128981 -> 541150128981
        """
        if phone.startswith("549"):
            # Quitar el 9 después del código de país 54
            return "54" + phone[3:]
        return phone

    # ---------- Public API ----------
    def send_text(self, to: str, body: str) -> Dict[str, Any]:
        to = self._normalize_phone(to)
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
        to = self._normalize_phone(to)
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
        to = self._normalize_phone(to)
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
        to = self._normalize_phone(to)
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

    # ---------- Webhook configuration ----------
    def configure_webhook(
        self,
        webhook_url: str,
        verify_token: str,
        app_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Configura el webhook en Facebook API.
        
        Args:
            webhook_url: URL completa del webhook (ej: https://tudominio.com/webhook)
            verify_token: Token de verificación que usas en tu endpoint GET
            app_id: ID de la aplicación de Facebook (opcional, se puede obtener del token)
        
        Returns:
            Dict con la respuesta de la API de Facebook
        
        Note:
            También necesitas configurar manualmente los campos a suscribir en:
            https://developers.facebook.com/apps/{app_id}/webhooks/
            
            O usar la API de Subscriptions para suscribirte a los campos necesarios.
        """
        # Si no se proporciona app_id, intentar obtenerlo del token o del phone_number_id
        if not app_id:
            # Intentar obtener el app_id del entorno o del contexto
            app_id = os.getenv("FACEBOOK_APP_ID")
            if not app_id:
                raise ValueError(
                    "app_id is required. Set FACEBOOK_APP_ID environment variable "
                    "or pass it as parameter."
                )
        
        # URL para configurar el webhook
        url = f"{self.base_url}/{app_id}/subscriptions"
        
        # Campos a suscribir (mensajes de WhatsApp)
        # Puedes agregar más campos según necesites
        fields = [
            "messages",
            "messaging_handovers",
        ]
        
        payload = {
            "object": "whatsapp_business_account",
            "callback_url": webhook_url,
            "verify_token": verify_token,
            "fields": fields,
        }
        
        response = requests.post(url, headers=self._headers(), json=payload)
        self._raise_for_error(response)
        
        return response.json()
    
    def get_webhook_info(self, app_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene información sobre la configuración actual del webhook.
        
        Args:
            app_id: ID de la aplicación de Facebook
        
        Returns:
            Dict con la información del webhook
        """
        if not app_id:
            app_id = os.getenv("FACEBOOK_APP_ID")
            if not app_id:
                raise ValueError(
                    "app_id is required. Set FACEBOOK_APP_ID environment variable "
                    "or pass it as parameter."
                )
        
        url = f"{self.base_url}/{app_id}/subscriptions"
        response = requests.get(url, headers=self._headers())
        self._raise_for_error(response)
        
        return response.json()
    
    def delete_webhook(self, app_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Elimina la configuración del webhook.
        
        Args:
            app_id: ID de la aplicación de Facebook
        
        Returns:
            Dict con la respuesta de la API
        """
        if not app_id:
            app_id = os.getenv("FACEBOOK_APP_ID")
            if not app_id:
                raise ValueError(
                    "app_id is required. Set FACEBOOK_APP_ID environment variable "
                    "or pass it as parameter."
                )
        
        url = f"{self.base_url}/{app_id}/subscriptions"
        response = requests.delete(url, headers=self._headers())
        self._raise_for_error(response)
        
        return response.json()

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