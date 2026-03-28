import asyncio
import json
import os
from datetime import datetime, time as dtime
import pytz
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

# Chat IDs that receive the weekly Saturday report
_subscribers: set[int] = set()


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


# ── Scheduled job ────────────────────────────────────────────────────────────

async def saturday_report_job(ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = ctx.job.chat_id
    print(f"[job] Saturday report → chat {chat_id}")
    result = await trigger_and_wait("fridge_inventory")
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=f"📅 Saturday Fridge Report!\n\n{result}",
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧊 Smart Fridge Bot\n\n"
        "Commands:\n"
        "  /image           — capture & send fridge photo\n"
        "  /list            — capture & list fridge items\n"
        "  /suggest pizza   — what's missing to make a dish\n"
        "  /subscribe 14:35 — weekly Saturday report at your chosen time\n"
        "  /unsubscribe     — stop weekly reports\n"
        "  /report          — run fridge report now\n\n"
        "Or type: suggest i want to make pasta"
    )


async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    print(f"[cmd] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - /subscribe from chat {update.effective_chat.id} with args: {ctx.args}")
    if not ctx.args:
        await update.message.reply_text("Usage: /subscribe HH:MM\nExample: /subscribe 14:35")
        return
    try:
        hour, minute = map(int, ctx.args[0].split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        await update.message.reply_text("Invalid time. Use HH:MM, e.g. /subscribe 14:35")
        return

    tz = pytz.timezone("Asia/Bangkok")
    chat_id = update.effective_chat.id

    # Remove any existing jobs for this user
    for job in ctx.job_queue.get_jobs_by_name(f"sat_{chat_id}"):
        job.schedule_removal()
    for job in ctx.job_queue.get_jobs_by_name(f"sat_once_{chat_id}"):
        job.schedule_removal()

    ctx.job_queue.run_daily(
        saturday_report_job,
        time=dtime(hour, minute, 0, tzinfo=tz),
        days=(5,),
        chat_id=chat_id,
        name=f"sat_{chat_id}",
    )

    # If today is Saturday and the time hasn't passed yet, also fire today
    now = datetime.now(tz)
    if now.weekday() == 5:
        scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled_today > now:
            ctx.job_queue.run_once(
                saturday_report_job,
                when=scheduled_today,
                chat_id=chat_id,
                name=f"sat_once_{chat_id}",
            )

    _subscribers.add(chat_id)
    await update.message.reply_text(
        f"✅ Subscribed! Fridge report every Saturday at {hour:02d}:{minute:02d} (Thailand time)."
    )


async def cmd_unsubscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _subscribers.discard(chat_id)
    for job in ctx.job_queue.get_jobs_by_name(f"sat_{chat_id}"):
        job.schedule_removal()
    for job in ctx.job_queue.get_jobs_by_name(f"sat_once_{chat_id}"):
        job.schedule_removal()
    await update.message.reply_text("🔕 Unsubscribed from weekly reports.")

async def cmd_jobs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    jobs = ctx.job_queue.jobs()
    if not jobs:
        await update.message.reply_text("No jobs scheduled.")
        return
    lines = [f"• {j.name} — next run: {j.next_t}" for j in jobs]
    await update.message.reply_text("\n".join(lines))

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

    # commands
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("image",       cmd_image))
    app.add_handler(CommandHandler("list",        cmd_list))
    app.add_handler(CommandHandler("suggest",     cmd_suggest))
    app.add_handler(CommandHandler("subscribe",   cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    app.add_handler(CommandHandler("jobs", cmd_jobs))

    print("[bot] Starting polling... (use /subscribe HH:MM to schedule Saturday reports)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
