import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
DB_PATH = os.getenv("DB_PATH", "yp_team.db")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN or TELEGRAM_TOKEN environment variable is missing.")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

ROLE_NAMES = {
    "artist": "🎤 Artist",
    "manager": "🧑‍💼 Manager",
    "producer": "🎧 Producer",
    "designer": "🎨 Designer",
}

RELEASE_ITEMS = [
    "Beat نهایی", "Lyrics نهایی", "Recording نهایی", "Mix", "Master",
    "Cover", "Teaser / Content", "Metadata", "Distributor", "Spotify",
    "SoundCloud", "YouTube", "TikTok", "Release Day Plan",
]

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def db(sql, params=(), fetch=False):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur.fetchall() if fetch else []


def init_db():
    db("""CREATE TABLE IF NOT EXISTS members(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT NOT NULL,
        role TEXT NOT NULL
    )""")
    db("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        role TEXT,
        assignee_id INTEGER,
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    db("""CREATE TABLE IF NOT EXISTS reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        due_at TEXT NOT NULL,
        sent INTEGER DEFAULT 0
    )""")
    db("""CREATE TABLE IF NOT EXISTS settings(
        chat_id INTEGER PRIMARY KEY,
        project TEXT DEFAULT 'YE PESARE — FIRST RELEASE'
    )""")


async def ensure_admin(update: Update):
    if not update.effective_chat:
        return False
    if update.effective_chat.type == "private":
        return True
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ("administrator", "creator")


def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 وظایف", callback_data="tasks"),
            InlineKeyboardButton("📊 وضعیت", callback_data="status"),
        ],
        [
            InlineKeyboardButton("🎵 چک‌لیست ریلیز", callback_data="release"),
            InlineKeyboardButton("👥 اعضا", callback_data="members"),
        ],
    ])


def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="menu")]
    ])


async def send_html(target, text, reply_markup=None):
    await target.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>🤖 YP Team Manager Bot</b>\n\n"
        "ربات مدیریت تیم YP برای Ye Pesare آماده است.\n\n"
        "<b>دستورهای اصلی:</b>\n"
        "/addmember @user role — راهنمای اضافه کردن عضو\n"
        "/joinrole role — ثبت نقش خودت\n"
        "/members — اعضای تیم\n"
        "/addtask عنوان | role — ساخت وظیفه\n"
        "/tasks — نمایش وظایف باز\n"
        "/done ID — انجام‌شده کردن وظیفه\n"
        "/status — وضعیت پروژه\n"
        "/release — چک‌لیست ریلیز\n"
        "/remind 30m متن — یادآوری\n"
        "/remind 2h متن — یادآوری\n"
        "/remind 1d متن — یادآوری\n"
        "/project نام پروژه — تغییر نام پروژه\n"
        "/help — راهنما"
    )
    if update.message:
        await send_html(update.message, text, menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def addmember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_admin(update):
        await update.message.reply_text("⛔ فقط ادمین گروه می‌تواند عضو اضافه کند.")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "فرمت:\n/addmember @username role\n\n"
            "role ها: artist / manager / producer / designer"
        )
        return
    username = context.args[0].lstrip("@")
    role = context.args[1].lower()
    if role not in ROLE_NAMES:
        await update.message.reply_text("❌ نقش نامعتبر است.")
        return
    await update.message.reply_text(
        f"برای @{username}:\n"
        f"داخل همین گروه بنویسد:\n"
        f"/joinrole {role}\n\n"
        "این کار User ID واقعی او را ثبت می‌کند."
    )


async def joinrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ROLE_NAMES:
        await update.message.reply_text(
            "فرمت: /joinrole artist\n"
            "نقش‌ها: artist / manager / producer / designer"
        )
        return
    role = context.args[0].lower()
    user = update.effective_user
    db(
        """INSERT INTO members(user_id, username, name, role)
           VALUES(?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
           username=excluded.username, name=excluded.name, role=excluded.role""",
        (user.id, user.username or "", user.full_name, role),
    )
    await update.message.reply_text(
        f"✅ {user.full_name} به عنوان {ROLE_NAMES[role]} ثبت شد."
    )


