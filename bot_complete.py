# bot_complete.py
import os
import asyncio
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import (
    init_db,
    buscar_usuario, inserir_usuario,
    inserir_cliente, listar_clientes, contar_clientes, buscar_cliente_por_id, deletar_cliente
)

# ---------------------- Estados (FSM) ----------------------
class CadastroUsuario(StatesGroup):
    nome = State()
    email = State()
    telefone = State()

class NovoCliente(StatesGroup):
    nome = State()
    telefone = State()
    pacote = State()
    valor = State()
    vencimento = State()
    info = State()

# ---------------------- Helpers ----------------------
def normaliza_tel(v: str | None) -> str | None:
    if not v:
        return None
    return "".join(c for c in v if c.isdigit() or c == "+")

def parse_valor(txt: str) -> Decimal | None:
    if not txt:
        return None
    s = re.sub(r"[^\d,.-]", "", txt).replace(".", "")
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def parse_vencimento(txt: str):
    """Retorna date (ou None). Aceita dd/mm/aaaa, dd/mm, aaaa-mm-dd, dd-mm-aaaa."""
    if not txt:
        return None
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})[\/\-](\d{1,2})$", txt)
    if m:
        d, mth = map(int, m.groups())
        try:
            return datetime(datetime.now().year, mth, d).date()
        except ValueError:
            return None
    return None

def fmt_moeda(v):
    return f"R$ {float(v):.2f}".replace(".", ",")

def fmt_cliente(c: dict) -> str:
    v = fmt_moeda(c["valor"]) if c.get("valor") is not None else "—"
    vc = c.get("vencimento")
    if isinstance(vc, str):
        venc = vc
    else:
        venc = vc.strftime("%d/%m/%Y") if vc else "—"
    return (
        f"<b>#{c['id']}</b> • {c.get('nome','—')}\n"
        f"📞 {c.get('telefone') or '—'} | 📦 {c.get('pacote') or '—'}\n"
        f"💰 {v} | 📅 {venc}\n"
        f"📝 {c.get('info') or '—'}"
    )

def pagina_kb(offset: int, limit: int, total: int):
    kb = InlineKeyboardBuilder()
    prev_off = max(offset - limit, 0)
    next_off = offset + limit
    if offset > 0:
        kb.button(text="⬅️ Anteriores", callback_data=f"pg:{prev_off}")
    if next_off < total:
        kb.button(text="Próximos ➡️", callback_data=f"pg:{next_off}")
    kb.adjust(2)
    return kb.as_markup()

def cliente_kb(cid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Detalhes", callback_data=f"cid:{cid}")],
        [InlineKeyboardButton(text="🗑️ Excluir", callback_data=f"del:{cid}")]
    ])

# Teclado persistente (principal)
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Novo Cliente"), KeyboardButton(text="📋 Clientes")],
        [KeyboardButton(text="❌ Cancelar")]
    ],
    is_persistent=True,
    resize_keyboard=True,
    input_field_placeholder="Escolha uma opção…"
)

# ---------------------- Boot ----------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Defina BOT_TOKEN no ambiente")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------------------- Handlers: Usuário ----------------------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    user = buscar_usuario(m.from_user.id)
    if user:
        await m.answer(
            f"👋 Olá, {user.get('nome') or m.from_user.first_name}! O que deseja fazer?",
            reply_markup=main_kb
        )
    else:
        await m.answer(
            "👋 Bem-vindo! Antes de usar, preciso do seu cadastro.\nQual é o seu <b>nome</b>?",
            reply_markup=main_kb
        )
        await state.set_state(CadastroUsuario.nome)

@dp.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(
        "<b>Comandos:</b>\n"
        "• /start — menu principal\n"
        "• /help — ajuda\n"
        "• /id 123 — detalhes do cliente por ID\n"
        "\nUse o teclado para ➕ Novo Cliente ou 📋 Clientes.",
        reply_markup=main_kb
    )

