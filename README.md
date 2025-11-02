# NanoLang 🌐 — WhatsApp Image Generation Bot

**NanoLang** is a WhatsApp bot powered by **LangGraph** that generates and edits images using **fal.ai's Nano-Banana** models.  
Messages flow through a conversational graph, dynamically routing users between features like **text-to-image** and **image-to-image editing**, with responses delivered directly on WhatsApp.

> 🧩 Built to learn LangGraph and experiment with audiovisual AI pipelines — the first public step of my journey as a builder.

---

## 🌱 About the Project

This project started as a hands-on way to explore **LangGraph**, my choosen framework to master after build some agents from scratch, and to experiment with audiovisual generation APIs.

NanoLang is both:
- a **learning playground** for LangChain graphs, designed to gain experience with image
- a **functional WhatsApp bot** that connects real users with multimodal AI features.

The core idea is simple: make AI image generation conversational — using WhatsApp as the interface.

---

## ⚙️ Features

- 💬 **WhatsApp Integration** — Full support for the WhatsApp Business Cloud API  
- 🎨 **Image Generation** — Create images from text using fal.ai Nano-Banana  
- 🪄 **Image Editing** — Modify existing images with natural-language instructions  
- 🖼️ **Multi-Image Support** — Combine or edit multiple images (up to 3 recommended)  
- 🔄 **Conversational Routing** — LangGraph nodes for dynamic task handling (`triage`, `txt_to_img`, `img_to_img`)  
- 🤖 **LLM-Powered Understanding** — Google Gemini for language interpretation and responses  

---

## 🧠 Architecture Overview

NanoLang is structured as a **LangGraph-based state machine**, with three key nodes:

| Node | Role |
|------|------|
| `triage` | Routes incoming messages to the right feature |
| `txt_to_img` | Handles text-to-image generation |
| `img_to_img` | Manages image editing requests |

---

## 🔧 Requirements

- Python 3.10+
- WhatsApp Business Account (Cloud API access)
- Google API Key (Gemini)
- fal.ai API Key
- Publicly accessible server for webhook handling

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/nanolang.git
cd nanolang

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # (use venv\Scripts\activate on Windows)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create and configure your environment file
cp .env_example .env
Then edit .env with your credentials:

env
WHATSAPP_TOKEN=your_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_VERIFY_TOKEN=your_verify_token_here
GOOGLE_API_KEY=your_google_api_key_here
FAL_KEY=your_fal_key_here
PORT=8000
🌐 WhatsApp Webhook Setup
Deploy NanoLang on a public server

Set your webhook URL to:
https://your-domain.com/webhook

Use the same verify token as in .env

Subscribe to:

messages

messaging_handovers

You can configure it from the Facebook Developer Console or through your own API script.

💻 Usage
Run the FastAPI server:

bash
uvicorn webhook:app --host 0.0.0.0 --port 8000
Once online, WhatsApp messages will be automatically routed and processed.

Example Interactions

🖋️ Text-to-Image

arduino
User: Generate an image of a cat wearing a space suit  
Bot: [Generates and sends image]
🪄 Image-to-Image

vbnet
User: [Sends image]  
Bot: What would you like to do with this image?  
User: Make the background blue and add stars  
Bot: [Edits and sends image]
🧩 Project Structure
pgsql
nanolang/
├── webhook.py              # FastAPI webhook server
├── whatsapp.py             # WhatsApp API wrapper
├── background_processor.py # Message processing logic
├── graph/
│   ├── graph.py            # LangGraph definition
│   ├── nodes.py            # Core nodes (triage, txt_to_img, img_to_img)
│   └── tools.py            # State definitions and AI clients
├── requirements.txt
└── .env_example
🧪 Development & Testing
To test the LangGraph logic interactively:

bash
jupyter notebook graph/test_graph.ipynb
Message Flow

WhatsApp webhook triggers webhook.py

Messages are queued and processed by background_processor.py

Session state is updated

LangGraph agent handles routing

Result is sent back to WhatsApp

🧱 Core Dependencies
langchain / langchain_openai / langchain_google_genai

fastapi + uvicorn

requests

pillow

fal-client

python-dotenv

🩵 Troubleshooting
Issue	Possible Fix
Webhook verification fails	Check that WHATSAPP_VERIFY_TOKEN matches your Facebook Developer Console settings
Images not generating	Confirm FAL_KEY validity and API quota
Messages not received	Verify webhook setup and phone number ID
LLM errors	Check your GOOGLE_API_KEY and Gemini quota

📜 License
[Add your license here]

🤝 Contributing
Pull requests, ideas and improvements are always welcome.
Feel free to open an issue or propose enhancements!

👨‍💻 **About the Author**  
Hi! I'm **Joaquín Peñalva** (20), an early-stage builder from Argentina exploring **Agentic Systems** and **Multi-Agent Systems (MAS)** powered by **LLMs**.  
NanoLang is part of a broader journey to deepen my understanding of **multi-agent orchestration**, **audiovisual AI**, and **conversational automation**.  

📎 [LinkedIn](https://www.linkedin.com/in/joaquin-peñalva-596898248)
