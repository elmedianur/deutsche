#!/usr/bin/env python3
"""
Quiz Bot Pro - Simple Start Script
Run: python start.py
"""
import os
import sys

# Check Python version
if sys.version_info < (3, 10):
    print("[ERROR] Python 3.10+ kerak!")
    sys.exit(1)

# Check .env file
if not os.path.exists('.env'):
    print("[ERROR] .env fayl topilmadi!")
    print("\n[INFO] .env faylini yarating:")
    print("   cp .env.example .env")
    print("   nano .env  # BOT_TOKEN ni kiriting")
    sys.exit(1)

# Check BOT_TOKEN
from dotenv import load_dotenv
load_dotenv()

token = os.getenv('BOT_TOKEN')
if not token or token == 'your_bot_token_here':
    print("[ERROR] BOT_TOKEN kiritilmagan!")
    print("\n[INFO] .env faylida BOT_TOKEN ni to'ldiring:")
    print("   BOT_TOKEN=7123456789:AAHxxx...")
    sys.exit(1)

print("=" * 50)
print("[BOT] Quiz Bot Pro")
print("=" * 50)
print(f"[OK] Python: {sys.version_info.major}.{sys.version_info.minor}")
print(f"[OK] BOT_TOKEN: ...{token[-10:]}")

# Check dependencies
missing = []
try:
    import aiogram
    print(f"[OK] aiogram: {aiogram.__version__}")
except ImportError:
    missing.append("aiogram")

try:
    import sqlalchemy
    print(f"[OK] sqlalchemy: {sqlalchemy.__version__}")
except ImportError:
    missing.append("sqlalchemy")

try:
    import pydantic
    print(f"[OK] pydantic: {pydantic.__version__}")
except ImportError:
    missing.append("pydantic")

try:
    import aiosqlite
    print("[OK] aiosqlite")
except ImportError:
    missing.append("aiosqlite")

if missing:
    print(f"\n[ERROR] Kutubxonalar yo'q: {', '.join(missing)}")
    print("\n[INFO] O'rnating:")
    print("   pip install aiogram sqlalchemy aiosqlite pydantic pydantic-settings structlog python-dotenv")
    sys.exit(1)

print("=" * 50)
print("[START] Bot ishga tushmoqda...")
print("   Ctrl+C - to'xtatish")
print("=" * 50)

# Start bot
import asyncio
sys.path.insert(0, '.')

async def main():
    from src.bot import create_bot, create_dispatcher, register_handlers
    from src.bot import on_startup, on_shutdown

    bot = create_bot()
    dp = await create_dispatcher()
    register_handlers(dp, bot)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Get bot info
    me = await bot.get_me()
    print(f"\n[OK] Bot: @{me.username}")
    print(f"[OK] ID: {me.id}")
    print("\n[READY] Bot tayyor! Telegram'da /start buyrug'ini yuboring\n")

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[BYE] Bot to'xtatildi")
