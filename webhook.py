from init import State
from langchain.messages import HumanMessage

#fake webhook listening
user_input = input("Write something: ")


phone = "5491150128981"
session: dict[str, State] = {}
while user_input != "EOF":
    flags = user_input.split(" ")
    if flags[0] == "-n" and flags[1].isdigit():
        phone = flags[1]
        print(f"phone number changed to {phone}")
        #fake webhook listening
        user_input = input("Write something: ")
        continue
    if flags[0] == "-n" and !(flags[1].isdigit()):
        print("just digits are allowed for -n")
        #fake webhook listening
        user_input = input("Write something: ")
        continue

    state = session.get(phone, {
        "messages": [],
        "current_node": "triage"
    })