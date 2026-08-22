# -*- coding: utf-8 -*-
"""تحلیل ساده‌ی ساختاری متن رپ کاربر (طول خط، تعداد خط، تراکم قافیه تقریبی)."""
import re


def analyze_lyrics(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return {"line_count": 0, "avg_words_per_line": 0, "sample_endings": []}

    word_counts = [len(re.findall(r"\S+", l)) for l in lines]
    avg_words = sum(word_counts) / len(word_counts)

    # آخرین کلمه‌ی هر خط، به عنوان سرنخ الگوی قافیه
    endings = []
    for l in lines:
        words = re.findall(r"\S+", l)
        if words:
            endings.append(words[-1])

    return {
        "line_count": len(lines),
        "avg_words_per_line": round(avg_words, 1),
        "sample_endings": endings[:12],
    }


def lyrics_summary_text(analysis: dict) -> str:
    if analysis["line_count"] == 0:
        return "متنی برای تحلیل ثبت نشده."
    endings = "، ".join(analysis["sample_endings"])
    return (
        f"تعداد خط نمونه: {analysis['line_count']}\n"
        f"میانگین کلمه در هر خط: {analysis['avg_words_per_line']}\n"
        f"نمونه کلمات پایانی خط‌ها (سرنخ قافیه): {endings}"
    )
