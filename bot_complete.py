# bot_complete.py
import os
import asyncio
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime

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
    pacote_personalizado = State()
    valor = State()
    valor_personalizado = State()
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

# ---------------------- Teclados ----------------------
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
    "💵 25,00", "💵 30,00", "💵 35,00",
    "💵 40,00", "💵 45,00", "💵 50,00",
    "💵 60,00", "💵 70,00", "💵 75,00",
    "💵 90,00", "✍️ Outro valor"
]
def kb_valores():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=VALORES_LABELS[0]), KeyboardButton(text=VALORES_LABELS[1]), KeyboardButton(text=VALORES_LABELS[2])],
            [KeyboardButton(text=VALORES_LABELS[3]), KeyboardButton(text=VALORES_LABELS[4]), KeyboardButton(text=VALORES_LABELS[5])],
            [KeyboardButton(text=VALORES_LABELS[6]), KeyboardButton(text=VALORES_LABELS[7]), KeyboardButton(text=VALORES_LABELS[8])],
            [KeyboardButton(text=VALORES_LABELS[9]), KeyboardButton(text=VALORES_LABELS[10])],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True,
        resize_keyboard=True,
        input_field_placeholder="Escolha um valor…"
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
            reply_markup=kb_main()
        )
    else:
        await m.answer(
            "👋 Bem-vindo! Antes de usar, preciso do seu cadastro.\nQual é o seu <b>nome</b>?",
            reply_markup=kb_main()
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
        reply_markup=kb_main()
    )

@dp.message(Command("id"))
async def cmd_id(m: Message, command: CommandObject):
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
    await m.answer("📧 Agora, seu <b>email</b>:", reply_markup=kb_main())
    await state.set_state(CadastroUsuario.email)

@dp.message(CadastroUsuario.email)
async def cad_email(m: Message, state: FSMContext):
    email = m.text.strip()
    await state.update_data(email=email)
    await m.answer("📱 Por fim, seu <b>telefone</b> (com DDD):", reply_markup=kb_main())
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
    await m.answer("✅ Cadastro concluído! Use os botões abaixo.", reply_markup=kb_main())

# ---------------------- Handlers: Clientes ----------------------
@dp.message(F.text.casefold() == "➕ novo cliente")
async def novo_cliente_start(m: Message, state: FSMContext):
    await m.answer("Vamos cadastrar um cliente.\nQual é o <b>nome</b>?", reply_markup=kb_main())
    await state.set_state(NovoCliente.nome)

@dp.message(NovoCliente.nome)
async def nc_nome(m: Message, state: FSMContext):
    nome = m.text.strip()
    if len(nome) < 2:
        await m.answer("Nome muito curto. Informe o <b>nome</b> completo.")
        return
    await state.update_data(nome=nome)
    await m.answer("📞 Informe o <b>telefone</b> (com DDD).", reply_markup=kb_main())
    await state.set_state(NovoCliente.telefone)

@dp.message(NovoCliente.telefone)
async def nc_tel(m: Message, state: FSMContext):
    tel = normaliza_tel(m.text)
    if tel and (len(tel) < 10 or len(tel) > 16):
        await m.answer("Telefone inválido. Ex.: +55 11 99999-0000")
        return
    await state.update_data(telefone=tel)
    await m.answer("📦 Escolha um <b>pacote</b> ou toque em Personalizado:", reply_markup=kb_pacotes())
    await state.set_state(NovoCliente.pacote)

@dp.message(NovoCliente.pacote)
async def nc_pacote(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    low = txt.lower()
    # Personalizado → pede para digitar
    if "personalizado" in low:
        await m.answer("🛠️ Digite o <b>nome do pacote</b> desejado:", reply_markup=kb_main())
        await state.set_state(NovoCliente.pacote_personalizado)
        return
    # Se clicou num botão conhecido, mapeia para o rótulo limpo
    if txt in PACOTE_MAP:
        await state.update_data(pacote=PACOTE_MAP[txt])
    else:
        # Usuário digitou algo — aceita como pacote
        await state.update_data(pacote=txt if txt else None)
    await m.answer("💰 Escolha um <b>valor</b> ou toque em Outro valor:", reply_markup=kb_valores())
    await state.set_state(NovoCliente.valor)

@dp.message(NovoCliente.pacote_personalizado)
async def nc_pacote_perso(m: Message, state: FSMContext):
    pacote = m.text.strip()
    if not pacote:
        await m.answer("Informe um <b>nome de pacote</b> válido.")
        return
    await state.update_data(pacote=pacote)
    await m.answer("💰 Escolha um <b>valor</b> ou toque em Outro valor:", reply_markup=kb_valores())
    await state.set_state(NovoCliente.valor)

@dp.message(NovoCliente.valor)
async def nc_valor(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    if "outro valor" in txt.lower():
        await m.answer("✍️ Digite o <b>valor</b> (ex.: 89,90):", reply_markup=kb_main())
        await state.set_state(NovoCliente.valor_personalizado)
        return
    valor = parse_valor(txt)
    if valor is None:
        await m.answer("Valor inválido. Tente algo como <code>89,90</code> ou escolha um botão.")
        return
    await state.update_data(valor=float(valor))
    await m.answer("📅 Qual é a <b>data de vencimento</b>? (ex.: 10/09/2025 ou 10/09)", reply_markup=kb_main())
    await state.set_state(NovoCliente.vencimento)

@dp.message(NovoCliente.valor_personalizado)
async def nc_valor_perso(m: Message, state: FSMContext):
    valor = parse_valor(m.text)
    if valor is None:
        await m.answer("Valor inválido. Ex.: <code>89,90</code>.")
        return
    await state.update_data(valor=float(valor))
    await m.answer("📅 Qual é a <b>data de vencimento</b>? (ex.: 10/09/2025 ou 10/09)", reply_markup=kb_main())
    await state.set_state(NovoCliente.vencimento)

@dp.message(NovoCliente.vencimento)
async def nc_venc(m: Message, state: FSMContext):
    data_v = parse_vencimento(m.text)
    if data_v is None:
        await m.answer("Data inválida. Use <code>dd/mm/aaaa</code>, <code>dd/mm</code> ou <code>aaaa-mm-dd</code>.")
        return
    await state.update_data(vencimento=data_v.isoformat())
    await m.answer("📝 Outras informações (MAC, OTP etc.). Se não houver, digite <i>sem</i>.", reply_markup=kb_main())
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
                   reply_markup=kb_main())

# Cancelar qualquer fluxo
@dp.message(F.text.casefold() == "❌ cancelar")
async def cancelar(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Operação cancelada.", reply_markup=kb_main())

# Listar clientes
@dp.message(F.text.casefold() == "📋 clientes")
async def ver_clientes(m: Message):
    total = contar_clientes()
    items = listar_clientes(limit=10, offset=0)
