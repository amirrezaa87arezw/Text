# -*- coding: utf-8 -*-
"""
تبدیل متن به گفتار با ElevenLabs، برای این‌که کاربر بشنوه فلو/ریتم متن
تقریباً چه‌جوریه.

⚠️ محدودیت مهم: این فقط یه خوانش گفتاری معمولیه (Text-to-Speech)، نه یه
اجرای واقعی رپ هماهنگ‌شده با بیت. TTS نمی‌تونه واقعاً «رپ بخونه» یا خودش
رو با BPM یه بیت هماهنگ کنه - فقط کمک می‌کنه حس تلفظ، مکث‌ها، و تاکیدهای
متن رو بشنوی.
"""
import re
import subprocess

import httpx
import config


def strip_section_labels(text: str) -> str:
    """حذف برچسب‌های ساختاری مثل [ورس ۱] قبل از فرستادن به TTS."""
    cleaned = re.sub(r"^\s*\[.*?\]\s*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def synthesize_speech(text: str) -> bytes:
    """متن رو به گفتار (mp3) تبدیل می‌کنه و بایت‌های صوتی رو برمی‌گردونه."""
    if not config.ELEVENLABS_API_KEY or not config.ELEVENLABS_VOICE_ID:
        raise RuntimeError(
            "ELEVENLABS_API_KEY یا ELEVENLABS_VOICE_ID تنظیم نشده. "
            "توی Variables ست‌شون کن تا قابلیت ویس فعال بشه."
        )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    # محدودیت طول متن برای جلوگیری از درخواست خیلی سنگین/گرون
    safe_text = text[:2500]
    payload = {
        "text": safe_text,
        "model_id": config.ELEVENLABS_MODEL_ID,
        "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.6},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"ElevenLabs API error {resp.status_code}: {resp.text[:400]}")
        return resp.content


def convert_mp3_to_ogg(mp3_path: str, ogg_path: str) -> None:
    """تبدیل mp3 به ogg/opus برای فرستادن به‌عنوان voice message تلگرام."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "48k", ogg_path],
        check=True,
        capture_output=True,
    )
