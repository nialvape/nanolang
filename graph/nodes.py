from langchain.messages import AnyMessage, SystemMessage, AIMessage
from typing import TypedDict, List, Optional, Literal
from PIL import Image
from io import BytesIO
from whatsapp import Whatsapp
from .tools import State, triage_agent, prompt_reader_agent, nanoclient, gemini, TriageSO, PromptSO
from pydantic import BaseModel, Field

wp = Whatsapp()


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
        state = add_assistant_msg(state, response.output)
        return state

    state = add_assistant_msg(state, """Hi! This bot is conected with nanobanana 🍌 Try this features:
    - text to image
    - image to image (prompt to edit your image)
    """)
    state["awaiting"] = "feature"
    return state

#txt_to_img Node
def txt_to_img(state: State):
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
                + state["messages"]
            )


#img_to_img Node
def img_to_img(state: State):
    state["messages"] += gemini.invoke(
        [SystemMessage(content="Tell to user this feature is not available")]
        + state["messages"]
    )
    return state