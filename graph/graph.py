from graph.nodes import triage, txt_to_img, img_to_img
from graph.tools import State
from typing import Literal
from langgraph.graph import StateGraph, START, END

graph = StateGraph(State)

graph.add_node("triage", triage)
graph.add_node("txt_to_img", txt_to_img)
graph.add_node("img_to_img", img_to_img)

graph.add_edge(START, "triage")

graph.add_conditional_edge(
    "triage",
    lambda state: state["current_node"] if state["awaiting"] != None else END,
    ["txt_to_img", "img_to_img", END]
)
