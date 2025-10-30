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

class GeneratedImage(TypedDict):
    prompt: str
    output: Image.Image

class State(TypedDict):
    messages: List[AnyMessage]
    current_node: str
    awaiting: str

wp = Whatsapp()

#MENU NODE

class TriageSO(BaseModel):
    interpreted_feature: Optional[Literal["text_to_image", "image_to_image"]] = Field(
        default=None, description="Interpreted feature."
    )
    output: Optional[str] = Field(
        default=None, description="Text asking to user for what feature they want to use if you don't understand"
    )

triage_agent = gemini.with_structured_output(TriageSO)

def add_assistant_msg(state: State, content: str) -> List[dict[str: str]]:
    state["messages"] += [AIMessage(content=content)]
    return state


#Triage Node
def triage(state: State) -> State:
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
        return

    state["messages"] += add_assitant_msg("""Hi! This bot is conected with nanobanana 🍌 Try this features:
    - text to image
    - image to image (prompt to edit your image)
    """)
    state["awaiting"] = "feature"

#txt_to_img Node
def text_to_image