# bot_complete.py
import os
import asyncio
import re
import urllib.parse
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
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

from dateutil.relativedelta import relativedelta

from db import (
    init_db,
    buscar_usuario, inserir_usuario,
    inserir_cliente, listar_clientes, contar_clientes,
    buscar_cliente_por_id, deletar_cliente, atualizar_cliente
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
    pacote_personalizado = State()
    valor = State()
    valor_personalizado = State()
    vencimento = State()
    info = State()

class EditCliente(StatesGroup):
    aguardando = State()
    nome = State()
    telefone = State()
    pacote = State()
    pacote_personalizado = State()
    valor = State()
    valor_personalizado = State()
    vencimento = State()
    info = State()

class MsgCliente(StatesGroup):
    personalizada = State()  # armazena cid no state

# ---------------------- Helpers ----------------------
def normaliza_tel(v: str | None) -> str | None:
    if not v:
        return None
    return "".join(c for c in v if c.isdigit() or c == "+")

def wa_link(phone: str | None, text: str) -> str | None:
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return None
    return f"https://wa.me/{digits}?text={urllib.parse.quote_plus(text)}"

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
            return date(datetime.now().year, mth, d)
        except ValueError:
            return None
    return None

def fmt_moeda(v):
    return f"R$ {float(v):.2f}".replace(".", ",")

def fmt_cliente(c: dict) -> str:
    v = fmt_moeda(c["valor"]) if c.get("valor") is not None else "—"
    vc = c.get("vencimento")
    venc = vc
    if isinstance(vc, str):
        try:
            vdate = datetime.fromisoformat(vc).date()
            venc = vdate.strftime("%d/%m/%Y")
        except Exception:
            venc = vc
    elif isinstance(vc, date):
        venc = vc.strftime("%d/%m/%Y")
    else:
        venc = "—"
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

def clientes_list_kb(items, offset: int, limit: int, total: int):
    kb = InlineKeyboardBuilder()
    for c in items:
        kb.button(text=f"🔎 #{c['id']} • {c['nome'][:40]}", callback_data=f"cid:{c['id']}")
    kb.adjust(1)
    # navegação
    prev_off = max(offset - limit, 0)
    next_off = offset + limit
    nav = []
    if offset > 0:
        kb.button(text="⬅️", callback_data=f"pg:{prev_off}")
    if next_off < total:
        kb.button(text="➡️", callback_data=f"pg:{next_off}")
    kb.adjust(1)
    return kb.as_markup()

def cliente_menu_kb(cid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Editar", callback_data=f"edit:{cid}"),
         InlineKeyboardButton(text="🔄 Renovar plano", callback_data=f"renew:{cid}")],
        [InlineKeyboardButton(text="💬 Mensagens", callback_data=f"msg:{cid}")],
        [InlineKeyboardButton(text="🗑️ Excluir", callback_data=f"del:{cid}")],
    ])

def renew_menu_kb(cid: int, pacote: str | None):
    # mapeia pacote → meses
    meses = 1
    label = "Mensal"
    p = (pacote or "").lower()
    if "tri" in p:
        meses, label = 3, "Trimestral"
    elif "sem" in p:
        meses, label = 6, "Semestral"
    elif "anual" in p or "12" in p:
        meses, label = 12, "Anual"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔁 Próximo ciclo ({label})", callback_data=f"renewx:{cid}:{meses}")],
        [InlineKeyboardButton(text="🗓 Definir data", callback_data=f"renewd:{cid}")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cid:{cid}")]
    ])

def msg_menu_kb(cid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Lembrete pagamento", callback_data=f"msgp:{cid}:lembrete")],
        [InlineKeyboardButton(text="✍️ Mensagem personalizada", callback_data=f"msgp:{cid}:personalizada")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cid:{cid}")]
    ])

# ---------------------- Teclados persistentes ----------------------
def kb_main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Novo Cliente"), KeyboardButton(text="📋 Clientes")],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True,
        resize_keyboard=True,
        input_field_placeholder="Escolha uma opção…"
    )

PACOTE_LABELS = [
    "📅 Mensal", "🗓️ Trimestral", "🗓️ Semestral", "📆 Anual", "🛠️ Personalizado"
]
PACOTE_MAP = {
    "📅 Mensal": "Mensal",
    "🗓️ Trimestral": "Trimestral",
    "🗓️ Semestral": "Semestral",
    "📆 Anual": "Anual",
}
def kb_pacotes():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=PACOTE_LABELS[0]), KeyboardButton(text=PACOTE_LABELS[1])],
            [KeyboardButton(text=PACOTE_LABELS[2]), KeyboardButton(text=PACOTE_LABELS[3])],
            [KeyboardButton(text=PACOTE_LABELS[4])],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True,
        resize_keyboard=True,
        input_field_placeholder="Escolha um pacote…"
    )

VALORES_LABELS = [
    "💵 25,00", "💵 30,00", "💵 35