async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db("SELECT * FROM members ORDER BY role, name", fetch=True)
    if not rows:
        await update.message.reply_text("هنوز عضوی ثبت نشده.")
        return
    lines = ["<b>👥 اعضای YP</b>", ""]
    for row in rows:
        tag = f"@{escape(row['username'])}" if row["username"] else escape(row["name"])
        lines.append(f"{ROLE_NAMES.get(row['role'], escape(row['role']))} — {tag}")
    await send_html(update.message, "\n".join(lines), back_menu())


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "فرمت:\n/addtask عنوان وظیفه | role\n\n"
            "مثال:\n/addtask نوشتن Hook | artist\n"
            "/addtask انتخاب کاور | designer"
        )
        return
    title, role = [x.strip() for x in raw.split("|", 1)]
    role = role.lower()
    if not title:
        await update.message.reply_text("❌ عنوان وظیفه خالی است.")
        return
    if role not in ROLE_NAMES and role not in ("all", "همه"):
        await update.message.reply_text("❌ نقش نامعتبر است.")
        return
    db(
        "INSERT INTO tasks(title, role, created_at) VALUES(?,?,?)",
        (title, role, datetime.now(timezone.utc).isoformat()),
    )
    await update.message.reply_text(
        f"✅ وظیفه ساخته شد:\n{title}\n{ROLE_NAMES.get(role, '👥 همه')}"
    )


def tasks_text():
    rows = db("SELECT * FROM tasks WHERE done=0 ORDER BY id", fetch=True)
    if not rows:
        return "<b>📋 وظایف باز YP</b>\n\n🎉 همه وظایف انجام شده‌اند!"
    lines = ["<b>📋 وظایف باز YP</b>", ""]
    for row in rows:
        lines.append(
            f"▫️ <code>#{row['id']}</code> {escape(row['title'])} — "
            f"{ROLE_NAMES.get(row['role'], '👥 همه')}"
        )
    return "\n".join(lines)


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or (update.callback_query.message if update.callback_query else None)
    if target:
        await send_html(target, tasks_text(), back_menu())


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("فرمت: /done 12")
        return
    task_id = int(context.args[0])
    rows = db("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True)
    if not rows:
        await update.message.reply_text("❌ چنین وظیفه‌ای وجود ندارد.")
        return
    if rows[0]["done"]:
        await update.message.reply_text("ℹ️ این وظیفه قبلاً انجام شده است.")
        return
    db("UPDATE tasks SET done=1, assignee_id=? WHERE id=?", (update.effective_user.id, task_id))
    await update.message.reply_text(f"✅ وظیفه #{task_id} انجام شد.")


def get_project(chat_id):
    rows = db("SELECT project FROM settings WHERE chat_id=?", (chat_id,), fetch=True)
    return rows[0]["project"] if rows else "YE PESARE — FIRST RELEASE"


def get_stage(pct):
    if pct < 25:
        return "آماده‌سازی"
    if pct < 60:
        return "تولید"
    if pct < 85:
        return "پس‌تولید"
    return "آماده انتشار"


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or (update.callback_query.message if update.callback_query else None)
    total = db("SELECT COUNT(*) AS c FROM tasks", fetch=True)[0]["c"]
    done_n = db("SELECT COUNT(*) AS c FROM tasks WHERE done=1", fetch=True)[0]["c"]
    pct = round(done_n / total * 100) if total else 0
    project_name = escape(get_project(update.effective_chat.id))
    stage = get_stage(pct)
    text = (
        f"<b>📊 {project_name}</b>\n\n"
        f"پیشرفت وظایف: <code>{pct}%</code>\n"
        f"انجام‌شده: <code>{done_n}</code>\n"
        f"باقی‌مانده: <code>{total - done_n}</code>\n\n"
        f"مرحله فعلی: <b>{stage}</b>"
    )
    if target:
        await send_html(target, text, back_menu())


async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or (update.callback_query.message if update.callback_query else None)
    done_titles = {
        row["title"].lower()
        for row in db("SELECT title FROM tasks WHERE done=1", fetch=True)
    }
    lines = ["<b>🎵 YP — RELEASE CHECKLIST</b>", ""]
    checked = 0
    for index, item in enumerate(RELEASE_ITEMS, 1):
        ok = any(item.lower() in title for title in done_titles)
        checked += int(ok)
        lines.append(f"{'✅' if ok else '⬜'} {index}. {escape(item)}")
    pct = round(checked / len(RELEASE_ITEMS) * 100)
    lines.extend(["", f"Progress: <code>{pct}%</code>"])
    if target:
        await send_html(target, "\n".join(lines), back_menu())


def parse_duration(value):
    value = value.strip().lower()
    units = {"min": 60, "m": 60, "h": 3600, "d": 86400}
    for unit, multiplier in units.items():
        if value.endswith(unit):
            try:
                amount = float(value[:-len(unit)])
            except ValueError:
                return None
            return int(amount * multiplier) if amount > 0 else None
    return None


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "فرمت:\n/remind 30m متن یادآوری\n"
            "/remind 2h متن یادآوری\n/remind 1d متن یادآوری"
        )
        return
    seconds = parse_duration(context.args[0])
    if seconds is None:
        await update.message.reply_text("❌ زمان را مثل 30m یا 2h یا 1d وارد کن.")
        return
    reminder_text = " ".join(context.args[1:]).strip()
    if not reminder_text:
        await update.message.reply_text("❌ متن یادآوری خالی است.")
        return
    due = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    db(
        "INSERT INTO reminders(chat_id,user_id,text,due_at) VALUES(?,?,?,?)",
        (update.effective_chat.id, update.effective_user.id, reminder_text, due.isoformat()),
    )
    if seconds < 3600:
        amount_text = f"{seconds // 60} دقیقه"
    elif seconds < 86400:
        amount_text = f"{seconds / 3600:g} ساعت"
    else:
        amount_text = f"{seconds / 86400:g} روز"
    await update.message.reply_text(f"⏰ یادآوری ثبت شد.\n{amount_text} دیگر.")


