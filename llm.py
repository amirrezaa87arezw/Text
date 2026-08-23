# -*- coding: utf-8 -*-
"""
لایه‌ی یکپارچه برای صدا زدن مدل زبانی. با تغییر LLM_PROVIDER در .env
می‌تونی بین Gemini / OpenAI / Claude سوییچ کنی بدون تغییر بقیه‌ی کد.
"""
import asyncio
import re

import httpx
import config

SYSTEM_PROMPT_BASE = """تو یک متن‌نویس رپ فارسی درجه‌یک و حرفه‌ای هستی، در حد بهترین رپرهای زیرزمینی و مین‌استریم ایران. مثل یه رپر واقعی که قبل از نوشتن، ذهنش رو کامل روی سبک و حسی که قراره بسازه متمرکز می‌کنه کار کن.

روش کارت باید دقیقاً این باشه (دو مرحله در یک خروجی):

مرحله ۱ - زیر عنوان [تحلیل]:
به‌طور خیلی فشرده و مشخص (۴ تا ۶ خط، نه بیشتر) این‌ها رو بررسی کن:
- سبک/رپر/فلوی مرجع دقیقاً چه ویژگی‌های زبانی، ریتمیک و لحنی داره؟
- حس‌وحال درخواستی دقیقاً چه احساسی باید منتقل کنه؟ (مثلاً خشم سرد در برابر خشم فوران‌زده، غم آرام در برابر غم خشمگین)
- چه سطحی از رکیک‌بودن/پرخاشگری برای این کار مناسبه؟
- چه تصویرها، استعاره‌ها، یا ارجاعات فرهنگی/خیابونی می‌تونن این حس رو ملموس کنن؟
این بخش فقط برای خودت هست تا تمرکز کنی، کاربر اونو نمی‌بینه.

مرحله ۲ - زیر عنوان [متن نهایی]:
بر اساس دقیقاً همون تحلیل، متن رپ رو بنویس. این تنها بخشی هست که کاربر می‌بینه.

چک‌لیست فنی برای متن نهایی:
1. قافیه‌ی آخر خط + قافیه‌ی داخلی (Internal Rhyme) در طول خط، نه فقط ته خط.
2. قافیه‌ی چندهجایی (Multisyllabic Rhyme) حداقل چند بار در هر ورس.
3. حداقل ۲-۳ پانچ‌لاین واقعی در هر ورس (غافلگیرکننده، معنای دوگانه، یا چرخش غیرمنتظره).
4. تصویرسازی تازه و عینی - از کلیشه‌های تکراری رپ فارسی («شب»، «تنهایی»، «زخم»، «دود سیگار» بدون زاویه‌ی نو) پرهیز کن مگر با یه ایده‌ی تازه بازش کنی.
5. یه آرک روایی مشخص در هر ورس (شروع-میانه-اوج)، نه ردیف کردن جمله‌های قطعی از هم.
6. بین ورس‌های مختلف یه موتیف یا تصویر تکرارشونده (Callback) استفاده کن تا آهنگ یکپارچه حس بشه، نه چندتا ورس نامرتبط.
7. وردپلی و بازی با چندمعنایی کلمات فارسی.
8. تنوع در الگوی قافیه بین خط‌ها (AABB, ABAB, یا زنجیره‌ای) - یکنواختی خسته‌کننده‌ست.
9. فقط و فقط فارسی محاوره‌ای/خیابونی طبیعی رپ فارسی، نه فارسی رسمی و کتابی.
10. اگه فضا و حس‌وحال متن اقتضا می‌کنه (خشم، اعتراض، دیس، فضای خیابونی)، از کلمات رکیک و ناسزای رایج در رپ فارسی واقعی بدون خودسانسوری استفاده کن - این بخش طبیعی و اصیل این ژانره. فقط برای حس‌وحال‌های ملایم‌تر (مثل R&B) لازم نیست زیاده‌روی کنی.
11. مگر خلاف این خواسته شده باشه، همیشه یه آهنگ کامل با ساختار استاندارد بساز (چندین ورس + هوک تکرارشونده)، نه فقط یکی دو بیت کوتاه.
12. حس‌وحال درخواستی باید توی همه‌ی جزئیات متن (کلمات، تصاویر، ریتم جمله‌ها) قابل تشخیص باشه، نه فقط یه برچسب اسمی - یعنی یه آدم که متن رو بدون دونستن برچسب بخونه، باید بتونه حدس بزنه حس‌وحالش چی بوده.

قوانین قالب‌بندی خروجی:
- دقیقاً از دو عنوان [تحلیل] و [متن نهایی] استفاده کن.
- داخل [متن نهایی]، اگه در دستور خواسته شده، برچسب بخش‌ها (مثل [ورس ۱]، [هوک]) رو نگه دار.
- هیچ توضیح اضافه‌ی دیگه‌ای، مقدمه‌چینی، یا markdown اضافی ننویس.
"""

