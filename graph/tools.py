import os
from dotenv import load_dotenv
load_dotenv()
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import AnyMessage
from google import genai
from PIL import Image
from typing import TypedDict, List, Optional, Literal
from pydantic import BaseModel, Field

gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GOOGLE_API_KEY")
)

nanoclient = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

class GeneratedImage(TypedDict):
    prompt: str
    output: Image.Image

class State(TypedDict):
    messages: List[AnyMessage]
    current_node: str
    awaiting: str
    user_last_prompt: str
    generated_image: Image.Image



class TriageSO(BaseModel):
    interpreted_feature: Optional[Literal["text_to_image", "image_to_image"]] = Field(
        default=None, description="Interpreted feature."
    )
    output: Optional[str] = Field(
        default=None, description="Text asking to user for what feature they want to use if you don't understand"
    )

class PromptSO(BaseModel):
    user_prompt: Optional[str] = Field(default=None, description="User's prompt")
    output: Optional[str] = Field(default=None, description="Text asking to user to confirm or ask the prompt")

triage_agent = gemini.with_structured_output(TriageSO)
prompt_reader_agent = gemini.with_structured_output(PromptSO)