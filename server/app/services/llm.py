from PIL import Image
from google import genai
from io import BytesIO
import os

API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyA8lMzrprXinbmmEJigUSP8kHbK1iRpKDY")
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

def analyze_image(jpg_bytes: bytes, mode: str = "general") -> str:
    image  = Image.open(BytesIO(jpg_bytes))
    prompt = PROMPTS.get(mode, PROMPTS["general"])

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt]
    )
    return response.text