import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
DB_PATH = os.getenv("DB_PATH", "yp_team.db")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN or TELEGRAM_TOKEN environment variable is missing.")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

ROLE_NAMES = {
    "artist": "🎤 Artist",
    "manager": "🧑‍💼 Manager",
    "producer": "🎧 Producer",
    "designer": "🎨 Designer",
}

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

def db(sql, params=(), fetch=False):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    if fetch:
        return cur.fetchall()
    return []

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

def is_admin(update: Update):
    return update.effective_user and (
        update.effective_user.id == update.effective_chat.owner_id
        if getattr(update.effective_chat, "owner_id", None) else False
    )

async def ensure_admin(update):
    if update.effective_chat.type == "private":
        return True
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ("administrator", "creator")

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 وظایف", callback_data="tasks"),
         InlineKeyboardButton("📊 وضعیت", callback_data="status")],
        [InlineKeyboardButton("🎵 چک‌لیست ریلیز", callback_data="release"),
         InlineKeyboardButton("👥 اعضا", callback_data="members")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *YP Team Manager Bot*\n\n"
        "ربات مدیریت تیم YP برای Ye Pesare آماده است.\n\n"
        "دستورهای اصلی:\n"
        "/addmember @user role — اضافه کردن عضو\n"
        "/members — اعضای تیم\n"
        "/addtask عنوان | role — ساخت وظیفه\n"
        "/tasks — نمایش وظایف\n"
        "/done ID — انجام‌شده کردن وظیفه\n"
        "/status — وضعیت پروژه\n"
        "/release — چک‌لیست ریلیز\n"
        "/remind 30m متن — یادآوری\n"
        "/remind 2h متن — یادآوری\n"
        "/project نام پروژه — تغییر نام پروژه\n"
        "/help — راهنما",
        parse_mode="Markdown",
        reply_markup=menu()
    )

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
    # Telegram Bot API cannot reliably resolve a username to a user_id.
    # The target member should use /joinrole role themselves.
    await update.message.reply_text(
        f"برای @{username}:\n"
        f"به او بگو داخل همین گروه بنویسد:\n"
        f"`/joinrole {role}`\n\n"
        "این کار باعث می‌شود ربات User ID واقعی او را ثبت کند.",
        parse_mode="Markdown"
    )

async def joinrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ROLE_NAMES:
        await update.message.reply_text(
            "فرمت: /joinrole artist\n"
            "نقش‌ها: artist / manager / producer / designer"
        )
        return
    role = context.args[0].lower()
    u = update.effective_user
    db("""INSERT INTO members(user_id, username, name, role)
          VALUES(?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET
          username=excluded.username, name=excluded.name, role=excluded.role""",
       (u.id, u.username or "", u.full_name, role))
    await update.message.reply_text(
        f"✅ {u.full_name} به عنوان {ROLE_NAMES[role]} ثبت شد."
    )

async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db("SELECT * FROM members ORDER BY role, name", fetch=True)
    if not rows:
        await update.message.reply_text("هنوز عضوی ثبت نشده.")
        return
    text = "👥 *اعضای YP*\n\n"
    for r in rows:
        tag = f"@{r['username']}" if r["username"] else r["name"]
        text += f"{ROLE_NAMES.get(r['role'], r['role'])} — {tag}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "فرمت:\n/addtask عنوان وظیفه | role\n\n"
            "مثال:\n/addtask نوشتن Hook | artist\n"
            "یا:\n/addtask انتخاب کاور | designer"
        )
        return
    title, role = [x.strip() for x in raw.split("|", 1)]
    role = role.lower()
    if role not in ROLE_NAMES and role not in ("all", "همه"):
        await update.message.reply_text("❌ نقش نامعتبر است.")
        return
    db("INSERT INTO tasks(title, role, created_at) VALUES(?,?,?)",
       (title, role, datetime.now(timezone.utc).isoformat()))
    await update.message.reply_text(f"✅ وظیفه ساخته شد:\n{title}\n{ROLE_NAMES.get(role, '👥 همه')}")

