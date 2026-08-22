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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import db
import llm
import rappers as rappers_data
from audio_analysis import analyze_audio, audio_summary_text
from text_analysis import analyze_lyrics, lyrics_summary_text

logging.basicConfig(level=logging.INFO)
router = Router()


class TextWriting(StatesGroup):
    waiting_topic = State()


class PersonalFlow(StatesGroup):
    waiting_audio = State()
    waiting_lyrics = State()
    waiting_topic = State()


# ---------- کیبوردها ----------

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎤 تکست نوشتن", callback_data="menu:write")],
            [InlineKeyboardButton(text="🎧 فلو شخصی", callback_data="menu:flow")],
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


def after_generate_kb(regen_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ بهترش کن", callback_data="refine:last")],
            [InlineKeyboardButton(text="🔁 یکی دیگه بساز", callback_data=regen_callback)],
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
    await state.set_state(TextWriting.waiting_topic)
    await state.update_data(gen_key=gen_key, rapper_name=rapper_name)
    await callback.message.edit_text(
        f"سبک انتخابی: {rapper_name}\n\n"
        "حالا موضوع یا حس‌وحالی که می‌خوای توی متن باشه رو بنویس "
        "(مثلاً: دلتنگی، خشم از بی‌پولی، عشق تموم‌شده...)\n"
        "یا فقط بنویس «آزاد» تا خودم انتخاب کنم."
    )
    await callback.answer()


@router.message(TextWriting.waiting_topic)
async def handle_topic_for_generation(message: Message, state: FSMContext):
    data = await state.get_data()
    gen_key = data["gen_key"]
    rapper_name = data["rapper_name"]
    rapper = rappers_data.get_rapper(gen_key, rapper_name)
    gen_title = rappers_data.get_generation_titles().get(gen_key, gen_key)
    topic = "" if message.text.strip() in ("آزاد", "ازاد") else message.text.strip()

    waiting_msg = await message.answer("⏳ دارم پیش‌نویس رو می‌نویسم و بعد یه دور ویرایش حرفه‌ای می‌زنم...")
    prompt = llm.build_generation_prompt(gen_title, rapper_name, rapper["mood_hint"], topic)
    try:
        lyrics = await llm.generate_text_pro(prompt)
    except Exception as e:
        await waiting_msg.edit_text(f"❌ خطا در تولید متن: {e}")
        return

    await waiting_msg.delete()
    regen_cb = f"rapper:{gen_key}:{rapper_name}"
    await state.update_data(last_lyrics=lyrics, last_regen_cb=regen_cb)
    await message.answer(lyrics, reply_markup=after_generate_kb(regen_cb))
    # برای رجنریت مستقیم بدون پرسیدن موضوع دوباره، استیت رو نگه می‌داریم اما با همون موضوع
    await state.set_state(TextWriting.waiting_topic)


# ---------- هندلرها: فلو شخصی ----------

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
    await state.set_state(PersonalFlow.waiting_audio)
    await callback.message.edit_text(
        "اول فایل صوتی آهنگت رو بفرست (voice یا audio).\n"
        f"حجم حداکثر: {config.MAX_AUDIO_MB}MB"
    )
    await callback.answer()


@router.message(PersonalFlow.waiting_audio, F.audio | F.voice | F.document)
async def handle_audio(message: Message, state: FSMContext, bot: Bot):
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
    await state.set_state(PersonalFlow.waiting_lyrics)
    await waiting_msg.edit_text(
        "✅ صدا تحلیل شد:\n\n"
        f"{audio_summary_text(analysis)}\n\n"
        "حالا متن (لیریک) همین آهنگ رو به صورت تکست بفرست."
    )


@router.message(PersonalFlow.waiting_audio)
async def handle_audio_wrong_type(message: Message):
    await message.answer("لطفاً یه فایل صوتی (voice یا audio) بفرست.")


@router.message(PersonalFlow.waiting_lyrics, F.text)
async def handle_lyrics_text(message: Message, state: FSMContext):
    data = await state.get_data()
    audio_summary = data.get("audio_analysis", "")
    text_analysis = analyze_lyrics(message.text)
    text_summary = lyrics_summary_text(text_analysis)

    profile_summary = (
        f"[تحلیل صوتی آهنگ مرجع کاربر]\n{audio_summary}\n\n"
        f"[تحلیل ساختاری متن مرجع کاربر]\n{text_summary}\n\n"
        f"[نمونه واقعی متن کاربر برای یادگیری لحن]\n{message.text[:800]}"
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
    await state.set_state(PersonalFlow.waiting_topic)
    await callback.message.edit_text(
        "موضوع یا حس مدنظرت برای این متن چیه؟ (یا بنویس «آزاد»)"
    )
    await callback.answer()


@router.message(PersonalFlow.waiting_topic, F.text)
async def handle_pf_topic(message: Message, state: FSMContext):
    profile = await db.get_profile(message.from_user.id)
    topic = "" if message.text.strip() in ("آزاد", "ازاد") else message.text.strip()

    waiting_msg = await message.answer("⏳ دارم با فلوی خودت متن می‌نویسم و بعد یه دور ویرایش حرفه‌ای می‌زنم...")
    prompt = llm.build_personal_flow_prompt(profile, topic)
    try:
        lyrics = await llm.generate_text_pro(prompt)
    except Exception as e:
        await waiting_msg.edit_text(f"❌ خطا در تولید متن: {e}")
        return

    await waiting_msg.delete()
    await state.update_data(last_lyrics=lyrics, last_regen_cb="pf:generate")
    await message.answer(lyrics, reply_markup=after_generate_kb("pf:generate"))
    await state.set_state(PersonalFlow.waiting_topic)


@router.callback_query(F.data == "refine:last")
async def cb_refine_last(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_lyrics = data.get("last_lyrics")
    last_regen_cb = data.get("last_regen_cb", "menu:home")
    if not last_lyrics:
        await callback.answer("چیزی برای بهتر کردن پیدا نکردم، اول یه متن بساز.", show_alert=True)
        return

    await callback.answer("⏳ دارم بهترش می‌کنم...")
    try:
        improved = await llm.refine_text(last_lyrics)
    except Exception as e:
        await callback.message.answer(f"❌ خطا در بهبود متن: {e}")
        return

    await state.update_data(last_lyrics=improved)
    await callback.message.answer(improved, reply_markup=after_generate_kb(last_regen_cb))


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
