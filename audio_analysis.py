# -*- coding: utf-8 -*-
"""
تحلیل صوتی heuristic برای استخراج حس‌وحال یه آهنگ (تمپو، انرژی، روشنی تن صدا).
این یه تحلیل تقریبیه، نه فهم واقعی موسیقی - هدفش فقط دادن چند سرنخ اضافه به
مدل زبانیه تا فلوی متنی که می‌سازه بهتر با ریتم آهنگ کاربر جور دربیاد.
"""
import librosa
import numpy as np


def analyze_audio(file_path: str) -> dict:
    y, sr = librosa.load(file_path, sr=22050, mono=True, duration=90)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])

    rms = float(np.mean(librosa.feature.rms(y=y)))
    spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))

    # دسته‌بندی کیفی و ساده بر اساس بازه‌های تجربی
    if tempo < 80:
        tempo_desc = "کند و سنگین (مناسب فلوی آروم و رسیتیشن‌گونه)"
    elif tempo < 110:
        tempo_desc = "متوسط (مناسب فلوی روایی و احساسی)"
    else:
        tempo_desc = "تند (مناسب فلوی تکنیکال و پرانرژی)"

    energy_desc = "پرانرژی و پرقدرت" if rms > 0.06 else "آروم و اتمسفریک"
    brightness_desc = "روشن و شاداب" if spectral_centroid > 2500 else "تاریک و دبگی"

    return {
        "tempo_bpm": round(tempo, 1),
        "tempo_desc": tempo_desc,
        "energy_desc": energy_desc,
        "brightness_desc": brightness_desc,
        "raw_zcr": round(zcr, 4),
    }


def audio_summary_text(analysis: dict) -> str:
    return (
        f"تمپو تقریبی: {analysis['tempo_bpm']} BPM ({analysis['tempo_desc']})\n"
        f"انرژی: {analysis['energy_desc']}\n"
        f"رنگ صدا: {analysis['brightness_desc']}"
    )
