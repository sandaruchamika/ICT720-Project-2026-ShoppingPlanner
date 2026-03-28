from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler
import requests
from io import BytesIO

TOKEN = "8585188760:AAFWv2T-R413Ms1TrSCAVHVJZXV1Q84z7Es"

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     welcome_text = (
#         "🧊 Welcome to your Smart Fridge!\n\n"
#         "Here is what you can ask me:\n"
#         "📷 Type 'image' - ดูของในตู้เย็น\n"
#         "📋 Type 'list' - ดูรายการสินค้า\n"
#         "🛒 Type 'suggest' - แนะนำของที่ควรซื้อ"
#     )

#     await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower()

    # 🔹 list → ส่งข้อความรายการสินค้า
    if user_text == "list":
        product_list = """
📦 สินค้าทั้งหมด:
1. food
2. cola
3. apple
"""
        await update.message.reply_text(product_list)

    # 🔹 image → ส่งรูปภาพ
    elif user_text == "image":
        url = "https://picsum.photos/300"

        try:
            response = requests.get(url)
            img = BytesIO(response.content)   # 🔥 แปลงเป็น file object

            await update.message.reply_photo(photo=img)

        except Exception as e:
            print("ERROR:", e)
            await update.message.reply_text("ส่งรูปไม่ได้")

    # 🔹 suggest → แนะนำสินค้า
    elif user_text == "suggest":
        suggest_text = "🔥 แนะนำ: iPhone 15 (ขายดีสุดตอนนี้!)"
        await update.message.reply_text(suggest_text)
    
    elif user_text == "start":
        welcome_text = (
            "🧊 Welcome to your Smart Fridge!\n\n"
            "Here is what you can ask me:\n"
            "📷 Type 'image' - ดูของในตู้เย็น\n"
            "📋 Type 'list' - ดูรายการสินค้า\n"
            "🛒 Type 'suggest' - แนะนำของที่ควรซื้อ"
        )

        await update.message.reply_text(welcome_text)

    # 🔹 default
    else:
        await update.message.reply_text("❌ ไม่เข้าใจคำสั่ง (ลองพิมพ์: list, image, suggest)")

# ▶️ รัน bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()