# -*- coding: utf-8 -*-
"""
لایه‌ی یکپارچه برای صدا زدن مدل زبانی. با تغییر LLM_PROVIDER در .env
می‌تونی بین Gemini / OpenAI / Claude سوییچ کنی بدون تغییر بقیه‌ی کد.
"""
import httpx
import config

SYSTEM_PROMPT_BASE = """تو یک متن‌نویس رپ فارسی درجه‌یک و حرفه‌ای هستی، در حد بهترین رپرهای زیرزمینی و مین‌استریم ایران.

چک‌لیست فنی که باید توی هر متن رعایت کنی:
1. قافیه‌ی آخر خط + قافیه‌ی داخلی (Internal Rhyme) در طول خط، نه فقط ته خط.
2. قافیه‌ی چندهجایی (Multisyllabic Rhyme) حداقل چند بار در هر ورس - نه فقط قافیه‌ی تک‌هجایی ساده.
3. حداقل ۲-۳ پانچ‌لاین واقعی در هر ورس (جمله‌ای که غافلگیرکننده باشه، معنای دوگانه داشته باشه، یا با یه چرخش غیرمنتظره تموم بشه).
4. تصویرسازی تازه و عینی - از کلیشه‌های تکراری رپ فارسی («شب»، «تنهایی»، «زخم»، «دود سیگار» بدون زاویه‌ی نو) پرهیز کن مگر با یه ایده‌ی تازه بازش کنی.
5. یه آرک روایی مشخص در هر ورس داشته باش (شروع-میانه-اوج)، نه فقط ردیف کردن جمله‌های قطعی از هم.
6. وردپلی و بازی با چندمعنایی کلمات فارسی، در حد امکان.
7. فقط و فقط فارسی محاوره‌ای/خیابونی طبیعی رپ فارسی بنویس، نه فارسی رسمی و کتابی.
8. ساختار استاندارد ورس/هوک رو رعایت کن مگر کاربر خلافش رو بخواد.

خروجی فقط خود متن رپ باشه، بدون توضیح اضافه، بدون مقدمه‌چینی، بدون علامت‌گذاری markdown اضافی.
"""

CRITIC_SYSTEM_PROMPT = """تو یک منتقد سرسخت و متخصص رپ فارسی هستی. یک پیش‌نویس متن رپ بهت داده میشه.
وظیفه‌ت: بازنویسی کامل و بهبودیافته‌ی همون متن، با رعایت دقیق این معیارها:
- هر جا قافیه ضعیف/تکراری/پیش‌پاافتاده بود، با قافیه‌ی چندهجایی و داخلی قوی‌تر جایگزینش کن.
- هر جا تصویر کلیشه‌ای بود، با یه تصویر تازه و عینی‌تر عوضش کن.
- حداقل یکی دو پانچ‌لاین قوی‌تر اضافه/جایگزین کن.
- ریتم و طول خط‌ها رو برای خوانش طبیعی‌تر تنظیم کن.
- هویت سبکی و موضوع اصلی متن رو دست نخور، فقط سطح فنی و کیفیت ادبی رو ببر بالا.

خروجی فقط نسخه‌ی نهایی و بازنویسی‌شده‌ی متن باشه، بدون توضیح، بدون مقدمه، بدون یادداشت نقد."""


async def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    # نکته: کلیدهای جدید Gemini (Auth keys, که با AQ. شروع می‌شن) باید توی هدر
    # x-goog-api-key فرستاده بشن، نه به‌صورت query param. کلیدهای قدیمی‌تر
    # (AIza...) هم با این روش هدر کار می‌کنن، پس این روش امن‌تره.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": config.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 1.0, "maxOutputTokens": 1200},
    }
    async with httpx.AsyncClient(timeout=60) as client:
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
        "max_tokens": 1200,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
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
        "max_tokens": 1200,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


async def _call_provider(system_prompt: str, user_prompt: str) -> str:
    if config.LLM_PROVIDER == "gemini":
        return await _call_gemini(system_prompt, user_prompt)
    if config.LLM_PROVIDER == "openai":
        return await _call_openai(system_prompt, user_prompt)
    if config.LLM_PROVIDER == "claude":
        return await _call_claude(system_prompt, user_prompt)
    raise ValueError(f"LLM_PROVIDER نامعتبر: {config.LLM_PROVIDER}")


async def generate_text(user_prompt: str, extra_system: str = "") -> str:
    system_prompt = SYSTEM_PROMPT_BASE + ("\n" + extra_system if extra_system else "")
    return await _call_provider(system_prompt, user_prompt)


async def refine_text(draft: str) -> str:
    """یه دور بازبینی و ارتقای کیفیت روی یه پیش‌نویس متن رپ."""
    return await _call_provider(CRITIC_SYSTEM_PROMPT, draft)


async def generate_text_pro(user_prompt: str, extra_system: str = "") -> str:
    """تولید دو‌مرحله‌ای: پیش‌نویس اولیه + یک دور بازبینی/ارتقا برای کیفیت حرفه‌ای‌تر."""
    draft = await generate_text(user_prompt, extra_system)
    try:
        return await refine_text(draft)
    except Exception:
        # اگه مرحله‌ی ریفاین خطا داد، حداقل پیش‌نویس اولیه رو برگردون
        return draft


def build_generation_prompt(gen_title: str, rapper_name: str, mood_hint: str, topic: str) -> str:
    return f"""یک متن رپ فارسی کامل (حداقل ۲ ورس ۱۶ خطی + یک هوک ۴ خطی) بنویس.

سبک مرجع: رپر «{rapper_name}» از {gen_title}
حس‌وحال و ویژگی‌های سبکی این رپر: {mood_hint}
موضوع/حس مورد نظر کاربر: {topic if topic else "آزاد، بر اساس سبک همون رپر انتخاب کن"}

هدف: متنی بنویس که هم‌تراز بهترین کارهای این رپر باشه، حتی یک پله جلوتر از نظر
تازگی تصویرها و پیچیدگی قافیه — ولی هویت سبکی همون رپر رو حفظ کن، کپی کلمه‌به‌کلمه نکن."""


def build_personal_flow_prompt(profile_summary: str, topic: str) -> str:
    return f"""بر اساس پروفایل سبکی زیر که از تحلیل آهنگ و متن‌های قبلی خود کاربر استخراج شده،
یک متن رپ فارسی جدید و کامل (حداقل ۲ ورس ۱۶ خطی + هوک) دقیقاً در همون فلو و لحن شخصی کاربر بنویس:

{profile_summary}

موضوع/حس مورد نظر برای این متن: {topic if topic else "آزاد، هماهنگ با حال‌وهوای کارهای قبلی کاربر"}

مهم: باید طوری بنویسی که انگار خود کاربر نوشته - همون الگوی قافیه‌بندی، طول خط،
و لحن احساسی رو حفظ کن."""
    