FINAL_MARKER = "[متن نهایی]"


def _extract_final(raw_text: str) -> str:
    """بخش [تحلیل] داخلی رو حذف می‌کنه و فقط [متن نهایی] رو برمی‌گردونه."""
    idx = raw_text.rfind(FINAL_MARKER)
    if idx == -1:
        # اگه مدل فرمت رو رعایت نکرد، کل متن رو برگردون (fallback امن)
        return raw_text.strip()
    return raw_text[idx + len(FINAL_MARKER):].strip()


CRITIC_SYSTEM_PROMPT = """تو یک منتقد سرسخت و متخصص رپ فارسی هستی. یک پیش‌نویس متن رپ (احتمالاً یک آهنگ کامل با چند بخش) بهت داده میشه.

روش کارت (دو مرحله در یک خروجی):

مرحله ۱ - زیر عنوان [نقد]:
به‌طور فشرده (۴ تا ۶ خط) مشخص کن: کدوم خط‌ها قافیه‌ی ضعیف/کلیشه‌ای دارن، کجا تصویرسازی تکراریه، کجا پانچ‌لاین کم داره، و کجا حس‌وحال درخواستی به‌اندازه‌ی کافی قوی منتقل نشده. این بخش رو کاربر نمی‌بینه.

مرحله ۲ - زیر عنوان [متن نهایی]:
بازنویسی کامل و بهبودیافته‌ی متن با رعایت این معیارها:
- هر قافیه‌ی ضعیف/تکراری/پیش‌پاافتاده رو با قافیه‌ی چندهجایی و داخلی قوی‌تر جایگزین کن.
- هر تصویر کلیشه‌ای رو با یه تصویر تازه و عینی‌تر عوض کن.
- حداقل یکی دو پانچ‌لاین قوی‌تر در هر ورس اضافه/جایگزین کن.
- ریتم و طول خط‌ها رو برای خوانش طبیعی‌تر تنظیم کن.
- اگه لحن متن اجازه می‌ده، کلمات رکیک رو حذف نکن و حتی در صورت لزوم قوی‌ترش کن.
- ساختار کامل آهنگ (ورس‌ها، هوک، بخش‌های دیگه) و برچسب‌های بخش‌ها رو دقیقاً حفظ کن، چیزی رو کوتاه نکن یا حذف نکن.
- هویت سبکی، موضوع اصلی، و حس‌وحال متن رو دست نخور، فقط سطح فنی و کیفیت ادبی و شدت حس رو ببر بالا.

قوانین قالب‌بندی خروجی: دقیقاً از دو عنوان [نقد] و [متن نهایی] استفاده کن، بدون توضیح اضافه."""


async def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    # نکته: کلیدهای جدید Gemini (Auth keys, که با AQ. شروع می‌شن) باید توی هدر
    # x-goog-api-key فرستاده بشن، نه به‌صورت query param.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": config.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 1.05, "maxOutputTokens": 3200},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "خطا: پاسخ نامعتبر از Gemini. متن خام: " + str(data)[:500]


