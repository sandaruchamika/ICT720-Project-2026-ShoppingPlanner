# from google import genai
# import os
# from dotenv import load_dotenv

# load_dotenv(dotenv_path="../../infra/.env")
# API_KEY = os.getenv("GEMINI_API_KEY")

# client = genai.Client(api_key=API_KEY)

# def list_available_models():
#     print(f"{'Model Name':<50} | {'Display Name':<30} | {'Methods'}")
#     print("-" * 110)
    
#     for model in client.models.list():
#         name = getattr(model, 'name', 'N/A')
#         display_name = getattr(model, 'display_name', 'N/A')
        
#         # รองรับทั้ง attribute name เก่าและใหม่
#         methods = getattr(model, 'supported_generation_methods', None) \
#                or getattr(model, 'supported_actions', [])
#         methods_str = ", ".join(methods) if methods else "N/A"
        
#         print(f"{name:<50} | {display_name:<30} | {methods_str}")

# if __name__ == "__main__":
#     list_available_models()

from PIL import Image
from google import genai
import sys
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="../../infra/.env")  # ปรับ path ให้ตรงกับ structure

API_KEY = os.getenv("GEMINI_API_KEY")
client  = genai.Client(api_key=API_KEY)

PROMPTS = {
    "general": """
        Analyze this image and describe:
        1. What objects or people are visible
        2. The environment or setting
        3. Any unusual or notable things
        Keep it concise within 3-4 sentences.
    """,

    "security": """
        You are a security camera AI. Analyze this image:
        1. How many people are present? What are they doing?
        2. Any suspicious behavior or objects?
        3. Overall safety assessment: NORMAL / WARNING / ALERT
        Be concise and factual.
    """,

    "shopping": """
        Analyze this image for shopping context:
        1. What products or items are visible?
        2. Estimate quantity or stock level if applicable
        3. Any pricing or label information visible?
        Be specific about product details.
    """,

    "thai": """
        วิเคราะห์ภาพนี้:
        1. มีอะไรในภาพบ้าง
        2. มีคนหรือไม่ (ถ้ามี: กี่คน ทำอะไร)
        3. มีสิ่งผิดปกติหรือไม่
        ตอบสั้นๆ ภายใน 3-4 ประโยค
    """,
}

def analyze(image_path: str, mode: str = "general"):
    image  = Image.open(image_path)
    prompt = PROMPTS.get(mode, PROMPTS["general"])

    print(f"Mode  : {mode}")
    print(f"Image : {image_path}")
    print("-" * 50)

    response = client.models.generate_content(
        model="gemini-2.0-flash",    # ← แก้ตรงนี้
        contents=[image, prompt]
    )
    print(response.text)


if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "test.jpg"
    mode       = sys.argv[2] if len(sys.argv) > 2 else "general"
    analyze(image_path, mode)