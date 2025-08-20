# bot_complete.py
import os
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from dotenv import load_dotenv

from db import init_db, buscar_usuario, inserir_usuario

# ---------- Estados do cadastro (FSM) ----------
class CadastroUsuario(StatesGroup):
    nome = State()
    email = State()
    telefone = State()

# ---------- Boot ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Defina BOT_TOKEN")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- Handlers ----------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    user = buscar_usuario(m.from_user.id)
    if user:
        await m.answer(f"👋 Olá, {user.get('nome') or m.from_user.first_name}! Você já está cadastrado.")
        return
    await m.answer("👋 Bem-vindo! Vamos fazer seu cadastro.\nQual é o seu <b>nome</b>?")
    await state.set_state(CadastroUsuario.nome)

@dp.message(CadastroUsuario.nome)
async def cadastro_nome(m: Message, state: FSMContext):
    await state.update_data(nome=m.text.strip())
    await m.answer("📧 Agora, seu <b>email</b>:")
    await state.set_state(CadastroUsuario.email)

@dp.message(CadastroUsuario.email)
async def cadastro_email(m: Message, state: FSMContext):
    await state.update_data(email=m.text.strip())
    await m.answer("📱 Por fim, seu <b>telefone</b> (com DDD):")
    await state.set_state(CadastroUsuario.telefone)

@dp.message(CadastroUsuario.telefone)
async def cadastro_telefone(m: Message, state: FSMContext):
    data = await state.update_data(telefone=m.text.strip())
    inserir_usuario(
        tg_id=m.from_user.id,
        nome=data["nome"],
        email=data["email"],
        telefone=data["telefone"]
    )
    await state.clear()
    await m.answer("✅ Cadastro concluído! Use /help para ver os comandos.")

# (opcional) handler de debug para confirmar que mensagens chegam — remova depois
@dp.message(F.text)
async def echo_debug(m: Message):
    await m.answer(f"Recebi: {m.text}")

# ---------- Main ----------
async def main():
    print("🚀 iniciando… limpando webhook e preparando DB")
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("✅ pronto. iniciando polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
