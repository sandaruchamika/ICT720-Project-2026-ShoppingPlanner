import asyncio
import json
import os
from io import BytesIO

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)

load_dotenv()

TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
FLASK_URL = os.getenv("FLASK_URL", "http://server:5000")


# ── Formatters ────────────────────────────────────────────────────────────────

def format_result(result: str, mode: str) -> str:
    try:
        data = json.loads(result)
        if mode == "fridge_inventory" and isinstance(data, list):
            lines = ["🧊 Fridge Inventory:"]
            for item in data:
                lines.append(f"• {item['count']}x {item['name']} ({item['type']})")
            return "\n".join(lines)
        if mode == "meal_suggestion" and isinstance(data, dict):
            lines = ["🍳 Meal Ideas:"]
            for m in data.get("meals", []):
                lines.append(f"\n🍽 {m['name']} ({m['difficulty']}, {m['time_minutes']} min)")
                lines.append(f"   {m['description']}")
            return "\n".join(lines)
        if mode == "shopping_recommendation" and isinstance(data, dict):
            lines = ["🛒 Shopping List:"]
            for item in data.get("recommended_to_buy", []):
                lines.append(f"• {item['name']} — {item['reason']}")
            if tip := data.get("tip"):
                lines.append(f"\n💡 {tip}")
            return "\n".join(lines)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return result


def format_suggest(result: str, dish: str) -> str:
    try:
        d        = json.loads(result)
        can_make = d.get("can_make", False)
        lines    = [f"{'✅' if can_make else '❌'} {dish.title()}"]
        avail    = d.get("available_for_dish", [])
        if avail:
            lines.append(f"\n✅ Have: {', '.join(avail)}")
        missing = d.get("missing", [])
        if missing:
            lines.append("\n🛒 Need to buy:")
            for item in missing:
                sub  = item.get("substitute")
                line = f"  • {item['name']}"
                if sub:
                    line += f" (or: {sub})"
                lines.append(line)
        tip = d.get("tip")
        if tip:
            lines.append(f"\n💡 {tip}")
        return "\n".join(lines)
    except (json.JSONDecodeError, KeyError, TypeError):
        return result


# ── Flask helpers ─────────────────────────────────────────────────────────────

async def trigger_and_wait_image() -> bytes | None:
    """Trigger capture and return raw JPEG bytes as soon as image is uploaded."""
    async with httpx.AsyncClient(timeout=10) as client:
        r    = await client.get(f"{FLASK_URL}/latest_ts")
        prev = r.json().get("ts")
        await client.post(f"{FLASK_URL}/trigger", json={"mode": "fridge_inventory"})
        for _ in range(30):
            await asyncio.sleep(1)
            r = await client.get(f"{FLASK_URL}/latest_ts")
            if r.json().get("ts") != prev:
                img = await client.get(f"{FLASK_URL}/latest_image")
                return img.content
    return None


async def trigger_and_wait(mode: str = "fridge_inventory", dish: str = None) -> str:
    """Trigger capture and wait for LLM analysis to complete."""
    body = {"mode": mode}
    if dish:
        body["dish"] = dish
    async with httpx.AsyncClient(timeout=10) as client:
        r    = await client.get(f"{FLASK_URL}/latest_ts")
        prev = r.json().get("ts")
        await client.post(f"{FLASK_URL}/trigger", json=body)
        for _ in range(60):
            await asyncio.sleep(1)
            r = await client.get(f"{FLASK_URL}/latest_analysis")
            j = r.json()
            if j.get("ts") != prev and j.get("analysis") is not None:
                if dish:
                    return format_suggest(j["analysis"], dish)
                return format_result(j["analysis"], mode)
    return "⚠️ Timeout — no image received from the camera."


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧊 Smart Fridge Bot\n\n"
        "Commands:\n"
        "  /image   — capture & send fridge photo\n"
        "  /list    — capture & list fridge items\n"
        "  /suggest pizza — what's missing to make a dish\n\n"
        "Or type: suggest i want to make pasta"
    )


async def cmd_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Capturing...")
    img = await trigger_and_wait_image()
    if img:
        await update.message.reply_photo(photo=BytesIO(img))
    else:
        await update.message.reply_text("⚠️ Timeout — no image received.")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Scanning fridge...")
    result = await trigger_and_wait("fridge_inventory")
    await update.message.reply_text(result)


async def cmd_suggest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dish = " ".join(ctx.args) if ctx.args else None
    if not dish:
        await update.message.reply_text("What do you want to make?\nExample: /suggest pizza")
        return
    await update.message.reply_text(f"🔍 Checking fridge for {dish}...")
    result = await trigger_and_wait("suggest_dish", dish=dish)
    await update.message.reply_text(result)


async def msg_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text  = update.message.text.strip()
    lower = text.lower()

    if lower.startswith("suggest"):
        dish = lower.replace("suggest", "", 1).strip()
        for prefix in ["i want to make ", "i want to cook ", "i'd like to make "]:
            if dish.startswith(prefix):
                dish = dish[len(prefix):]
                break
        dish = dish.strip()
        if not dish:
            await update.message.reply_text("What do you want to make?\nExample: suggest pizza")
            return
        await update.message.reply_text(f"🔍 Checking fridge for {dish}...")
        result = await trigger_and_wait("suggest_dish", dish=dish)
        await update.message.reply_text(result)
    else:
        await cmd_image(update, ctx)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("image",   cmd_image))
    app.add_handler(CommandHandler("list",    cmd_list))
    app.add_handler(CommandHandler("suggest", cmd_suggest))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    print("[bot] Starting polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
