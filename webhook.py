import os
import logging
from fastapi import FastAPI, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from whatsapp import Whatsapp
from background_processor import process_message_background

wp = Whatsapp()

load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Verificación del webhook (GET request de Facebook)
@app.get("/webhook")
async def verify_webhook(
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge"),
):
    """Verifica el webhook cuando Facebook lo configura"""
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")
    
    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully")
        return int(challenge)
    else:
        logger.warning(f"Webhook verification failed. Mode: {mode}, Token match: {token == verify_token}")
        raise HTTPException(status_code=403, detail="Forbidden")

# Recibir mensajes del webhook (POST request de Facebook)
@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe mensajes de WhatsApp a través del webhook.
    
    Este endpoint responde rápidamente a Facebook y encola el procesamiento
    en background para evitar timeouts y bloqueos.
    """
    try:
        body = await request.json()
        logger.info(f"Received webhook notification")

        # Facebook envía las notificaciones en entry -> changes -> value
        if "object" in body and body["object"] == "whatsapp_business_account":
            entries = body.get("entry", [])
            
            for entry in entries:
                changes = entry.get("changes", [])
                
                for change in changes:
                    value = change.get("value", {})
                    
                    # Manejar mensajes - encolar para procesamiento en background
                    if "messages" in value:
                        messages = value.get("messages", [])
                        metadata = value.get("metadata", {})
                        
                        for message in messages:
                            # Encolar el procesamiento en background
                            # Esto permite que el webhook responda inmediatamente
                            background_tasks.add_task(
                                process_message_background,
                                message,
                                metadata
                            )
                    
                    # Manejar status updates (opcional, procesamiento rápido)
                    # Comentado porque genera mucho ruido en los logs
                    # if "statuses" in value:
                    #     statuses = value.get("statuses", [])
                    #     logger.info(f"Received status updates: {statuses}")

        # Responder inmediatamente a Facebook
        return JSONResponse(status_code=200, content={"status": "ok"})
    
    except Exception as e:
        logger.error(f"Error receiving webhook: {str(e)}", exc_info=True)
        # Aún así responder 200 para evitar reintentos de Facebook
        return JSONResponse(status_code=200, content={"status": "error"})

@app.get("/")
async def root():
    """Endpoint raíz para verificar que el servidor está funcionando"""
    return {"status": "ok", "message": "Webhook server is running"}

@app.get("/health")
async def health_check():
    """Endpoint de health check"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
