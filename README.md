# YP Team Manager Bot

ربات مدیریت گروه کاری YP برای Ye Pesare.

## امکانات
- ثبت ۴ نقش: Artist / Manager / Producer / Designer
- مدیریت Task
- درصد پیشرفت پروژه
- Release Checklist
- Reminder
- تغییر نام پروژه
- پنل دکمه‌ای ساده

## راه‌اندازی روی Railway

1. این فایل‌ها را در GitHub قرار بده یا ZIP را استخراج کن.
2. در Railway یک New Project بساز و Deploy from GitHub Repo را بزن.
3. در Variables این متغیر را اضافه کن:
   BOT_TOKEN=توکن ربات
4. Start Command:
   python bot.py

Railway معمولاً Procfile را هم می‌خواند.

## راه‌اندازی در تلگرام

ربات را به گروه اضافه کن و برای هر عضو:
- Artist: /joinrole artist
- Manager: /joinrole manager
- Producer: /joinrole producer
- Designer: /joinrole designer

مثال ساخت وظیفه:
 /addtask نوشتن Hook | artist
 /addtask ساخت Beat | producer
 /addtask طراحی Cover | designer

انجام وظیفه:
 /done 1

یادآوری:
 /remind 30m تکست را کامل کن
 /remind 2h جلسه تیم YP

وضعیت:
 /status

چک‌لیست:
 /release