@dp.message(Command("id"))
async def cmd_id(m: Message, command: Command):
    if not command.args or not command.args.strip().isdigit():
        await m.answer("Uso: <code>/id 123</code>")
        return
    cid = int(command.args.strip())
    c = buscar_cliente_por_id(cid)
    if not c:
        await m.answer(f"Cliente #{cid} não encontrado.")
        return
    await m.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_kb(cid))

# Cadastro de usuário
@dp.message(CadastroUsuario.nome)
async def cad_nome(m: Message, state: FSMContext):
    nome = m.text.strip()
    if len(nome) < 2:
        await m.answer("Nome muito curto. Informe seu <b>nome</b> completo.")
        return
    await state.update_data(nome=nome)
    await m.answer("📧 Agora, seu <b>email</b>:")
    await state.set_state(CadastroUsuario.email)

@dp.message(CadastroUsuario.email)
async def cad_email(m: Message, state: FSMContext):
    email = m.text.strip()
    await state.update_data(email=email)
    await m.answer("📱 Por fim, seu <b>telefone</b> (com DDD):")
    await state.set_state(CadastroUsuario.telefone)

@dp.message(CadastroUsuario.telefone)
async def cad_tel(m: Message, state: FSMContext):
    tel = normaliza_tel(m.text)
    data = await state.update_data(telefone=tel)

    inserir_usuario(
        tg_id=m.from_user.id,
        nome=data["nome"],
        email=data["email"],
        telefone=data["telefone"] or ""
    )
    await state.clear()
    await m.answer("✅ Cadastro concluído! Use os botões abaixo.", reply_markup=main_kb)

# ---------------------- Handlers: Clientes ----------------------
# Iniciar cadastro
@dp.message(F.text.casefold() == "➕ novo cliente")
async def novo_cliente_start(m: Message, state: FSMContext):
    await m.answer("Vamos cadastrar um cliente.\nQual é o <b>nome</b>?", reply_markup=main_kb)
    await state.set_state(NovoCliente.nome)

@dp.message(NovoCliente.nome)
async def nc_nome(m: Message, state: FSMContext):
    nome = m.text.strip()
    if len(nome) < 2:
        await m.answer("Nome muito curto. Informe o <b>nome</b> completo.")
        return
    await state.update_data(nome=nome)
    await m.answer("📞 Informe o <b>telefone</b> (com DDD).")
    await state.set_state(NovoCliente.telefone)

@dp.message(NovoCliente.telefone)
async def nc_tel(m: Message, state: FSMContext):
    tel = normaliza_tel(m.text)
    if tel and (len(tel) < 10 or len(tel) > 16):
        await m.answer("Telefone inválido. Ex.: +55 11 99999-0000")
        return
    await state.update_data(telefone=tel)
    await m.answer("📦 Qual é o <b>pacote</b>? (ex.: Plano Mensal 50MB)")
    await state.set_state(NovoCliente.pacote)

@dp.message(NovoCliente.pacote)
async def nc_pacote(m: Message, state: FSMContext):
    pacote = m.text.strip() if m.text else None
    await state.update_data(pacote=pacote)
    await m.answer("💰 Qual é o <b>valor</b>? (ex.: 89,90)")
    await state.set_state(NovoCliente.valor)

@dp.message(NovoCliente.valor)
async def nc_valor(m: Message, state: FSMContext):
    valor = parse_valor(m.text)
    if valor is None:
        await m.answer("Valor inválido. Tente algo como <code>89,90</code>.")
        return
    await state.update_data(valor=float(valor))
    await m.answer("📅 Qual é a <b>data de vencimento</b>? (ex.: 10/09/2025 ou 10/09)")
    await state.set_state(NovoCliente.vencimento)

