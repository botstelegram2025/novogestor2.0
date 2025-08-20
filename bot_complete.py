# bot_complete.py (trecho principal)
import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from db import init_db  # seu db Postgres
# ... (outros imports e handlers que você já tem)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Defina BOT_TOKEN")

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("👋 Olá! Estou online. Use /help para ver os comandos.")

# (debug) eco para confirmar recebimento de updates
@dp.message(F.text)
async def echo_debug(m: Message):
    # remova depois que tudo estiver OK
    await m.answer(f"Recebi: {m.text}")

async def main():
    print("🚀 iniciando… deletando webhook e iniciando DB")
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("✅ pronto. iniciando polling…")
    # allowed_updates ajuda o Telegram a entregar só o que você realmente usa
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
