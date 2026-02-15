import asyncio
import re
import aiosqlite

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.error import BadRequest

# =========================
# 1) SOZLAMALAR
# =========================
TOKEN = "8402389380:AAGsMRmgplvSrr7O4fyCazPrPySDLCwx5pU"
ADMIN_IDS = {6027270363,8362605543,8031453208}
DB_PATH = "codes.db"

REQUIRED_CHANNELS = [
    "@kinolar_muslim_asosiy"
]

CONFIRM_CB = "confirm_sub"

# admin /add qilgandan keyin forward kutish
pending_code = {}  # admin_id -> code


# =========================
# 2) DATABASE
# =========================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL
        )
        """)
        await db.commit()

async def save_code(code: str, file_id: str, file_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO codes(code, file_id, file_type) VALUES(?,?,?)",
            (code, file_id, file_type)
        )
        await db.commit()

async def get_code(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT file_id, file_type FROM codes WHERE code = ?",
            (code,)
        )
        return await cur.fetchone()


# =========================
# 3) FORCE SUB
# =========================
def sub_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for ch in REQUIRED_CHANNELS:
        rows.append([
            InlineKeyboardButton(
                text=f"🔔 {ch} ga obuna bo‘lish",
                url=f"https://t.me/{ch.lstrip('@')}"
            )
        ])
    rows.append([InlineKeyboardButton("✅ Tasdiqlash", callback_data=CONFIRM_CB)])
    return InlineKeyboardMarkup(rows)

async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ("left", "kicked"):
                return False
        except BadRequest:
            return False
    return True


# =========================
# 4) FILE ID AJRATISH
# =========================
def extract_file_from_message(msg):
    if msg.video:
        return msg.video.file_id, "video"
    if msg.document:
        return msg.document.file_id, "document"
    if msg.audio:
        return msg.audio.file_id, "audio"
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    return None, None


# =========================
# 5) HANDLERLAR
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_subscribed(update, context, user_id):
        await update.message.reply_text(
            "Botdan foydalanish uchun quyidagi kanallarga a’zo bo‘ling, so‘ng ✅ Tasdiqlash bosing:",
            reply_markup=sub_keyboard()
        )
        return
    await update.message.reply_text("Assalomu alaykum! Kodni yuboring.")

async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not await is_subscribed(update, context, user_id):
        await query.answer("❌ Hali hamma kanallarga a’zo bo‘lmadingiz!", show_alert=True)
        return

    await query.message.edit_text("Kodni yuboring.")

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Siz admin emassiz.")

    if not context.args:
        return await update.message.reply_text("❗ Foydalanish: /add 1208")

    code = context.args[0].strip()
    if not re.fullmatch(r"[0-9A-Za-z_-]{1,30}", code):
        return await update.message.reply_text("❌ Kod formati noto‘g‘ri. (1-30ta belgi: raqam/harf/_- )")

    pending_code[user_id] = code
    await update.message.reply_text(
        f"✅ Kod qabul qilindi: {code}\n"
        "Endi kanaldagi shu fayl postini menga FORWARD qiling (video/document/audio/photo)."
    )

async def forwarded_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message

    if user_id not in ADMIN_IDS:
        return

    if user_id not in pending_code:
        return await msg.reply_text("❗ Avval /add KOD yozing. Keyin postni forward qiling.")

    code = pending_code.pop(user_id)
    file_id, file_type = extract_file_from_message(msg)

    if not file_id:
        pending_code[user_id] = code  # qayta tiklab qo'yamiz
        return await msg.reply_text("❌ Men fayl topolmadim. Video/PDF/audio/photo postni forward qiling.")

    await save_code(code, file_id, file_type)
    await msg.reply_text(f"✅ Saqlandi!\nKod: {code}\nTuri: {file_type}")

async def code_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = update.effective_user.id

    text = (msg.text or "").strip()
    if not text or text.startswith("/"):
        return

    # obuna tekshirish
    if not await is_subscribed(update, context, user_id):
        await msg.reply_text(
            "❌ Avval kanallarga a’zo bo‘ling, so‘ng ✅ Tasdiqlash bosing:",
            reply_markup=sub_keyboard()
        )
        return

    row = await get_code(text)
    if not row:
        return await msg.reply_text("❌ Kod topilmadi. Qayta tekshiring.")

    file_id, file_type = row

    if file_type == "video":
        await msg.reply_video(file_id)
    elif file_type == "document":
        await msg.reply_document(file_id)
    elif file_type == "audio":
        await msg.reply_audio(file_id)
    elif file_type == "photo":
        await msg.reply_photo(file_id)
    else:
        await msg.reply_text("❌ Noma’lum fayl turi.")


# =========================
# 6) MAIN
# =========================
async def post_init(app: Application):
    await init_db()

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CallbackQueryHandler(confirm_cb, pattern=f"^{CONFIRM_CB}$"))

    # Forward qilingan xabarlar: video/doc/audio/photo bo'lsa ushlaymiz
    app.add_handler(MessageHandler(filters.FORWARDED, forwarded_handler))

    # Oddiy matn (kod qidirish)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_lookup))

    app.run_polling()

if __name__ == "__main__":
    main()
