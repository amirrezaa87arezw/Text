# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import tempfile

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import db
import llm
import moods as moods_data
import rappers as rappers_data
import tts
from audio_analysis import analyze_audio, audio_summary_text
from text_analysis import analyze_lyrics, lyrics_summary_text

logging.basicConfig(level=logging.INFO)
router = Router()


class PersonalFlowSetup(StatesGroup):
    waiting_audio = State()
    waiting_lyrics = State()


class Flow(StatesGroup):
    waiting_focus = State()


# ---------- کیبوردها ----------

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎤 تکست نوشتن", callback_data="menu:write")],
            [InlineKeyboardButton(text="🎧 فلو شخصی", callback_data="menu:flow")],
            [InlineKeyboardButton(text="🎵 نوشتن روی بیت", callback_data="menu:beat")],
        ]
    )


def generations_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, title in rappers_data.get_generation_titles().items():
        rows.append([InlineKeyboardButton(text=title, callback_data=f"gen:{key}")])
    rows.append([InlineKeyboardButton(text="🏠 منو اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rappers_kb(gen_key: str) -> InlineKeyboardMarkup:
    rows = []
    for r in rappers_data.get_rappers(gen_key):
        rows.append(
            [InlineKeyboardButton(text=r["name"], callback_data=f"rapper:{gen_key}:{r['name']}")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ برگشت به نسل‌ها", callback_data="menu:write")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moods_kb() -> InlineKeyboardMarkup:
    rows = []
    items = list(moods_data.MOODS.items())
    for i in range(0, len(items), 2):
        row = []
        for key, mood in items[i : i + 2]:
            row.append(InlineKeyboardButton(text=mood["label"], callback_data=f"mood:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏠 منو اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def preview_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ عالیه، آهنگ کامل رو بساز", callback_data="sf:full")],
            [InlineKeyboardButton(text="🔁 پیش‌نمایش جدید", callback_data="sf:preview_retry")],
            [InlineKeyboardButton(text="🏠 منو اصلی", callback_data="menu:home")],
        ]
    )


def after_full_song_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ بهترش کن", callback_data="refine:last")],
            [InlineKeyboardButton(text="🎙 بشنو چطوری میشه", callback_data="tts:last")],
            [InlineKeyboardButton(text="🔁 آهنگ کامل دیگه بساز", callback_data="sf:full")],
            [InlineKeyboardButton(text="🏠 منو اصلی", callback_data="menu:home")],
        ]
    )


def personal_flow_menu_kb(has_profile: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_profile:
        rows.append(
            [InlineKeyboardButton(text="🎯 بساز با فلوی من", callback_data="pf:generate")]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 ثبت/آپدیت نمونه فلو", callback_data="pf:new_sample")]
    )
    rows.append([InlineKeyboardButton(text="🏠 منو اصلی", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- هندلرها: منو ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "سلام 👋\n"
        "به ربات تکست‌نویسی رپ فارسی خوش اومدی.\n\n"
        "یکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("منو اصلی:", reply_markup=main_menu_kb())
    await callback.answer()


# ---------- مسیر ۱: تکست نوشتن با انتخاب رپر ----------

@router.callback_query(F.data == "menu:write")
async def cb_write_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "یکی از نسل‌های رپ فارسی رو انتخاب کن:", reply_markup=generations_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gen:"))
async def cb_choose_generation(callback: CallbackQuery, state: FSMContext):
    gen_key = callback.data.split(":", 1)[1]
    title = rappers_data.get_generation_titles().get(gen_key, gen_key)
    await callback.message.edit_text(
        f"{title}\nحالا یه رپر مرجع انتخاب کن:", reply_markup=rappers_kb(gen_key)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rapper:"))
async def cb_choose_rapper(callback: CallbackQuery, state: FSMContext):
    _, gen_key, rapper_name = callback.data.split(":", 2)
    rapper = rappers_data.get_rapper(gen_key, rapper_name)
    gen_title = rappers_data.get_generation_titles().get(gen_key, gen_key)
    style_block = llm.rapper_style_block(gen_title, rapper_name, rapper["mood_hint"])
    await state.update_data(context_type="rapper", style_block=style_block, context_label=rapper_name)
    await callback.message.edit_text(
        f"سبک انتخابی: {rapper_name}\n\nحالا حس‌وحال موزیک رو انتخاب کن:",
        reply_markup=moods_kb(),
    )
    await callback.answer()


# ---------- مسیر ۲: فلو شخصی ----------

@router.callback_query(F.data == "menu:flow")
async def cb_flow_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    profile = await db.get_profile(callback.from_user.id)
    text = (
        "بخش «فلو شخصی» 🎧\n\n"
        "یه آهنگ از خودت (فایل صوتی) + متنش رو برام بفرست، تحلیلش می‌کنم و "
        "از این به بعد می‌تونم دقیقاً با همون فلو برات متن بنویسم."
    )
    if profile:
        text += "\n\n✅ الان یه پروفایل فلو ازت ثبت شده."
    await callback.message.edit_text(text, reply_markup=personal_flow_menu_kb(bool(profile)))
    await callback.answer()


@router.callback_query(F.data == "pf:new_sample")
async def cb_pf_new_sample(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PersonalFlowSetup.waiting_audio)
    await callback.message.edit_text(
        "اول فایل صوتی آهنگت رو بفرست (voice یا audio).\n"
        f"حجم حداکثر: {config.MAX_AUDIO_MB}MB"
    )
    await callback.answer()


async def handle_pf_audio(message: Message, state: FSMContext, bot: Bot):
    file_obj = message.audio or message.voice or message.document
    if file_obj.file_size and file_obj.file_size > config.MAX_AUDIO_MB * 1024 * 1024:
        await message.answer(f"فایل خیلی بزرگه، حداکثر {config.MAX_AUDIO_MB}MB.")
        return

    waiting_msg = await message.answer("⏳ دارم صدا رو تحلیل می‌کنم...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.join(tmp_dir, "audio_input")
        tg_file = await bot.get_file(file_obj.file_id)
        await bot.download_file(tg_file.file_path, destination=local_path)
        try:
            analysis = analyze_audio(local_path)
        except Exception as e:
            await waiting_msg.edit_text(
                f"❌ نتونستم فایل صوتی رو پردازش کنم: {e}\n"
                "مطمئن شو فرمتش پشتیبانی‌شده‌ست (mp3/ogg/wav/m4a)."
            )
            return

    await state.update_data(audio_analysis=audio_summary_text(analysis))
    await state.set_state(PersonalFlowSetup.waiting_lyrics)
    await waiting_msg.edit_text(
        "✅ صدا تحلیل شد:\n\n"
        f"{audio_summary_text(analysis)}\n\n"
        "حالا متن (لیریک) همین آهنگ رو به صورت تکست بفرست (هر چقدر کامل‌تر بهتر - "
        "این متن دقیقاً برای یادگیری سبک نوشتاری خودت استفاده میشه)."
    )


@router.message(PersonalFlowSetup.waiting_lyrics, F.text)
async def handle_pf_lyrics_text(message: Message, state: FSMContext):
    data = await state.get_data()
    audio_summary = data.get("audio_analysis", "")
    text_analysis = analyze_lyrics(message.text)
    text_summary = lyrics_summary_text(text_analysis)

    # این متن، متن خود کاربره (نه اثر شخص ثالث)، پس آزادانه به‌عنوان نمونه‌ی
    # سبکی کامل به مدل داده میشه - محدودیت کپی‌رایت اینجا صدق نمی‌کنه.
    profile_summary = (
        f"[تحلیل صوتی آهنگ مرجع کاربر]\n{audio_summary}\n\n"
        f"[تحلیل ساختاری متن مرجع کاربر]\n{text_summary}\n\n"
        f"[نمونه‌ی کامل و واقعی متن خود کاربر - این دقیق‌ترین منبع برای یادگیری سبکشه]\n{message.text[:2000]}"
    )
    await db.save_profile(message.from_user.id, profile_summary)
    await state.clear()

    await message.answer(
        "✅ فلوی شخصیت ثبت شد!\nحالا می‌تونی با «بساز با فلوی من» متن جدید بگیری.",
        reply_markup=personal_flow_menu_kb(True),
    )


@router.callback_query(F.data == "pf:generate")
async def cb_pf_generate(callback: CallbackQuery, state: FSMContext):
    profile = await db.get_profile(callback.from_user.id)
    if not profile:
        await callback.answer("هنوز پروفایلی ثبت نشده.", show_alert=True)
        return
    style_block = llm.personal_style_block(profile)
    await state.update_data(context_type="personal", style_block=style_block, context_label="فلوی شخصی")
    await callback.message.edit_text("حس‌وحال موزیک رو انتخاب کن:", reply_markup=moods_kb())
    await callback.answer()


# ---------- مسیر ۳: نوشتن روی بیت ----------

@router.callback_query(F.data == "menu:beat")
async def cb_beat_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PersonalFlowSetup.waiting_audio)
    await state.update_data(mode="beat")
    await callback.message.edit_text(
        "🎵 بیت (موزیک بی‌کلام) رو برام بفرست تا تحلیلش کنم و روش متن بنویسم.\n"
        f"حجم حداکثر: {config.MAX_BEAT_MB}MB"
    )
    await callback.answer()


@router.message(PersonalFlowSetup.waiting_audio, F.audio | F.voice | F.document)
async def handle_audio_generic(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    mode = data.get("mode")

    file_obj = message.audio or message.voice or message.document
    if file_obj.file_size and file_obj.file_size > config.MAX_BEAT_MB * 1024 * 1024:
        await message.answer(f"فایل خیلی بزرگه، حداکثر {config.MAX_BEAT_MB}MB.")
        return

    if mode == "beat":
        waiting_msg = await message.answer("⏳ دارم بیت رو تحلیل می‌کنم...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, "beat_input")
            tg_file = await bot.get_file(file_obj.file_id)
            await bot.download_file(tg_file.file_path, destination=local_path)
            try:
                analysis = analyze_audio(local_path)
            except Exception as e:
                await waiting_msg.edit_text(f"❌ نتونستم بیت رو پردازش کنم: {e}")
                return

        beat_summary = audio_summary_text(analysis)
        style_block = llm.beat_style_block(beat_summary)
        await state.update_data(
            context_type="beat", style_block=style_block, context_label="بیت ارسالی"
        )
        await waiting_msg.edit_text(
            f"✅ بیت تحلیل شد:\n\n{beat_summary}\n\nحالا حس‌وحال موزیک رو انتخاب کن:",
            reply_markup=moods_kb(),
        )
        return

    # در غیر این صورت، این فایل صوتی برای فلوی شخصیه
    await handle_pf_audio(message, state, bot)


@router.message(PersonalFlowSetup.waiting_audio)
async def handle_pf_audio_wrong_type(message: Message):
    await message.answer("لطفاً یه فایل صوتی (voice یا audio) بفرست.")


# ---------- انتخاب حس‌وحال + کلمات تمرکز + پیش‌نمایش + آهنگ کامل ----------

@router.callback_query(F.data.startswith("mood:"))
async def cb_choose_mood(callback: CallbackQuery, state: FSMContext):
    mood_key = callback.data.split(":", 1)[1]
    mood = moods_data.get_mood(mood_key)
    if not mood:
        await callback.answer("این حس‌وحال پیدا نشد.", show_alert=True)
        return
    await state.update_data(mood_key=mood_key)
    await state.set_state(Flow.waiting_focus)
    await callback.message.edit_text(
        f"حس‌وحال انتخابی: {mood['label']}\n\n"
        "چند تا کلمه یا موضوع بفرست که روشون تمرکز کنیم "
        "(مثلاً: دلتنگی یه رفیق، خشم از بی‌پولی، خیانت...)\n"
        "یا بنویس «آزاد» تا کاملاً بر اساس حس‌وحال بالا بنویسم."
    )
    await callback.answer()


async def _generate_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    mood = moods_data.get_mood(data["mood_key"])
    mood_text = llm.mood_block(mood["style"], data.get("focus_words", ""))
    prompt = llm.build_preview_prompt(data["style_block"], mood_text)

    waiting_msg = await message.answer("⏳ دارم یه پیش‌نمایش می‌سازم...")
    try:
        preview = await llm.generate_text(prompt)
    except Exception as e:
        await waiting_msg.edit_text(f"❌ خطا در تولید متن: {e}")
        return

    await waiting_msg.delete()
    await state.update_data(preview_text=preview)
    await message.answer(
        f"🎤 پیش‌نمایش:\n\n{preview}\n\nنظرت چیه؟",
        reply_markup=preview_confirm_kb(),
    )


@router.message(Flow.waiting_focus, F.text)
async def handle_focus_words(message: Message, state: FSMContext):
    focus = "" if message.text.strip() in ("آزاد", "ازاد") else message.text.strip()
    await state.update_data(focus_words=focus)
    await _generate_preview(message, state)


@router.callback_query(F.data == "sf:preview_retry")
async def cb_preview_retry(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _generate_preview(callback.message, state)


@router.callback_query(F.data == "sf:full")
async def cb_generate_full_song(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "style_block" not in data or "mood_key" not in data:
        await callback.answer("اطلاعات کافی نیست، از اول شروع کن.", show_alert=True)
        return
    mood = moods_data.get_mood(data["mood_key"])
    mood_text = llm.mood_block(mood["style"], data.get("focus_words", ""))
    preview_text = data.get("preview_text")

    if preview_text:
        prompt = llm.build_full_song_prompt(data["style_block"], mood_text, preview_text)
    else:
        prompt = llm.build_regenerate_full_prompt(data["style_block"], mood_text)

    await callback.answer()
    waiting_msg = await callback.message.answer(
        "⏳ دارم آهنگ کامل رو می‌سازم و یه دور ویرایش حرفه‌ای هم می‌زنم "
        "(ممکنه کمی طول بکشه چون کارش بزرگه)..."
    )
    try:
        full_song = await llm.generate_text_pro(prompt)
    except Exception as e:
        await waiting_msg.edit_text(f"❌ خطا در تولید متن: {e}")
        return

    await waiting_msg.delete()
    await state.update_data(last_lyrics=full_song)
    await callback.message.answer(full_song, reply_markup=after_full_song_kb())


@router.callback_query(F.data == "refine:last")
async def cb_refine_last(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_lyrics = data.get("last_lyrics")
    if not last_lyrics:
        await callback.answer("چیزی برای بهتر کردن پیدا نکردم، اول یه آهنگ بساز.", show_alert=True)
        return

    await callback.answer("⏳ دارم بهترش می‌کنم...")
    try:
        improved = await llm.refine_text(last_lyrics)
    except Exception as e:
        await callback.message.answer(f"❌ خطا در بهبود متن: {e}")
        return

    await state.update_data(last_lyrics=improved)
    await callback.message.answer(improved, reply_markup=after_full_song_kb())


# ---------- بشنو چطوری میشه (TTS) ----------

@router.callback_query(F.data == "tts:last")
async def cb_tts_last(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_lyrics = data.get("last_lyrics")
    if not last_lyrics:
        await callback.answer("چیزی برای خوندن پیدا نکردم.", show_alert=True)
        return

    await callback.answer()
    waiting_msg = await callback.message.answer(
        "⏳ دارم ویس می‌سازم... (این فقط یه خوانش گفتاریه تا حس متن دستت بیاد، "
        "نه یه اجرای واقعی رپ روی بیت)"
    )
    try:
        clean_text = tts.strip_section_labels(last_lyrics)
        mp3_bytes = await tts.synthesize_speech(clean_text)
    except Exception as e:
        await waiting_msg.edit_text(f"❌ خطا در ساخت ویس: {e}")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        mp3_path = os.path.join(tmp_dir, "speech.mp3")
        ogg_path = os.path.join(tmp_dir, "speech.ogg")
        with open(mp3_path, "wb") as f:
            f.write(mp3_bytes)
        try:
            tts.convert_mp3_to_ogg(mp3_path, ogg_path)
        except Exception as e:
            await waiting_msg.edit_text(f"❌ خطا در تبدیل فرمت ویس: {e}")
            return

        await waiting_msg.delete()
        await bot.send_voice(chat_id=callback.message.chat.id, voice=FSInputFile(ogg_path))


# ---------- اجرا ----------

async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده. توی .env مقداردهیش کن.")

    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
