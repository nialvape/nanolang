
#whatsap simulation
class Whatsapp():
    def send_message(phone: str, content: str, file: str | None = None):
        if not file:
            print(f"Message sent to: {phone}\nContent: {content}")
            return {"success": True}
        print(f"Message with file sent to: {phone}\nContent: text: {content}")
        return {"success": True}

           