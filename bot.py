import os
import sqlite3
import logging
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================
# DATABASE
# =========================

DB = "data.db"

def db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS replied (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    return conn


def get_setting(key, default=""):
    conn = db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()
    conn.close()

    return row[0] if row else default


def set_setting(key, value):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (key, str(value))
    )
    conn.commit()
    conn.close()


def add_user(user_id):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users(user_id, first_seen) VALUES(?,?)",
        (user_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def already_replied(user_id):
    conn = db()
    row = conn.execute(
        "SELECT user_id FROM replied WHERE user_id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return row is not None


def mark_replied(user_id):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO replied(user_id) VALUES(?)",
        (user_id,)
    )
    conn.commit()
    conn.close()


# =========================
# HELPERS
# =========================

def is_owner(update: Update):
    return (
        update.effective_user
        and update.effective_user.id == OWNER_ID
    )


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user:
        add_user(user.id)

    text = (
        f"سلام {user.first_name} 👋\n\n"
        "به ربات خوش اومدی.\n"
        "برای دیدن امکانات /help رو بزن."
    )

    await update.message.reply_text(text)


# =========================
# HELP
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 راهنمای ربات

/start
شروع کار با ربات

/help
نمایش راهنما

/panel
باز کردن پنل مدیریت

📌 امکانات:
• منشی خودکار
• پنل مدیریتی
• مدیریت کاربران
• آمار
• Welcome
• مدیریت گروه
• Ban / Unban
• حذف پیام
"""

    await update.message.reply_text(text)


# =========================
# PANEL
# =========================

def panel_keyboard():
    secretary = get_setting("secretary", "0") == "1"

    status = "🟢 روشن" if secretary else "🔴 خاموش"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🤖 منشی: {status}",
                callback_data="toggle_secretary"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ تغییر متن منشی",
                callback_data="change_secretary"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 آمار",
                callback_data="stats"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 بستن پنل",
                callback_data="close_panel"
            )
        ],
    ])


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text(
            "⛔ این پنل فقط برای مالک ربات است."
        )
        return

    text = (
        "🎛️ **پنل مدیریت**\n\n"
        "از گزینه‌های زیر استفاده کن:"
    )

    await update.message.reply_text(
        text,
        reply_markup=panel_keyboard(),
        parse_mode="Markdown"
    )


# =========================
# PANEL CALLBACK
# =========================

async def panel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        await query.answer(
            "⛔ دسترسی ندارید.",
            show_alert=True
        )
        return

    if query.data == "toggle_secretary":
        current = get_setting("secretary", "0")

        new_value = "0" if current == "1" else "1"
        set_setting("secretary", new_value)

        status = "روشن 🟢" if new_value == "1" else "خاموش 🔴"

        await query.edit_message_text(
            f"🤖 منشی اکنون **{status}** است.",
            reply_markup=panel_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data == "change_secretary":
        context.user_data["waiting_secretary"] = True

        await query.edit_message_text(
            "✏️ متن جدید منشی را در پیام بعدی بفرست."
        )

    elif query.data == "stats":
        conn = db()
        count = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]
        conn.close()

        await query.edit_message_text(
            f"📊 آمار ربات\n\n"
            f"👤 کاربران: {count}",
            reply_markup=panel_keyboard()
        )

    elif query.data == "close_panel":
        await query.delete_message()


# =========================
# SECRETARY
# =========================

async def secretary_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user:
        return

    # تغییر متن منشی توسط Owner
    if (
        user.id == OWNER_ID
        and context.user_data.get("waiting_secretary")
    ):
        if update.message and update.message.text:
            set_setting(
                "secretary_text",
                update.message.text
            )

            context.user_data["waiting_secretary"] = False

            await update.message.reply_text(
                "✅ متن منشی با موفقیت تغییر کرد."
            )
            return

    # فقط PV
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    add_user(user.id)

    # خود Owner
    if user.id == OWNER_ID:
        return

    # منشی خاموش
    if get_setting("secretary", "0") != "1":
        return

    # قبلاً جواب داده
    if already_replied(user.id):
        return

    text = get_setting(
        "secretary_text",
        "فعلاً آفم رفیق 🖤 پیامت رسید؛ وقتی برگشتم خودم میام سراغت."
    )

    await update.message.reply_text(text)

    mark_replied(user.id)


# =========================
# GROUP WELCOME
# =========================

async def welcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        name = member.first_name

        await update.message.reply_text(
            f"خوش اومدی {name} 🖤\n"
            f"قوانین گروه رو رعایت کن و خوش بگذره."
        )


# =========================
# BAN
# =========================

async def ban(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_owner(update):
        return

    if update.effective_chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):
        await update.message.reply_text(
            "این دستور فقط داخل گروه کار می‌کند."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "روی پیام کاربر Reply کن و /ban بزن."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await context.bot.ban_chat_member(
            update.effective_chat.id,
            user.id
        )

        await update.message.reply_text(
            f"🚫 {user.first_name} بن شد."
        )

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(
            "❌ نتونستم کاربر رو بن کنم."
        )


# =========================
# UNBAN
# =========================

async def unban(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_owner(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "روی پیام کاربر Reply کن و /unban بزن."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await context.bot.unban_chat_member(
            update.effective_chat.id,
            user.id,
            only_if_banned=True
        )

        await update.message.reply_text(
            f"✅ {user.first_name} آنبن شد."
        )

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(
            "❌ عملیات انجام نشد."
        )


# =========================
# DELETE
# =========================

async def delete_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_owner(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "روی پیام Reply کن و /del بزن."
        )
        return

    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()

    except Exception as e:
        logging.error(e)


# =========================
# ERROR
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    logging.error(
        "Exception:",
        exc_info=context.error
    )


# =========================
# MAIN
# =========================

def main():
    db()

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("panel", panel)
    )

    application.add_handler(
        CommandHandler("ban", ban)
    )

    application.add_handler(
        CommandHandler("unban", unban)
    )

    application.add_handler(
        CommandHandler("del", delete_message)
    )

    application.add_handler(
        CallbackQueryHandler(panel_callback)
    )

    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            secretary_message
        )
    )

    application.add_error_handler(error_handler)

    print("🤖 YePesare Bot is running...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()