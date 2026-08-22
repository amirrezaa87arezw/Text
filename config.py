# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# موتور LLM: "gemini" (رایگان و پیشنهادی)، "openai" یا "claude"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

DB_PATH = os.getenv("DB_PATH", "bot.db")

MAX_AUDIO_MB = 20
