import os
import logging
import threading
import tempfile
import json
from typing import Dict, Any, Optional, List
from collections import deque
from PIL import Image
from io import BytesIO
import requests
from graph.tools import State
from graph.graph import agent
from whatsapp import Whatsapp
from langchain.messages import HumanMessage, SystemMessage

wp = Whatsapp()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sesiones compartidas (importadas desde webhook o gestionadas aquí)
# Por ahora, las gestionaremos aquí para evitar dependencias circulares
sessions: Dict[str, State] = {}
session_lock = threading.Lock()

# Cola de mensajes pendientes por número de teléfono
pending_messages: Dict[str, deque] = {}
# Flags de procesamiento activo por número
processing_flags: Dict[str, bool] = {}
# Lock para las colas y flags
queue_lock = threading.Lock()

def get_or_create_session(phone_number: str) -> State:
    """Obtiene o crea una sesión de forma thread-safe"""
    with session_lock:
        if phone_number not in sessions:
            sessions[phone_number] = {
                "messages": [],
                "current_node": "triage",
                "awaiting": None,
                "back": False,
                "user_last_prompt": None,
                "generated_image": None,
                "user_images": [],
            }
        return sessions[phone_number]

async def process_message_background(message: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """
    Procesa un mensaje completo en background.
    
    Esta función maneja todo el procesamiento del bot (texto, imágenes, etc.)
    de forma asíncrona para no bloquear el webhook.
    
    Los mensajes del mismo número se acumulan y se procesan juntos en una sola
    llamada al graph para evitar race conditions.
    
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
        
        logger.info(f"Received message {message_id} from {from_number}, type: {message_type}")
        
        # Marcar mensaje como leído inmediatamente
        if message_id:
            try:
                wp.mark_read(message_id)
            except Exception as e:
                logger.warning(f"Could not mark message as read: {e}")
        
        # Agregar mensaje a la cola o procesar directamente
        should_process = False
        with queue_lock:
            # Inicializar cola si no existe
            if from_number not in pending_messages:
                pending_messages[from_number] = deque()
            
            # Agregar mensaje a la cola
            pending_messages[from_number].append({
                "message": message,
                "metadata": metadata,
                "type": message_type
            })
            
            # Si ya hay un procesamiento activo, solo agregar a la cola y salir
            if processing_flags.get(from_number, False):
                logger.info(f"Processing active for {from_number}, message added to queue. Queue size: {len(pending_messages[from_number])}")
                return
            
            # Marcar como procesando DENTRO del lock para evitar race conditions
            processing_flags[from_number] = True
            should_process = True
        
        # Procesar todos los mensajes acumulados (solo si somos el que inició el procesamiento)
        if should_process:
            await process_all_pending_messages(from_number)
    
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        from_number = message.get("from")
        if from_number:
            try:
                wp.send_text(from_number, "❌ Ocurrió un error procesando tu mensaje. Intenta de nuevo.")
            except:
                pass

async def process_all_pending_messages(phone_number: str) -> None:
    """
    Procesa todos los mensajes pendientes de un número de teléfono.
    Agrega todos los mensajes a la sesión y llama al graph una sola vez.
    """
    while True:
        # Obtener todos los mensajes pendientes de forma thread-safe
        messages_to_process: List[Dict[str, Any]] = []
        with queue_lock:
            if phone_number in pending_messages:
                while pending_messages[phone_number]:
                    messages_to_process.append(pending_messages[phone_number].popleft())
        
        # Si no hay mensajes pendientes, salir del loop
        if not messages_to_process:
            break
        
        logger.info(f"Processing {len(messages_to_process)} message(s) for {phone_number}")
        
        try:
            # Obtener sesión de forma thread-safe
            # get_or_create_session ya maneja el lock internamente, no necesitamos otro lock aquí
            state = get_or_create_session(phone_number)
            
            # Contar mensajes antes de agregar nuevos
            messages_before = len(state.get("messages", []))
            
            # Agregar todos los mensajes a la sesión
            for msg_data in messages_to_process:
                message = msg_data["message"]
                message_type = msg_data["type"]
                
                # Procesar según el tipo de mensaje
                if message_type == "text":
                    text_body = message.get("text", {}).get("body", "")
                    state["messages"].append(HumanMessage(content=text_body))
                    logger.info(f"Added text message to session: {text_body[:50]}...")
                
                elif message_type == "image":
                    # Obtener información de la imagen
                    image_data = message.get("image", {})
                    image_id = image_data.get("id")
                    caption = image_data.get("caption")
                    
                    logger.info(f"Processing image message - image_id: {image_id}, caption: {caption if caption else 'None'}")
                    
                    if not image_id:
                        logger.warning(f"No image_id found in message")
                        wp.send_text(phone_number, "⚠️ No se pudo obtener la información de la imagen.")
                        msg_data["type"] = "image_failed"
                        continue
                    
                    try:
                        # Descargar la imagen de WhatsApp PRIMERO (sin notificar todavía)
                        # Las URLs de media de WhatsApp expiran rápidamente, así que descargamos inmediatamente
                        logger.info(f"Downloading image {image_id} for {phone_number}")
                        image_bytes = download_image_from_whatsapp(image_id)
                        
                        # Convertir a PIL Image
                        image = Image.open(BytesIO(image_bytes))
                        
                        # Guardar imagen en el estado
                        state["user_images"].append(image)
                        
                        # Ahora sí notificar al usuario que se recibió y procesó
                        wp.send_text(phone_number, "📸 Recibí tu imagen, procesándola...")
                        
                        state["messages"].append(SystemMessage(content=f"{len(state['user_images'])} {'Image' if len(state['user_images']) == 1 else 'Images'} added to chat"))

                        # Si hay caption, procesarlo como HumanMessage
                        if caption:
                            state["messages"].append(HumanMessage(content=f"Last image caption: {caption}"))
                        
                        # Cambiar al nodo de img_to_img
                        state["current_node"] = "img_to_img"
                        state["awaiting"] = None
                        
                        logger.info(f"Added image message to session successfully, total images: {len(state['user_images'])}")
                    except requests.exceptions.HTTPError as e:
                        # Si la imagen expiró o hay un error de descarga
                        error_msg = str(e)
                        if "400" in error_msg or "404" in error_msg:
                            logger.error(f"Error downloading image {image_id}: {e} - Media may have expired")
                            wp.send_text(phone_number, "⚠️ Lo siento, no pude descargar tu imagen. Es posible que haya expirado. Por favor, envía la imagen nuevamente.")
                        else:
                            logger.error(f"HTTP error downloading image {image_id}: {e}")
                            wp.send_text(phone_number, "⚠️ Ocurrió un error al descargar tu imagen. Por favor, intenta de nuevo.")
                        # Si hay caption, procesarlo como texto
                        if caption:
                            state["messages"].append(HumanMessage(content=caption))
                        # Marcar este mensaje como no procesable para el graph
                        msg_data["type"] = "image_failed"
                        continue
                    except Exception as e:
                        # Otros errores al procesar la imagen
                        logger.error(f"Error processing image: {e}", exc_info=True)
                        wp.send_text(phone_number, "❌ Ocurrió un error al procesar tu imagen. Por favor, intenta de nuevo.")
                        # Si hay caption, procesarlo como texto
                        if caption:
                            state["messages"].append(HumanMessage(content=caption))
                        # Marcar este mensaje como no procesable para el graph
                        msg_data["type"] = "image_failed"
                        continue
                
                elif message_type == "document":
                    logger.info("Document message received")
                    wp.send_text(phone_number, "Por ahora solo soportamos imágenes, no documentos 😅")
                    continue
                
                elif message_type == "audio" or message_type == "voice":
                    logger.info("Audio/Voice message received")
                    wp.send_text(phone_number, "Por ahora solo soportamos texto e imágenes 📝🖼️")
                    continue
                
                else:
                    logger.info(f"Unsupported message type: {message_type}")
                    wp.send_text(phone_number, f"Tipo de mensaje '{message_type}' no soportado aún 🤔")
                    continue
            
            # Verificar si se agregaron mensajes nuevos al estado en este batch
            messages_after = len(state.get("messages", []))
            messages_added = messages_after > messages_before
            
            # Solo ejecutar el graph si hay mensajes procesables (text o image)
            processable_messages = [m for m in messages_to_process if m["type"] in ["text", "image"]]
            
            # Ejecutar graph si hay mensajes procesables Y se agregaron mensajes al estado
            if processable_messages and messages_added:
                # Guardar estado actualizado después de agregar todos los mensajes/imágenes
                # antes de ejecutar el graph
                with session_lock:
                    sessions[phone_number] = state
                
                last_messages_count = len(state["messages"])
                state = agent.invoke(state)
                
                # Guardar estado actualizado de forma thread-safe
                with session_lock:
                    sessions[phone_number] = state
                
                # Enviar respuesta del asistente si hay mensajes nuevos
                new_messages_count = len(state["messages"]) - last_messages_count
                send_assistant_responses(state, phone_number, new_messages_count)
        
        except Exception as e:
            logger.error(f"Error processing messages for {phone_number}: {str(e)}", exc_info=True)
            try:
                wp.send_text(phone_number, "❌ Ocurrió un error procesando tu mensaje. Intenta de nuevo.")
            except:
                pass
        finally:
            # Verificar si hay más mensajes pendientes antes de marcar como no procesando
            with queue_lock:
                if phone_number in pending_messages and len(pending_messages[phone_number]) > 0:
                    # Hay más mensajes, continuar procesando
                    logger.info(f"More messages pending for {phone_number}, continuing processing")
                else:
                    # No hay más mensajes, marcar como no procesando
                    processing_flags[phone_number] = False
                    logger.info(f"Finished processing all messages for {phone_number}")
                    break


def download_image_from_whatsapp(media_id: str) -> bytes:
    """
    Descarga una imagen de WhatsApp usando el media ID.
    
    Para Cloud API, la descarga es en dos pasos:
    1. GET https://graph.facebook.com/v20.0/{MEDIA_ID} (sin phone_number_id)
    2. Descargar desde la URL que viene en la respuesta
    
    Las URLs de media de WhatsApp expiran rápidamente (típicamente después de 5 minutos),
    así que esta función debe llamarse lo antes posible después de recibir el mensaje.
    
    Args:
        media_id: ID del media en WhatsApp
    
    Returns:
        bytes: Contenido de la imagen
    
    Raises:
        requests.exceptions.HTTPError: Si hay un error HTTP (400, 404, etc.)
        ValueError: Si no se puede obtener la URL del media
    """
    # Paso 1: Obtener la URL privada del medio
    # Para Cloud API, NO se usa phone_number_id en el path
    url = f"{wp.base_url}/{media_id}"
    headers = {"Authorization": f"Bearer {wp.token}"}
    
    logger.info(f"Downloading image {media_id}")
    
    # Obtener la URL temporal del media con timeout corto
    # Las URLs expiran rápido, así que descargamos inmediatamente
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code != 200:
        logger.error(f"Media API error (status {response.status_code}): {response.text}")
    
    response.raise_for_status()
    
    media_info = response.json()
    media_url = media_info.get("url")
    mime_type = media_info.get("mime_type")
    
    if not media_url:
        error_detail = media_info.get("error", {}).get("message", "Unknown error")
        logger.error(f"No media URL in response: {error_detail}")
        raise ValueError(f"No se pudo obtener la URL del media: {error_detail}")
    
    logger.info(f"Obtained media URL (mime_type: {mime_type}), downloading...")
    
    # Paso 2: Descargar el binario usando esa URL
    # La URL expira; siempre pedirla y descargar enseguida
    image_response = requests.get(media_url, headers=headers, stream=True, timeout=30)
    image_response.raise_for_status()
    
    logger.info(f"Image downloaded, size: {len(image_response.content)} bytes")
    
    return image_response.content

def send_assistant_responses(state: State, phone_number: str, count: int = 0) -> None:
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
        last_ai_messages = []
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai_messages.append(msg)
            if (len(messages) - messages.index(msg)) == count:
                break
        # Enviar mensajes del asistente
        for message in reversed(last_ai_messages):
            if message and message.content:
                # Enviar el mensaje del asistente
                wp.send_text(phone_number, message.content)
        
        # Si hay una imagen generada, enviarla también (una sola vez)
        if state.get("generated_image"):
            try:
                # Guardar la imagen en un archivo temporal
                pil_image: Image.Image = state["generated_image"]
                tmp_file = None
                try:
                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                    pil_image.save(tmp_file.name, format='PNG')
                    tmp_file.close()  # Cerrar explícitamente antes de subir
                    
                    # Subir y enviar la imagen
                    media_id = wp.upload_media(tmp_file.name, mime_type='image/png')
                    wp.send_image(phone_number, media_id=media_id)
                    logger.info(f"Image sent successfully to {phone_number}")
                finally:
                    # Limpiar el archivo temporal
                    if tmp_file:
                        os.unlink(tmp_file.name)
                    # Resetear generated_image después de enviarla
                    state["generated_image"] = None
            except Exception as e:
                logger.error(f"Error sending image: {str(e)}", exc_info=True)
                # Asegurarse de resetear even si hay error
                state["generated_image"] = None
        
    except Exception as e:
        logger.error(f"Error sending assistant responses: {str(e)}", exc_info=True)
