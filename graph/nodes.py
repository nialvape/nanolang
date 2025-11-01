import logging
from langchain.messages import AnyMessage, SystemMessage, AIMessage
from typing import TypedDict, List, Optional, Literal
from PIL import Image
from .tools import State, triage_agent, edit_agent, prompt_reader_agent, nanoclient, gemini, TriageSO, PromptSO

logger = logging.getLogger(__name__)


def add_assistant_msg(state: State, content: str) -> List[dict[str: str]]:
    state["messages"] += [AIMessage(content=content)]
    return state


#Triage Node
def triage(state: State) -> State:
    """Routing/menu node"""
    logger.info("entrando a triage")
    if state["current_node"] != "triage":
        logger.info(f"yendo a {state['current_node']}")
        return state

    if state["awaiting"] == "feature":
        response: TriageSO = triage_agent.invoke(
            [SystemMessage(content=""""
            You are a fun AI Agent, expert in generating and editing images with nanobanana🍌. Your task is detect user intention.
            Explain what you can do 🎯 if user don't get it. 
            Actual features:
                - generation of images from text
                - editing images with natural language
                - editing or generating images with more than one input image, example: generate an image of this person [image 1] happily showing this product [image 2].
            """)]
            + state["messages"]
        )
        if response.interpreted_feature:
            state["current_node"] = response.interpreted_feature
            state["awaiting"] = None
            logger.info(f"yendo a {state['current_node']}")
            return state
        state = add_assistant_msg(state, response.output)
        return state

    response: TriageSO = triage_agent.invoke(
        [SystemMessage(content=f""""
        You are a fun AI Agent, expert in generating and editing images with nanobanana🍌.
        Greet 👋 the user and explain what you can do 🎯. 
        Actual features:
            - generation of images from text
            - editing images with natural language
            - editing or generating images with more than one input image
        """)]
        + state["messages"]
    )
    if response.interpreted_feature:
        state["current_node"] = response.interpreted_feature
        state["awaiting"] = None
        logger.info(f"yendo a {state['current_node']}")

        return state

    state = add_assistant_msg(state, response.output)
    state["awaiting"] = "feature"

    return state

#txt_to_img Node
def txt_to_img(state: State):
    """Process user request to generate an image with text only"""
    logger.info("estamos en a text to image")

    response = prompt_reader_agent.invoke(
        [SystemMessage(content="""
        You are a fun AI Agent, expert in generating and editing images with nanobanana🍌. Now in txt_to_img feature ✍ -> 📷.
        If user provide a prompt, rewrite it just correcting prossible typos, not modify anything else. Use 'output' to ask for a prompt, clarify the actual one or explain something to the user.
        """)]
        + state["messages"]
    )

    if response.other_feature:
        state["back"] = True
        state["current_node"] = "triage"
        state["awaiting"] = "feature"
        return state

    if response.user_prompt:
        state["user_last_prompt"] = response.user_prompt
        state["awaiting"] = None
        try:
            image = nanoclient.generate_image(state["user_last_prompt"])
            response = gemini.invoke(
                [SystemMessage(content="User image was generated")]
                + state["messages"]
            )
            state["messages"].append(response)
            state["generated_image"] = image
            state["current_node"] = "triage"
            state["awaiting"] = "feature"
            return state
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            response = gemini.invoke(
                [SystemMessage(content="There was an error generating the image")]
                + state["messages"]
            )
            state["messages"].append(response)
            state["current_node"] = "triage"
            state["awaiting"] = "feature"
            return state

    state = add_assistant_msg(state, response.output)
    return state


#img_to_img Node
def img_to_img(state: State):
    """Process user request to edit an image with a prompt"""
    logger.info(f"estamos en image to image")

    response = edit_agent.invoke(
        [SystemMessage(content=f"""
        You are a fun AI Agent, expert in generating and editing images with nanobanana🍌. Now in img_to_img feature ✍ -> 📷.
        Use the 'output' to ask the user if they have already sent all their images or if the request is not understood, ALWAYS BEFORE filling out user_prompt or images_to_edit.
        DON'T FILL OUT user_prompt or images_to_edit IF THE USER HASN'T SENT ALL THEIR IMAGES and CONFIRM WHAT THEY WANT TO DO WITH THE IMAGES.
        Images count in chat: {len(state["user_images"])}. Tell to user that use up to 3 get better results.
        The image indices are ascending starting with 0 in the order in which the user sent them.
        Rewrite provided prompt just correcting prossible typos and translating to english for better results.
        """)]
        + state["messages"]
    )

    if response.other_feature:
        state["back"] = True
        state["current_node"] = "triage"
        state["awaiting"] = "feature"
        return state

    if response.user_prompt is not None and len(response.images_to_edit) > 0:
        logger.info("llm lleno el prompt y las imagenes")
        state["user_last_prompt"] = response.user_prompt
        state["awaiting"] = None

        try:
            images = []
            for i in response.images_to_edit:
                images.append(state["user_images"][i])

            # Editar la imagen
            edited_image: Image.Image = nanoclient.edit_image(state["user_last_prompt"], images)
            response = gemini.invoke(
                [SystemMessage(content="User image was edited successfully 😄")]
                + state["messages"]
            )
            state["messages"].append(response)
            state["generated_image"] = edited_image
            state["current_node"] = "triage"
            state["awaiting"] = "feature"
            return state

        except Exception as e:
            logger.error(f"Error editing image: {e}", exc_info=True)
            response = gemini.invoke(
                [SystemMessage(content="There was an error editing the image 😓")]
                + state["messages"]
            )
            state["messages"].append(response)
            state["current_node"] = "triage"
            state["awaiting"] = "feature"
            return state

    state = add_assistant_msg(state, response.output)
    return state