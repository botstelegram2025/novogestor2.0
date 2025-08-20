import os
from typing import Optional
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from db import init_db, inserir_cliente, listar_clientes, contar_clientes, buscar_cliente_por_id
from models import Cliente

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Defina BOT_TOKEN no .env")
ADMINS = {int(x) for x in os.getenv("ADMINS", "").replace(" ", "").split(",") if x}

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# ---------- Helpers ----------
def somente_admin(user_id: int) -> bool:
    return not ADMINS or (user_id in ADMINS)

def paginacao_keyboard(offset: int, limit: int, total: int):
    kb = InlineKeyboardBuilder()
    prev_off = max(offset - limit, 0)
    next_off = offset + limit
    if offset > 0:
        kb.button(text="⬅️ Anteriores", callback_data=f"page:{prev_off}")
    if next_off < total:
        kb.button(text="Próximos ➡️", callback_data=f"page:{next_off}")
    kb.adjust(2)
    return kb.as_markup()

def format_cliente(c: dict) -> str:
    tel = c.get("telefone") or "—"
    em = c.get("email") or "—"
    return f"<b>#{c['id']}</b> • {c['nome']}\n📞 {tel} | ✉️ {em}"

# ---------- Startup ----------
@dp.startup()
async def on_startup():
    init_db()

# ---------- Comandos ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Olá! Eu sou o seu Bot Gestor de Clientes.\n"
        "Use /help para ver os comandos."
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Comandos:</b>\n"
        "/add Nome;Telefone;Email — cadastra cliente rápido (Email e Telefone opcionais)\n"
        "/list — lista últimos clientes (paginado)\n"
        "/id 123 — mostra detalhes do cliente pelo ID\n"
        "/help — ajuda"
    )

@dp.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject):
    if not somente_admin(message.from_user.id):
        await message.answer("🚫 Você não tem permissão para cadastrar.")
        return

    if not command.args:
        await message.answer("Formato: <code>/add Nome;Telefone;Email</code>\nEx.: <code>/add Maria Silva;+55 11 99999-0000;maria@email.com</code>")
        return

    partes = [p.strip() for p in command.args.split(";")]
    nome: Optional[str] = partes[0] if len(partes) > 0 and partes[0] else None
    telefone: Optional[str] = partes[1] if len(partes) > 1 and partes[1] else None
    email: Optional[str] = partes[2] if len(partes) > 2 and partes[2] else None

    if not nome:
        await message.answer("❗️Informe ao menos o <b>Nome</b>. Formato: <code>/add Nome;Telefone;Email</code>")
        return

    try:
        cliente = Cliente(nome=nome, telefone=telefone, email=email)
    except Exception as e:
        await message.answer(f"Dados inválidos: <code>{e}</code>")
        return

    cid = inserir_cliente(cliente.nome, cliente.telefone, str(cliente.email) if cliente.email else None)
    await message.answer(f"✅ Cliente cadastrado com ID <b>#{cid}</b>.")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    total = contar_clientes()
    clientes = listar_clientes(limit=10, offset=0)
    if not clientes:
        await message.answer("Sem clientes cadastrados ainda. Use /add para inserir o primeiro.")
        return
    texto = "<b>Clientes (mais recentes):</b>\n\n" + "\n\n".join(format_cliente(c) for c in clientes)
    await message.answer(texto, reply_markup=paginacao_keyboard(offset=0, limit=10, total=total))

@dp.callback_query(F.data.startswith("page:"))
async def cb_page(query):
    try:
        offset = int(query.data.split(":")[1])
    except:
        offset = 0
    total = contar_clientes()
    clientes = listar_clientes(limit=10, offset=offset)
    texto = "<b>Clientes:</b>\n\n" + "\n\n".join(format_cliente(c) for c in clientes) if clientes else "Sem resultados nesta página."
    await query.message.edit_text(texto, reply_markup=paginacao_keyboard(offset=offset, limit=10, total=total))
    await query.answer()

@dp.message(Command("id"))
async def cmd_id(message: Message, command: CommandObject):
    if not command.args or not command.args.isdigit():
        await message.answer("Uso: <code>/id 123</code>")
        return
    cid = int(command.args)
    c = buscar_cliente_por_id(cid)
    if not c:
        await message.answer(f"Não encontrei o cliente #{cid}.")
        return
    await message.answer("🗂️ Detalhes do cliente:\n\n" + format_cliente(c))

# ---------- Execução ----------
def main():
    import asyncio
    from aiogram import F
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
