from PIL import Image
from google import genai
from io import BytesIO
from dotenv import load_dotenv
import os
import json

load_dotenv(dotenv_path="../../infra/.env")

API_KEY = os.getenv("GEMINI_API_KEY")
client  = genai.Client(api_key=API_KEY)

PROMPTS = {

    # ── PROMPT 1: Fridge Inventory ──────────────────────────────────────────
    "fridge_inventory": """
        You are a kitchen inventory assistant.
        Look at this fridge image and identify every visible item.
        Respond ONLY with a valid JSON array. No explanation, no markdown fences.
        Each element must have exactly these fields:
          "name"  : specific item name (e.g. "milk", "cheddar cheese")
          "type"  : category — one of: dairy, vegetable, fruit, beverage, meat, condiment, leftovers, other
          "count" : integer (estimate 1 if unclear)
        Example: [{"name": "milk", "type": "dairy", "count": 1}]
        Only include items you can clearly see.
    """,

    # ── PROMPT 2: Shopping Recommendations ─────────────────────────────────
    "shopping_recommendation": """
        You are a smart kitchen assistant helping a user restock their fridge.
        Based on the fridge image provided, identify what is LOW, MISSING, or RUNNING OUT.

        Consider common household essentials: eggs, milk, vegetables, fruits, protein (meat/tofu),
        condiments, beverages, and leftovers.

        Respond ONLY with a valid JSON object. No explanation, no markdown fences.
        Use exactly this structure:
        {
          "low_stock": [
            {"name": "item name", "reason": "only 1 left / nearly empty / etc."}
          ],
          "recommended_to_buy": [
            {"name": "item name", "priority": "high/medium/low", "reason": "why to buy"}
          ],
          "tip": "one short practical kitchen tip based on what you see"
        }

        Be practical and helpful. Only recommend realistic grocery items.
    """,

    # ── PROMPT 3: Meal Suggestions ──────────────────────────────────────────
    "meal_suggestion": """
        You are a creative home chef assistant.
        Look at the fridge image and suggest meals that can be made using the visible ingredients.

        Respond ONLY with a valid JSON object. No explanation, no markdown fences.
        Use exactly this structure:
        {
          "available_ingredients": ["ingredient1", "ingredient2"],
          "meals": [
            {
              "name": "Meal name",
              "difficulty": "easy/medium/hard",
              "time_minutes": 20,
              "ingredients_used": ["ingredient1", "ingredient2"],
              "missing_ingredients": ["anything extra needed"],
              "description": "One sentence about the dish"
            }
          ],
          "fun_fact": "A short fun food fact related to the ingredients"
        }

        Suggest 3 meals ranging from simple to creative. Prioritize meals that use
        ingredients that are close to expiring (e.g. leftovers, open packages).
    """,
}


def analyze_image(jpg_bytes: bytes, mode: str = "general") -> str:
    image  = Image.open(BytesIO(jpg_bytes))
    prompt = PROMPTS.get(mode, PROMPTS["fridge_inventory"])

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt]
    )
    return response.text


def suggest_dish(jpg_bytes: bytes, dish: str) -> str:
    """Check fridge image for what's available/missing to make a specific dish."""
    image  = Image.open(BytesIO(jpg_bytes))
    prompt = f"""
        The user wants to make: {dish}

        Look at this fridge image and respond ONLY with a valid JSON object.
        No explanation, no markdown fences.
        {{
            "dish": "{dish}",
            "available_for_dish": ["ingredient1", "ingredient2"],
            "missing": [
                {{"name": "ingredient name", "substitute": "possible substitute or null"}}
            ],
            "can_make": true,
            "tip": "one short cooking tip"
        }}
        Be realistic — only list ingredients clearly visible in the fridge.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt]
    )
    return response.text


def analyze_fridge(jpg_bytes: bytes) -> dict:
    """
    Run all 3 fridge-specific prompts and return structured results.
    Returns dict with keys: inventory, recommendations, meals
    """
    results = {}

    for key in ["fridge_inventory", "shopping_recommendation", "meal_suggestion"]:
        raw = analyze_image(jpg_bytes, mode=key)
        try:
            results[key] = json.loads(raw)
        except json.JSONDecodeError:
            results[key] = {"raw": raw, "error": "Failed to parse JSON"}

    return results