async def reminder_worker(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    rows = db("SELECT * FROM reminders WHERE sent=0", fetch=True)
    for row in rows:
        try:
            due = datetime.fromisoformat(row["due_at"])
            if due <= now:
                await context.bot.send_message(
                    row["chat_id"],
                    f"<b>⏰ YP Reminder</b>\n\n"
                    f"{escape(row['text'])}\n"
                    f"👤 برای: <code>{row['user_id']}</code>",
                    parse_mode="HTML",
                )
                db("UPDATE reminders SET sent=1 WHERE id=?", (row["id"],))
        except Exception:
            logging.exception("Reminder error")


async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_admin(update):
        await update.message.reply_text("⛔ فقط ادمین گروه می‌تواند پروژه را تغییر دهد.")
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("فرمت: /project YP Track 001")
        return
    db(
        """INSERT INTO settings(chat_id, project) VALUES(?,?)
           ON CONFLICT(chat_id) DO UPDATE SET project=excluded.project""",
        (update.effective_chat.id, name),
    )
    await update.message.reply_text(f"✅ پروژه تغییر کرد به:\n{name}")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu":
        await query.message.reply_text(
            "🤖 <b>YP Team Manager Bot</b>\n\nیک گزینه را انتخاب کن:",
            parse_mode="HTML",
            reply_markup=menu(),
        )
    elif query.data == "tasks":
        await send_html(query.message, tasks_text(), back_menu())
    elif query.data == "status":
        await status(update, context)
    elif query.data == "release":
        await release(update, context)
    elif query.data == "members":
        rows = db("SELECT * FROM members ORDER BY role, name", fetch=True)
        if not rows:
            text = "<b>👥 اعضای YP</b>\n\nهنوز عضوی ثبت نشده."
        else:
            lines = ["<b>👥 اعضای YP</b>", ""]
            for row in rows:
                tag = f"@{escape(row['username'])}" if row["username"] else escape(row["name"])
                lines.append(f"{ROLE_NAMES.get(row['role'], escape(row['role']))} — {tag}")
            text = "\n".join(lines)
        await send_html(query.message, text, back_menu())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.exception("Unhandled error", exc_info=context.error)


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addmember", addmember))
    app.add_handler(CommandHandler("joinrole", joinrole))
    app.add_handler(CommandHandler("members", members))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("release", release))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("project", project))
    app.add_handler(CallbackQueryHandler(button))

    app.job_queue.run_repeating(reminder_worker, interval=30, first=10)
    app.add_error_handler(error_handler)

    logging.info("🤖 YP Team Manager Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
