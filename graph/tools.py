import os
import logging
import requests
from dotenv import load_dotenv
load_dotenv()
import fal_client
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import AnyMessage
from PIL import Image
from typing import TypedDict, List, Optional, Literal
from pydantic import BaseModel, Field
from io import BytesIO

logger = logging.getLogger(__name__)

gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GOOGLE_API_KEY")
)

# Wrapper para fal.ai usando el SDK oficial
class FalconClient:
    """Wrapper para fal.ai Model APIs usando el SDK oficial"""
    
    def generate_image(self, prompt: str, model: str = "fal-ai/nano-banana") -> Image.Image:
        """
        Genera una imagen usando fal.ai
        
        Args:
            prompt: El prompt de texto para generar la imagen
            model: El modelo de fal.ai a usar (default: fal-ai/nano-banana)
            
        Returns:
            PIL.Image.Image: La imagen generada
        """
        # Usar el SDK oficial que maneja todo el polling automáticamente
        handler = fal_client.submit(
            model,
            arguments={"prompt": prompt}
        )
        
        # Obtener el resultado
        result = handler.get()
        
        # Descargar la imagen desde la URL
        image_url = result["images"][0]["url"]
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        
        # Convertir a PIL Image
        return Image.open(BytesIO(image_response.content))
    
    def edit_image(self, prompt: str, images: List[Image.Image]) -> Image.Image:
        """
        Edita una imagen usando fal.ai nano-banana/edit
        
        Args:
            prompt: El prompt de edición para la imagen
            images: Las imagenes PIL a editar
            
        Returns:
            PIL.Image.Image: La imagen editada
        """
        # Subir todas las imágenes una por una a fal.ai
        # upload_image() solo acepta una imagen a la vez, no una lista
        image_urls = []
        for idx, img in enumerate(images):
            # Convertir a PIL Image si es necesario (por si se corrompió al guardar/recuperar el estado)
            if isinstance(img, BytesIO):
                logger.warning(f"Image {idx} is BytesIO, converting to PIL")
                img.seek(0)
                img = Image.open(img)
            elif not isinstance(img, Image.Image):
                if isinstance(img, bytes):
                    logger.warning(f"Image {idx} is bytes, converting to PIL")
                    img = Image.open(BytesIO(img))
                else:
                    raise ValueError(f"Expected PIL Image, BytesIO, or bytes at index {idx}, got {type(img)}")
            
            if not isinstance(img, Image.Image):
                raise ValueError(f"Failed to convert image {idx} to PIL Image")
            
            # Subir cada imagen a fal.ai temporalmente
            # upload_image acepta PIL Image y retorna directamente la URL como string
            image_url = fal_client.upload_image(img)
            image_urls.append(image_url)
            
        # Usar el SDK oficial con el endpoint de edición
        # El endpoint acepta image_urls (array) según la documentación oficial
        handler = fal_client.submit(
            "fal-ai/nano-banana/edit",
            arguments={
                "prompt": prompt,
                "image_urls": image_urls  # Array con todas las URLs subidas
            }
        )
        
        # Obtener el resultado
        result = handler.get()
        
        # Descargar la imagen editada desde la URL
        image_url = result["images"][0]["url"]
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        
        # Convertir a PIL Image
        return Image.open(BytesIO(image_response.content))

nanoclient = FalconClient()

class GeneratedImage(TypedDict):
    prompt: str
    output: Image.Image

class State(TypedDict):
    messages: List[AnyMessage]
    current_node: str
    awaiting: str
    back: bool
    user_last_prompt: str
    generated_image: Image.Image
    user_images: List[Image.Image]


class TriageSO(BaseModel):
    interpreted_feature: Optional[Literal["txt_to_img", "img_to_img"]] = Field(
        default=None, description="Interpreted feature."
    )
    output: Optional[str] = Field(
        default=None, description="Text asking to user for what feature they want to use if you don't understand"
    )

class PromptSO(BaseModel):
    user_prompt: Optional[str] = Field(default=None, description="User's prompt")
    output: Optional[str] = Field(default=None, description="Text asking to user to confirm or ask the prompt")
    other_feature: Optional[bool] = Field(default=False, description="True if user manifest do something else not related with txt_to_txt")

class EditImages(BaseModel):
    user_prompt: Optional[str] = Field(default=None, description="User's prompt. What to do with the image or images.")
    images_to_edit: Optional[List[int]] = Field(default=None, description="User's images's index to be used.")
    output: Optional[str] = Field(default=None, description="To ask the user if they have already sent all their images or if the request is not understood, always before filling out user_prompt or images_to_edit")
    other_feature: Optional[bool] = Field(default=False, description="True if user manifest do something not related with img_to_img")

triage_agent = gemini.with_structured_output(TriageSO)
prompt_reader_agent = gemini.with_structured_output(PromptSO)
edit_agent = gemini.with_structured_output(EditImages)