@dp.message(NovoCliente.vencimento)
async def nc_venc(m: Message, state: FSMContext):
    data_v = parse_vencimento(m.text)
    if data_v is None:
        await m.answer("Data inválida. Use <code>dd/mm/aaaa</code>, <code>dd/mm</code> ou <code>aaaa-mm-dd</code>.")
        return
    await state.update_data(vencimento=data_v.isoformat())
    await m.answer("📝 Outras informações (MAC, OTP etc.). Se não houver, digite <i>sem</i>.")
    await state.set_state(NovoCliente.info)

@dp.message(NovoCliente.info)
async def nc_info(m: Message, state: FSMContext):
    info = (m.text or "").strip()
    info = None if info.lower() == "sem" else info
    data = await state.update_data(info=info)

    cid = inserir_cliente(
        nome=data.get("nome"),
        telefone=data.get("telefone"),
        pacote=data.get("pacote"),
        valor=data.get("valor"),
        vencimento=data.get("vencimento"),
        info=data.get("info"),
    )

    await state.clear()
    resumo = {
        "id": cid,
        "nome": data.get("nome"),
        "telefone": data.get("telefone"),
        "pacote": data.get("pacote"),
        "valor": data.get("valor"),
        "vencimento": data.get("vencimento"),
        "info": data.get("info"),
    }
    await m.answer(f"✅ Cliente cadastrado com ID <b>#{cid}</b>.\n\n{fmt_cliente(resumo)}",
                   reply_markup=main_kb)

# Cancelar qualquer fluxo
@dp.message(F.text.casefold() == "❌ cancelar")
async def cancelar(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Operação cancelada.", reply_markup=main_kb)

# Listar clientes
@dp.message(F.text.casefold() == "📋 clientes")
async def ver_clientes(m: Message):
    total = contar_clientes()
    items = listar_clientes(limit=10, offset=0)
    if not items:
        await m.answer("Ainda não há clientes.", reply_markup=main_kb)
        return
    texto = "<b>Clientes (mais recentes):</b>\n\n" + "\n\n".join(
        f"#{c['id']} • {c['nome']} — {c.get('pacote') or '—'}" for c in items
    )
    await m.answer(texto, reply_markup=pagina_kb(0, 10, total))

@dp.callback_query(F.data.startswith("pg:"))
async def cb_pagina(cq: CallbackQuery):
    offset = int(cq.data.split(":")[1])
    total = contar_clientes()
    items = listar_clientes(limit=10, offset=offset)
    texto = "<b>Clientes:</b>\n\n" + ("\n\n".join(
        f"#{c['id']} • {c['nome']} — {c.get('pacote') or '—'}" for c in items
    ) if items else "Sem resultados.")
    await cq.message.edit_text(texto, reply_markup=pagina_kb(offset, 10, total))
    await cq.answer()

@dp.callback_query(F.data.startswith("cid:"))
async def cb_cliente(cq: CallbackQuery):
    cid = int(cq.data.split(":")[1])
    c = buscar_cliente_por_id(cid)
    if not c:
        await cq.answer("Cliente não encontrado", show_alert=True)
        return
    await cq.message.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_kb(cid))
    await cq.answer()

@dp.callback_query(F.data.startswith("del:"))
async def cb_del(cq: CallbackQuery):
    cid = int(cq.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❗ Confirmar exclusão", callback_data=f"delc:{cid}")],
        [InlineKeyboardButton(text="Cancelar", callback_data="noop")]
    ])
    await cq.message.answer(f"Tem certeza que deseja excluir o cliente #{cid}?", reply_markup=kb)
    await cq.answer()

@dp.callback_query(F.data == "noop")
async def cb_noop(cq: CallbackQuery):
    await cq.answer("Operação cancelada.")

@dp.callback_query(F.data.startswith("delc:"))
async def cb_del_confirm(cq: CallbackQuery):
    cid = int(cq.data.split(":")[1])
    deletar_cliente(cid)
    await cq.message.answer(f"🗑️ Cliente #{cid} excluído.", reply_markup=main_kb)
    await cq.answer()

# ---------------------- Main ----------------------
async def main():
    print("🚀 iniciando… limpando webhook e preparando DB")
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("✅ pronto. iniciando polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
