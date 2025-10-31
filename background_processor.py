import os
import logging
import threading
from typing import Dict, Any, Optional
from PIL import Image
from io import BytesIO
import requests

from init import State, wp, triage, text_to_image, img_to_img, add_assistant_msg
from langchain.messages import HumanMessage

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sesiones compartidas (importadas desde webhook o gestionadas aquí)
# Por ahora, las gestionaremos aquí para evitar dependencias circulares
sessions: Dict[str, State] = {}
session_lock = threading.Lock()

def get_or_create_session(phone_number: str) -> State:
    """Obtiene o crea una sesión de forma thread-safe"""
    with session_lock:
        if phone_number not in sessions:
            sessions[phone_number] = {
                "messages": [],
                "current_node": "triage",
                "awaiting": None,
                "user_last_prompt": None,
                "generated_image": None,
            }
        return sessions[phone_number]

async def process_message_background(message: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """
    Procesa un mensaje completo en background.
    
    Esta función maneja todo el procesamiento del bot (texto, imágenes, etc.)
    de forma asíncrona para no bloquear el webhook.
    
    Args:
        message: Diccionario con el mensaje de WhatsApp
        metadata: Metadata del mensaje (phone_number_id, etc.)
    """
    try:
        message_id = message.get("id")
        from_number = message.get("from")
        message_type = message.get("type")
        
        if not from_number:
            logger.warning("Message without from number, skipping")
            return
        
        logger.info(f"Processing message {message_id} from {from_number}, type: {message_type}")
        
        # Marcar mensaje como leído inmediatamente
        if message_id:
            try:
                wp.mark_read(message_id)
            except Exception as e:
                logger.warning(f"Could not mark message as read: {e}")
        
        # Obtener sesión de forma thread-safe
        state = get_or_create_session(from_number)
        
        # Procesar según el tipo de mensaje
        if message_type == "text":
            await process_text_message_background(state, from_number, message)
        
        elif message_type == "image":
            await process_image_message_background(state, from_number, message)
        
        elif message_type == "document":
            logger.info("Document message received")
            wp.send_text(from_number, "Por ahora solo soportamos imágenes, no documentos 😅")
        
        elif message_type == "audio" or message_type == "voice":
            logger.info("Audio/Voice message received")
            wp.send_text(from_number, "Por ahora solo soportamos texto e imágenes 📝🖼️")
        
        else:
            logger.info(f"Unsupported message type: {message_type}")
            wp.send_text(from_number, f"Tipo de mensaje '{message_type}' no soportado aún 🤔")
        
        # Guardar estado actualizado de forma thread-safe
        with session_lock:
            sessions[from_number] = state
    
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        from_number = message.get("from")
        if from_number:
            try:
                wp.send_text(from_number, "❌ Ocurrió un error procesando tu mensaje. Intenta de nuevo.")
            except:
                pass

async def process_text_message_background(state: State, phone_number: str, message: Dict[str, Any]) -> None:
    """Procesa mensajes de texto usando toda la lógica del bot"""
    try:
        text_body = message.get("text", {}).get("body", "")
        logger.info(f"Processing text message from {phone_number}: {text_body[:50]}...")
        
        # Agregar mensaje del usuario al estado
        state["messages"].append(HumanMessage(content=text_body))
        
        # Procesar según el nodo actual
        current_node = state.get("current_node", "triage")
        
        if current_node == "triage":
            state = triage(state)
        
        elif current_node == "text_to_image":
            state = text_to_image(state)
            # Si no está awaiting, volver a triage
            if not state.get("awaiting"):
                state["current_node"] = "triage"
        
        elif current_node == "image_to_image":
            # Si hay una imagen en el estado, procesar imagen a imagen
            if state.get("generated_image"):
                state = img_to_img(state)
            else:
                # Si no hay imagen, volver a triage
                state["current_node"] = "triage"
                state = triage(state)
        
        # Enviar respuesta del asistente si hay mensajes nuevos
        send_assistant_responses(state, phone_number)
        
    except Exception as e:
        logger.error(f"Error in process_text_message_background: {str(e)}", exc_info=True)
        wp.send_text(phone_number, "❌ Ocurrió un error procesando tu mensaje de texto.")

async def process_image_message_background(state: State, phone_number: str, message: Dict[str, Any]) -> None:
    """Procesa mensajes con imágenes"""
    try:
        logger.info(f"Processing image message from {phone_number}")
        
        # Obtener información de la imagen
        image_data = message.get("image", {})
        image_id = image_data.get("id")
        caption = image_data.get("caption")
        
        # Notificar al usuario
        wp.send_text(phone_number, "📸 Recibí tu imagen, procesándola...")
        
        # Descargar la imagen de WhatsApp
        image_bytes = download_image_from_whatsapp(image_id)
        
        # Convertir a PIL Image
        image = Image.open(BytesIO(image_bytes))
        
        # Guardar imagen en el estado
        state["generated_image"] = image
        
        # Si hay caption, procesarlo como texto también
        if caption:
            state["messages"].append(HumanMessage(content=caption))
        
        # Cambiar al nodo de image_to_image
        state["current_node"] = "image_to_image"
        state["awaiting"] = None
        
        # Procesar según la lógica del bot
        state = img_to_img(state)
        
        # Enviar respuesta del asistente
        send_assistant_responses(state, phone_number)
        
        logger.info(f"Image processed successfully for {phone_number}")
    
    except Exception as e:
        logger.error(f"Error processing image message: {str(e)}", exc_info=True)
        wp.send_text(phone_number, "❌ Ocurrió un error al procesar tu imagen. Por favor, intenta de nuevo.")

def download_image_from_whatsapp(media_id: str) -> bytes:
    """
    Descarga una imagen de WhatsApp usando el media ID.
    
    Args:
        media_id: ID del media en WhatsApp
    
    Returns:
        bytes: Contenido de la imagen
    """
    try:
        # Primero obtener la URL del media
        url = f"{wp.base_url}/{wp.phone_number_id}/media/{media_id}"
        headers = {"Authorization": f"Bearer {wp.token}"}
        
        # Obtener la URL temporal del media
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        media_url = response.json().get("url")
        
        if not media_url:
            raise ValueError("No se pudo obtener la URL del media")
        
        # Descargar la imagen desde la URL temporal
        image_response = requests.get(media_url, headers=headers, stream=True)
        image_response.raise_for_status()
        
        return image_response.content
    
    except Exception as e:
        logger.error(f"Error downloading image from WhatsApp: {str(e)}", exc_info=True)
        raise

def send_assistant_responses(state: State, phone_number: str) -> None:
    """
    Envía las respuestas del asistente basadas en los mensajes AI en el estado.
    
    Esto busca mensajes AIMessage recientes que aún no se han enviado.
    """
    try:
        # Obtener los últimos mensajes del asistente
        # Por ahora, asumimos que si hay mensajes, el último es del asistente
        # En una implementación más sofisticada, podrías trackear qué mensajes ya se enviaron
        
        messages = state.get("messages", [])
        if not messages:
            return
        
        # Buscar el último mensaje del asistente
        from langchain.messages import AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg
                break
        
        if last_ai_message and last_ai_message.content:
            # Enviar el mensaje del asistente
            wp.send_text(phone_number, last_ai_message.content)
            
            # Si hay una imagen generada, enviarla también
            if state.get("generated_image"):
                # Por ahora, solo notificamos que hay una imagen
                # En el futuro podrías enviarla usando wp.send_image
                pass
        
    except Exception as e:
        logger.error(f"Error sending assistant responses: {str(e)}", exc_info=True)
