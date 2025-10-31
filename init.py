from dotenv import load_dotenv
load_dotenv()
import os
from langchain.tools import tool
from lanchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, SystemMessage, AIMessage
from typing import TypedDict, List
from PIL import Image
from io import BytesIO
from google import genai
from whatsapp import Whatsapp

gemini = init_chat_model(
    "gemini-2.5-flash"
)

nanoclient = genai.Client(
    api_key=os.environ.get("GOOGLE_NANO_API_KEY")
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

wp = Whatsapp()

#MENU NODE

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

def add_assistant_msg(state: State, content: str) -> List[dict[str: str]]:
    state["messages"] += [AIMessage(content=content)]
    return state


#Triage Node
def triage(state: State) -> State:
    """Routing node"""
    if state["current_node"] != "triage":
        return state

    if state["awaiting"] == "feature":
        response: TriageSO = triage_agent.invoke(
            [SystemMessage(content="You are a helpful bot conected with nanobana. Be funny!. Your task is to understand what feature the user want to use. posibles: 'text_to_image', 'image_to_image'")]
            + state["messages"]
        )
        if response.interpreted_feature:
            state["current_node"] = response.interpreted_feature
            state["awaiting"] = None
            return state
        state = add_asisstant_msg(state, response.output)
        return state

    state["messages"] += add_assitant_msg("""Hi! This bot is conected with nanobanana 🍌 Try this features:
    - text to image
    - image to image (prompt to edit your image)
    """)
    state["awaiting"] = "feature"
    return state

#txt_to_img Node
def text_to_image(state: State):
    """Process user request to generate an image with text only"""
    if state["awaiting"] == "prompt":
        response = prompt_reader_agent.invoke(
            [SystemMessage(content="")]
            + state["messages"]
        )
        if response.prompt:
            state["user_last_prompt"] = response.prompt
            state["awaiting"] = None
            response = nanoclient.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[state["user_last_prompt"]]
            )
            for part in response.candidates[0].content.parts:
                if part.incine_data is not None:
                    image = Image.open(BytesIO(part.incline_data.data))


            state["messages"] += gemini.invoke(
                [SystemMessage(content="User image was generated")]
            )


#img_to_img Node
def img_to_img(state: State):
    state["messages"] += gemini.invoke(
        [SystemMessage(content="Tell to user this feature is not available")]
        + state["messages"]
    )
    return state