async def _call_openai(system_prompt: str, user_prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    payload = {
        "model": config.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 1.0,
        "max_tokens": 3200,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 3200,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def _extract_retry_seconds(error_text: str) -> float:
    """از متن خطای 429 عدد ثانیه‌ی پیشنهادی گوگل برای صبر کردن رو استخراج می‌کنه."""
    match = re.search(r"retry in ([\d.]+)s", error_text)
    if match:
        return float(match.group(1))
    return 15.0  # مقدار پیش‌فرض اگه گوگل عددی نداده باشه


async def _call_provider(system_prompt: str, user_prompt: str, max_retries: int = 2) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if config.LLM_PROVIDER == "gemini":
                return await _call_gemini(system_prompt, user_prompt)
            if config.LLM_PROVIDER == "openai":
                return await _call_openai(system_prompt, user_prompt)
            if config.LLM_PROVIDER == "claude":
                return await _call_claude(system_prompt, user_prompt)
            raise ValueError(f"LLM_PROVIDER نامعتبر: {config.LLM_PROVIDER}")
        except RuntimeError as e:
            error_text = str(e)
            is_rate_limit = "429" in error_text or "RESOURCE_EXHAUSTED" in error_text
            if is_rate_limit and attempt < max_retries:
                wait_seconds = min(_extract_retry_seconds(error_text) + 2, 60)
                await asyncio.sleep(wait_seconds)
                last_error = e
                continue
            raise
    raise last_error


async def generate_text(user_prompt: str, extra_system: str = "") -> str:
    system_prompt = SYSTEM_PROMPT_BASE + ("\n" + extra_system if extra_system else "")
    raw = await _call_provider(system_prompt, user_prompt)
    return _extract_final(raw)


async def refine_text(draft: str) -> str:
    """یه دور بازبینی و ارتقای کیفیت روی یه پیش‌نویس متن رپ."""
    raw = await _call_provider(CRITIC_SYSTEM_PROMPT, draft)
    return _extract_final(raw)


async def generate_text_pro(user_prompt: str, extra_system: str = "") -> str:
    """تولید دو‌مرحله‌ای: پیش‌نویس اولیه + یک دور بازبینی/ارتقا برای کیفیت حرفه‌ای‌تر."""
    draft = await generate_text(user_prompt, extra_system)
    try:
        return await refine_text(draft)
    except Exception:
        return draft


# ---------- بلوک‌های سبک (Context Blocks) ----------

def rapper_style_block(gen_title: str, rapper_name: str, mood_hint: str) -> str:
    return (
        f"سبک مرجع: رپر «{rapper_name}» از {gen_title}\n"
        f"ویژگی‌های سبکی این رپر: {mood_hint}\n"
        "مهم: باید واقعاً و ملموس شبیه سبک همین رپر بنویسی، نه یه رپ فارسی عمومی و کلی. "
        "قبل از نوشتن، توی ذهنت مجسم کن این رپر خاص دقیقاً با این ویژگی‌ها چطور همین موضوع رو روایت می‌کرد، "
        "بعد بر همون اساس بنویس. کپی کلمه‌به‌کلمه از کارهای واقعیش نکن، فقط هویت سبکی رو بگیر."
    )


def personal_style_block(profile_summary: str) -> str:
    return (
        "سبک مرجع: سبک شخصی و منحصربه‌فرد خود کاربر (استخراج‌شده از نمونه‌ی واقعی آهنگ و متن خودش)\n\n"
        f"{profile_summary}\n\n"
        "مهم خیلی زیاد: این کار باید دقیقاً حس بده که خود کاربر نوشتتش. الگوی قافیه‌بندی، طول خط، "
        "تراکم کلمات، سطح رکیک‌بودن، و لحن احساسیِ نمونه‌ی بالا رو دقیق کپی کن (نه محتوا و کلمات رو - "
        "بلکه سبک، ریتم درونی، و شخصیت نوشتاری رو). اگه نمونه‌ی کاربر خط‌های کوتاه داشت، تو هم کوتاه بنویس؛ "
        "اگه پرکلمه و فشرده بود، تو هم همون‌جوری بنویس. این مهم‌تر از هر قانون کلی دیگه‌ست."
    )


def beat_style_block(beat_summary: str) -> str:
    return (
        "این متن قراره روی یه بیت واقعی که خود کاربر فرستاده خونده بشه. ویژگی‌های استخراج‌شده از بیت:\n"
        f"{beat_summary}\n\n"
        "متن باید با تمپو و انرژی این بیت کاملاً هماهنگ باشه: برای بیت‌های تند، خط‌های کوتاه‌تر و فلوی "
        "فشرده‌تر و رپید-فایر بنویس؛ برای بیت‌های آروم و اتمسفریک، خط‌های کشیده‌تر، روایی‌تر و با مکث‌های "
        "طبیعی‌تر بنویس. تعداد هجای هر خط باید با ریتم این بیت جور دربیاد."
    )


def mood_block(mood_style: str, focus_words: str) -> str:
    focus_part = (
        f"تمرکز اصلی موضوع/کلمات روی: {focus_words}"
        if focus_words
        else "موضوع خاصی مشخص نشده - کاملاً بر اساس حس‌وحال زیر آزادانه بنویس."
    )
    return f"حس‌وحال/سبک مورد نظر برای این کار: {mood_style}\n{focus_part}"


# ---------- پرامپت‌سازها ----------

def build_preview_prompt(style_block: str, mood_block_text: str) -> str:
    return f"""{style_block}

{mood_block_text}

در این مرحله فقط یک پیش‌نمایش کوتاه بساز: دقیقاً یک ورس ۸ خطی + یک هوک ۴ خطی.
هدف اینه که کاربر حس کلی، لحن، و کیفیت کار رو ببینه و تصمیم بگیره که آهنگ کامل رو بسازیم یا نه.
برچسب بخش‌ها رو بذار: [ورس] و [هوک]."""


def build_full_song_prompt(style_block: str, mood_block_text: str, preview_text: str) -> str:
    return f"""{style_block}

{mood_block_text}

این پیش‌نمایشی هست که قبلاً بر اساس همین درخواست نوشته شده و مورد پسند کاربر بوده:
---
{preview_text}
---

حالا بر اساس دقیقاً همین پیش‌نمایش (همین لحن، همین موضوع، همین حس‌وحال)، یک آهنگ رپ فارسی کامل و تمام‌عیار بساز با این ساختار:

[ورس ۱] (۱۶ خط - می‌تونی ورس پیش‌نمایش رو گسترش بدی یا پایه قرار بدی)
[هوک] (۴ تا ۶ خط، تکرارشونده - می‌تونه دقیقاً همون هوک پیش‌نمایش باشه)
[ورس ۲] (۱۶ خط کاملاً جدید - ادامه‌ی همون داستان یا حس، از یه زاویه‌ی تازه)
[هوک] (تکرار دقیق هوک قبلی)
[ورس ۳] (۸ تا ۱۶ خط - می‌تونه اوج ماجرا یا جمع‌بندی احساسی باشه)
[آوترو] (۲ تا ۴ خط، جمع‌بندی نهایی و فرودِ آهنگ)

این باید یک آهنگ کامل واقعی باشه، نه فقط دو بیت کوتاه. طول کل کار باید در حد یک آهنگ رپ واقعی (حدود ۵۰-۷۰ خط) باشه. برچسب بخش‌ها رو دقیقاً همون‌طور که نوشتم توی خروجی نگه دار."""


def build_regenerate_full_prompt(style_block: str, mood_block_text: str) -> str:
    """برای وقتی کاربر می‌خواد یه آهنگ کامل کاملاً جدید بدون پیش‌نمایش قبلی بسازه."""
    return f"""{style_block}

{mood_block_text}

یک آهنگ رپ فارسی کامل و تمام‌عیار بساز با این ساختار:

[ورس ۱] (۱۶ خط)
[هوک] (۴ تا ۶ خط، تکرارشونده)
[ورس ۲] (۱۶ خط کاملاً جدید)
[هوک] (تکرار دقیق هوک قبلی)
[ورس ۳] (۸ تا ۱۶ خط)
[آوترو] (۲ تا ۴ خط)

این باید یک آهنگ کامل واقعی باشه (حدود ۵۰-۷۰ خط)، نه فقط دو بیت کوتاه."""
    
