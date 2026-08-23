# -*- coding: utf-8 -*-
"""
تحلیل صوتی heuristic برای استخراج حس‌وحال یه آهنگ یا بیت (تمپو، انرژی،
روشنی تن صدا، سنگینی باس). این یه تحلیل تقریبیه، نه فهم واقعی موسیقی -
هدفش فقط دادن چند سرنخ اضافه به مدل زبانیه.

نکته‌ی فنی مهم: به‌جای تکیه به ffmpeg نصب‌شده روی سیستم عامل (که روی
بعضی هاست‌ها مثل Railway ممکنه درست نصب/پیدا نشه)، از پکیج imageio-ffmpeg
استفاده می‌کنیم که یه باینری ffmpeg مستقل رو همراه خودش نصب می‌کنه. این
باعث میشه فرمت‌های مختلف (ogg/opus تلگرام، mp3، m4a، ...) همیشه درست
دیکود بشن، مستقل از تنظیمات هاست.
"""
import os
import subprocess
import tempfile

import imageio_ffmpeg
import librosa
import numpy as np


def _get_ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _decode_to_wav(input_path: str, target_sr: int = 22050) -> str:
    """هر فرمت صوتی رو به یه wav تک‌کاناله‌ی استاندارد تبدیل می‌کنه."""
    ffmpeg_exe = _get_ffmpeg_path()
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    result = subprocess.run(
        [
            ffmpeg_exe, "-y", "-i", input_path,
            "-ac", "1", "-ar", str(target_sr),
            "-t", "120",  # حداکثر ۱۲۰ ثانیه کافیه برای تحلیل
            wav_path,
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        os.remove(wav_path)
        raise RuntimeError(f"خطای ffmpeg در دیکود فایل صوتی: {result.stderr.decode(errors='ignore')[:300]}")
    return wav_path


def _fix_tempo_octave_error(tempo: float) -> float:
    """librosa گاهی تمپو رو نصف یا دوبرابر واقعیش تشخیص می‌ده. چون رپ/ترپ/دریل
    فارسی معمولاً بین ۶۰ تا ۱۸۰ بی‌پی‌ام هستن، این خطا رو تصحیح می‌کنیم."""
    if tempo <= 0:
        return tempo
    while tempo < 60:
        tempo *= 2
    while tempo > 185:
        tempo /= 2
    return tempo


def analyze_audio(file_path: str) -> dict:
    wav_path = _decode_to_wav(file_path)
    try:
        y, sr = librosa.load(wav_path, sr=22050, mono=True, duration=110)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass

    if y.size == 0:
        raise RuntimeError("فایل صوتی خالی یا قابل خوندن نبود.")

    # --- تمپو (با آنالیز onset، دقیق‌تر از حالت پیش‌فرض) ---
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    tempo = _fix_tempo_octave_error(float(np.atleast_1d(tempo)[0]))

    # --- انرژی کلی (RMS) ---
    rms_frames = librosa.feature.rms(y=y)[0]
    rms_mean = float(np.mean(rms_frames))
    rms_std = float(np.std(rms_frames))

    # --- رنگ صدا (Spectral Centroid) ---
    spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    # --- سنگینی باس (برای تشخیص ترپ/دریل سنگین در برابر بیت سبک) ---
    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = freqs < 150
    bass_energy = float(np.mean(stft[bass_mask, :])) if bass_mask.any() else 0.0
    overall_energy = float(np.mean(stft)) if stft.size else 1e-9
    bass_ratio = bass_energy / overall_energy if overall_energy > 0 else 0.0

    # --- دسته‌بندی کیفی ---
    if tempo < 80:
        tempo_desc = "کند و سنگین (مناسب فلوی آروم، روایی و رسیتیشن‌گونه)"
    elif tempo < 100:
        tempo_desc = "متوسط‌رو‌به‌کند (مناسب فلوی روایی و احساسی، گنگ/سد رپ)"
    elif tempo < 130:
        tempo_desc = "متوسط (مناسب فلوی معمولی رپ فارسی)"
    elif tempo < 155:
        tempo_desc = "تند (مناسب فلوی تکنیکال، پرانرژی، گنگ فست)"
    else:
        tempo_desc = "خیلی تند (مناسب فلوی رپید-فایر و دریل)"

    energy_desc = (
        "پرانرژی و پرقدرت" if rms_mean > 0.05 else "آروم و کم‌فشار"
    )
    dynamics_desc = (
        "با فراز و فرود زیاد (بخش‌های آروم و اوج مشخص)"
        if rms_std > 0.03
        else "یکنواخت و پیوسته"
    )
    brightness_desc = "روشن و شاداب" if spectral_centroid > 2200 else "تاریک و دبگی"
    bass_desc = "باس سنگین (ترپ/دریل‌وار)" if bass_ratio > 0.30 else "باس متعادل/سبک"

    return {
        "tempo_bpm": round(tempo, 1),
        "tempo_desc": tempo_desc,
        "energy_desc": energy_desc,
        "dynamics_desc": dynamics_desc,
        "brightness_desc": brightness_desc,
        "bass_desc": bass_desc,
    }


def audio_summary_text(analysis: dict) -> str:
    return (
        f"تمپو تقریبی: {analysis['tempo_bpm']} BPM ({analysis['tempo_desc']})\n"
        f"انرژی: {analysis['energy_desc']}، {analysis['dynamics_desc']}\n"
        f"رنگ صدا: {analysis['brightness_desc']}\n"
        f"باس: {analysis['bass_desc']}"
    )
    