def tasks_text():
    rows = db("SELECT * FROM tasks WHERE done=0 ORDER BY id", fetch=True)
    if not rows:
        return "📋 *وظایف*\n\n🎉 همه وظایف انجام شده‌اند!"
    text = "📋 *وظایف باز YP*\n\n"
    for r in rows:
        text += f"▫️ `#{r['id']}` {r['title']} — {ROLE_NAMES.get(r['role'], '👥 همه')}\n"
    return text

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tasks_text(), parse_mode="Markdown")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("فرمت: /done 12")
        return
    task_id = int(context.args[0])
    rows = db("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True)
    if not rows:
        await update.message.reply_text("❌ چنین وظیفه‌ای وجود ندارد.")
        return
    db("UPDATE tasks SET done=1, assignee_id=? WHERE id=?", (update.effective_user.id, task_id))
    await update.message.reply_text(f"✅ وظیفه #{task_id} انجام شد.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reply_target = update.message or (update.callback_query.message if update.callback_query else None)
    s = db("SELECT project FROM settings WHERE chat_id=?", (chat_id,), fetch=True)
    project = s[0]["project"] if s else "YE PESARE — FIRST RELEASE"
    total = db("SELECT COUNT(*) c FROM tasks", fetch=True)[0]["c"]
    done_n = db("SELECT COUNT(*) c FROM tasks WHERE done=1", fetch=True)[0]["c"]
    pct = round(done_n / total * 100) if total else 0
    await reply_target.reply_text(
        f"📊 *{project}*\n\n"
        f"پیشرفت وظایف: `{pct}%`\n"
        f"انجام‌شده: `{done_n}`\n"
        f"باقی‌مانده: `{total-done_n}`\n\n"
        f"مرحله فعلی: {("آماده‌سازی" if pct < 25 else "تولید" if pct < 60 else "پس‌تولید" if pct < 85 else "آماده انتشار")}",
        parse_mode="Markdown"
    )

RELEASE_ITEMS = [
    "Beat نهایی",
    "Lyrics نهایی",
    "Recording نهایی",
    "Mix",
    "Master",
    "Cover",
    "Teaser / Content",
    "Metadata",
    "Distributor",
    "Spotify",
    "SoundCloud",
    "YouTube",
    "TikTok",
    "Release Day Plan",
]

async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_target = update.message or (update.callback_query.message if update.callback_query else None)
    done_titles = {r["title"].lower() for r in db("SELECT title FROM tasks WHERE done=1", fetch=True)}
    lines = []
    checked = 0
    for i, item in enumerate(RELEASE_ITEMS, 1):
        ok = any(item.lower() in x for x in done_titles)
        checked += int(ok)
        lines.append(f"{'✅' if ok else '⬜'} {i}. {item}")
    pct = round(checked / len(RELEASE_ITEMS) * 100)
    await reply_target.reply_text(
        "🎵 *YP — RELEASE CHECKLIST*\n\n" +
        "\n".join(lines) +
        f"\n\nProgress: `{pct}%`",
        parse_mode="Markdown"
    )

def parse_duration(s):
    s = s.strip().lower()
    units = {"m": 60, "min": 60, "h": 3600, "d": 86400}
    for u, mult in units.items():
        if s.endswith(u):
            return int(float(s[:-len(u)]) * mult)
    return None

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("فرمت: /remind 30m متن یادآوری")
        return
    seconds = parse_duration(context.args[0])
    if seconds is None:
        await update.message.reply_text("زمان را مثل 30m یا 2h یا 1d وارد کن.")
        return
    text = " ".join(context.args[1:])
    due = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    db("INSERT INTO reminders(chat_id,user_id,text,due_at) VALUES(?,?,?,?)",
       (update.effective_chat.id, update.effective_user.id, text, due.isoformat()))
    await update.message.reply_text(
        f"⏰ یادآوری ثبت شد.\n{seconds//60 if seconds < 3600 else seconds/3600:g} "
        f"{'دقیقه' if seconds < 3600 else 'ساعت'} دیگر."
    )

async def reminder_worker(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    rows = db("SELECT * FROM reminders WHERE sent=0", fetch=True)
    for r in rows:
        try:
            due = datetime.fromisoformat(r["due_at"])
            if due <= now:
                await context.bot.send_message(
                    r["chat_id"],
                    f"⏰ *YP Reminder*\n\n{r['text']}\n👤 برای: `{r['user_id']}`",
                    parse_mode="Markdown"
                )
                db("UPDATE reminders SET sent=1 WHERE id=?", (r["id"],))
        except Exception:
            logging.exception("Reminder error")

async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_admin(update):
        await update.message.reply_text("⛔ فقط ادمین گروه.")
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("فرمت: /project YP Track 001")
        return
    db("""INSERT INTO settings(chat_id, project) VALUES(?,?)
          ON CONFLICT(chat_id) DO UPDATE SET project=excluded.project""",
       (update.effective_chat.id, name))
    await update.message.reply_text(f"✅ پروژه تغییر کرد به:\n{name}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "tasks":
        await q.message.reply_text(tasks_text(), parse_mode="Markdown")
    elif q.data == "status":
        await status(update, context)
    elif q.data == "release":
        await release(update, context)
    elif q.data == "members":
        rows = db("SELECT * FROM members ORDER BY role, name", fetch=True)
        text = "👥 *اعضای YP*\n\n" + (
            "\n".join(
                f"{ROLE_NAMES.get(r['role'], r['role'])} — "
                f"{('@'+r['username']) if r['username'] else r['name']}"
                for r in rows
            ) if rows else "هنوز عضوی ثبت نشده."
        )
        await q.message.reply_text(text, parse_mode="Markdown")

async def error_handler(update, context):
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
