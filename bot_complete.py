# bot_complete.py
import os
import asyncio
import re
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

from db import (
    init_db,
    buscar_usuario, inserir_usuario,
    inserir_cliente, listar_clientes, contar_clientes, buscar_cliente_por_id, deletar_cliente,
    atualizar_cliente, renovar_vencimento
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
    aguardando_campo = State()
    nome = State()
    telefone = State()
    pacote = State()
    pacote_personalizado = State()
    valor = State()
    valor_personalizado = State()
    vencimento = State()
    info = State()

class MsgCliente(StatesGroup):
    personalizada = State()

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

def fmt_moeda(v) -> str:
    return f"R$ {float(v):.2f}".replace(".", ",")

def fmt_data(dv) -> str:
    if not dv:
        return "—"
    if isinstance(dv, str):
        try:
            return datetime.fromisoformat(dv).date().strftime("%d/%m/%Y")
        except ValueError:
            return dv
    if isinstance(dv, date):
        return dv.strftime("%d/%m/%Y")
    return str(dv)

def fmt_cliente(c: dict) -> str:
    v = fmt_moeda(c["valor"]) if c.get("valor") is not None else "—"
    venc = fmt_data(c.get("vencimento"))
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

def cliente_actions_kb(cid: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Editar", callback_data=f"cli:{cid}:edit"),
         InlineKeyboardButton(text="🔁 Renovar", callback_data=f"cli:{cid}:renew")],
        [InlineKeyboardButton(text="💬 Mensagem", callback_data=f"cli:{cid}:msg"),
         InlineKeyboardButton(text="🗑️ Excluir", callback_data=f"cli:{cid}:del")],
        [InlineKeyboardButton(text="⬅️ Voltar à lista", callback_data="list:back")]
    ])
    return kb

def edit_menu_kb(cid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Nome", callback_data=f"edit:{cid}:nome"),
         InlineKeyboardButton(text="📞 Telefone", callback_data=f"edit:{cid}:telefone")],
        [InlineKeyboardButton(text="📦 Pacote", callback_data=f"edit:{cid}:pacote"),
         InlineKeyboardButton(text="💰 Valor", callback_data=f"edit:{cid}:valor")],
        [InlineKeyboardButton(text="📅 Vencimento", callback_data=f"edit:{cid}:venc"),
         InlineKeyboardButton(text="📝 Info", callback_data=f"edit:{cid}:info")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")]
    ])

def renew_menu_kb(cid: int, pacote: str | None):
    # opções fixas; se tiver pacote conhecido, mostra "Usar pacote atual"
    row1 = [
        InlineKeyboardButton(text="Mensal +1M", callback_data=f"renew:{cid}:1"),
        InlineKeyboardButton(text="Trimestral +3M", callback_data=f"renew:{cid}:3")
    ]
    row2 = [
        InlineKeyboardButton(text="Semestral +6M", callback_data=f"renew:{cid}:6"),
        InlineKeyboardButton(text="Anual +12M", callback_data=f"renew:{cid}:12")
    ]
    rows = [row1, row2]
    if pacote and pacote.lower() in {"mensal", "trimestral", "semestral", "anual"}:
        rows.insert(0, [InlineKeyboardButton(text=f"Usar pacote atual ({pacote})", callback_data=f"renew:{cid}:auto")])
    rows.append([InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def msg_menu_kb(cid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Cobrança", callback_data=f"msg:{cid}:cobranca"),
         InlineKeyboardButton(text="📦 Renovação", callback_data=f"msg:{cid}:renovacao")],
        [InlineKeyboardButton(text="✍️ Personalizada", callback_data=f"msg:{cid}:perso")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")]
    ])

# ---------------------- Teclados de resposta ----------------------
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

PACOTE_LABELS = ["📅 Mensal", "🗓️ Trimestral", "🗓️ Semestral", "📆 Anual", "🛠️ Personalizado"]
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
    await m.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_actions_kb(cid))

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

# ---------------------- Handlers: Clientes (cadastro guiado) ----------------------
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
    if "personalizado" in txt.lower():
        await m.answer("🛠️ Digite o <b>nome do pacote</b> desejado:", reply_markup=kb_main())
        await state.set_state(NovoCliente.pacote_personalizado)
        return
    if txt in PACOTE_MAP:
        await state.update_data(pacote=PACOTE_MAP[txt])
    else:
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
    resumo = {"id": cid, **data}
    await m.answer(f"✅ Cliente cadastrado com ID <b>#{cid}</b>.\n\n{fmt_cliente(resumo)}",
                   reply_markup=kb_main())

# ---------------------- Handlers: Clientes (listar/ações) ----------------------
@dp.message(F.text.casefold() == "📋 clientes")
async def ver_clientes(m: Message):
    total = contar_clientes()
    items = listar_clientes(limit=10, offset=0)
    if not items:
        await m.answer("Ainda não há clientes.", reply_markup=kb_main())
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

@dp.callback_query(F.data == "list:back")
async def cb_list_back(cq: CallbackQuery):
    total = contar_clientes()
    items = listar_clientes(limit=10, offset=0)
    texto = "<b>Clientes (mais recentes):</b>\n\n" + ("\n\n".join(
        f"#{c['id']} • {c['nome']} — {c.get('pacote') or '—'}" for c in items
    ) if items else "Sem resultados.")
    await cq.message.edit_text(texto, reply_markup=pagina_kb(0, 10, total))
    await cq.answer()

@dp.callback_query(F.data.startswith("cid:"))
async def cb_cliente_view_legacy(cq: CallbackQuery):
    # compat com versões anteriores; redireciona para novo padrão
    cid = int(cq.data.split(":")[1])
    await cb_cli_view(cq, cid)

@dp.callback_query(F.data.startswith("cli:"))
async def cb_cli_router(cq: CallbackQuery):
    # Formatos: cli:<cid>:view|edit|renew|msg|del
    _, cid, action = cq.data.split(":")
    cid = int(cid)
    if action == "view":
        await cb_cli_view(cq, cid)
    elif action == "edit":
        c = buscar_cliente_por_id(cid)
        if not c:
            await cq.answer("Cliente não encontrado", show_alert=True); return
        await cq.message.answer(f"✏️ Editar cliente #{cid}:\n\n{fmt_cliente(c)}", reply_markup=edit_menu_kb(cid))
        await cq.answer()
    elif action == "renew":
        c = buscar_cliente_por_id(cid)
        if not c:
            await cq.answer("Cliente não encontrado", show_alert=True); return
        await cq.message.answer(
            f"🔁 Renovar plano do cliente #{cid}:\n\n{fmt_cliente(c)}",
            reply_markup=renew_menu_kb(cid, c.get("pacote"))
        )
        await cq.answer()
    elif action == "msg":
        c = buscar_cliente_por_id(cid)
        if not c:
            await cq.answer("Cliente não encontrado", show_alert=True); return
        await cq.message.answer(
            f"💬 Mensagem rápida para cliente #{cid} ({c['nome']}):",
            reply_markup=msg_menu_kb(cid)
        )
        await cq.answer()
    elif action == "del":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❗ Confirmar exclusão", callback_data=f"delc:{cid}")],
            [InlineKeyboardButton(text="Cancelar", callback_data=f"cli:{cid}:view")]
        ])
        await cq.message.answer(f"Tem certeza que deseja excluir o cliente #{cid}?", reply_markup=kb)
        await cq.answer()

async def cb_cli_view(cq: CallbackQuery, cid: int):
    c = buscar_cliente_por_id(cid)
    if not c:
        await cq.answer("Cliente não encontrado", show_alert=True); return
    await cq.message.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_actions_kb(cid))
    await cq.answer()

@dp.callback_query(F.data.startswith("delc:"))
async def cb_del_confirm(cq: CallbackQuery):
    cid = int(cq.data.split(":")[1])
    deletar_cliente(cid)
    await cq.message.answer(f"🗑️ Cliente #{cid} excluído.", reply_markup=kb_main())
    await cq.answer()

# ---------------------- Editar Cliente ----------------------
@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit_select(cq: CallbackQuery, state: FSMContext):
    # edit:<cid>:<campo>
    _, cid, campo = cq.data.split(":")
    cid = int(cid)
    await state.update_data(edit_cid=cid)
    if campo == "nome":
        await state.set_state(EditCliente.nome)
        await cq.message.answer("Informe o <b>novo nome</b>:", reply_markup=kb_main()); await cq.answer(); return
    if campo == "telefone":
        await state.set_state(EditCliente.telefone)
        await cq.message.answer("Informe o <b>novo telefone</b>:", reply_markup=kb_main()); await cq.answer(); return
    if campo == "pacote":
        await state.set_state(EditCliente.pacote)
        await cq.message.answer("Escolha o <b>pacote</b> (ou Personalizado):", reply_markup=kb_pacotes()); await cq.answer(); return
    if campo == "valor":
        await state.set_state(EditCliente.valor)
        await cq.message.answer("Escolha o <b>valor</b> (ou Outro valor):", reply_markup=kb_valores()); await cq.answer(); return
    if campo == "venc":
        await state.set_state(EditCliente.vencimento)
        await cq.message.answer("Informe a <b>nova data de vencimento</b> (dd/mm/aaaa):", reply_markup=kb_main()); await cq.answer(); return
    if campo == "info":
        await state.set_state(EditCliente.info)
        await cq.message.answer("Digite as <b>informações</b> (MAC, OTP etc.):", reply_markup=kb_main()); await cq.answer(); return

@dp.message(EditCliente.nome)
async def edit_nome(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    nome = m.text.strip()
    atualizar_cliente(cid, nome=nome)
    await state.clear()
    await m.answer("✅ Nome atualizado.")
@dp.message(EditCliente.telefone)
async def edit_tel(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    tel = normaliza_tel(m.text)
    atualizar_cliente(cid, telefone=tel)
    await state.clear()
    await m.answer("✅ Telefone atualizado.")
@dp.message(EditCliente.pacote)
async def edit_pacote(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    txt = (m.text or "").strip()
    if "personalizado" in txt.lower():
        await state.set_state(EditCliente.pacote_personalizado)
        await m.answer("🛠️ Digite o <b>nome do pacote</b>:", reply_markup=kb_main())
        return
    pacote = PACOTE_MAP.get(txt, txt)
    atualizar_cliente(cid, pacote=pacote)
    await state.clear()
    await m.answer("✅ Pacote atualizado.")
@dp.message(EditCliente.pacote_personalizado)
async def edit_pacote_perso(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    pacote = m.text.strip()
    atualizar_cliente(cid, pacote=pacote)
    await state.clear()
    await m.answer("✅ Pacote atualizado.")
@dp.message(EditCliente.valor)
async def edit_valor(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    txt = (m.text or "").strip()
    if "outro valor" in txt.lower():
        await state.set_state(EditCliente.valor_personalizado)
        await m.answer("✍️ Digite o <b>valor</b> (ex.: 89,90):", reply_markup=kb_main())
        return
    valor = parse_valor(txt)
    if valor is None:
        await m.answer("Valor inválido. Escolha um botão ou digite ex.: 89,90.")
        return
    atualizar_cliente(cid, valor=float(valor))
    await state.clear()
    await m.answer("✅ Valor atualizado.")
@dp.message(EditCliente.valor_personalizado)
async def edit_valor_perso(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    valor = parse_valor(m.text)
    if valor is None:
        await m.answer("Valor inválido. Ex.: 89,90.")
        return
    atualizar_cliente(cid, valor=float(valor))
    await state.clear()
    await m.answer("✅ Valor atualizado.")
@dp.message(EditCliente.vencimento)
async def edit_venc(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    d = parse_vencimento(m.text)
    if not d:
        await m.answer("Data inválida. Use dd/mm/aaaa, dd/mm ou aaaa-mm-dd.")
        return
    atualizar_cliente(cid, vencimento=d.isoformat())
    await state.clear()
    await m.answer("✅ Vencimento atualizado.")
@dp.message(EditCliente.info)
async def edit_info(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid")
    info = (m.text or "").strip()
    atualizar_cliente(cid, info=None if info.lower() == "sem" else info)
    await state.clear()
    await m.answer("✅ Informações atualizadas.")

# ---------------------- Renovar Plano ----------------------
PACOTE_TO_MONTHS = {"mensal": 1, "trimestral": 3, "semestral": 6, "anual": 12}

@dp.callback_query(F.data.startswith("renew:"))
async def cb_renew(cq: CallbackQuery):
    # renew:<cid>:<months|auto>
    _, cid, opt = cq.data.split(":")
    cid = int(cid)
    c = buscar_cliente_por_id(cid)
    if not c:
        await cq.answer("Cliente não encontrado", show_alert=True); return

    if opt == "auto":
        pacote = (c.get("pacote") or "").lower()
        months = PACOTE_TO_MONTHS.get(pacote)
        if not months:
            await cq.answer("Pacote não reconhecido. Escolha 1/3/6/12 meses.", show_alert=True); return
    else:
        months = int(opt)

    new_date = renovar_vencimento(cid, months)
    await cq.message.answer(
        f"🔁 Renovado!\nCliente: <b>{c['nome']}</b>\nNovo vencimento: <b>{fmt_data(new_date)}</b>",
        reply_markup=cliente_actions_kb(cid)
    )
    await cq.answer()

# ---------------------- Mensagens Rápidas ----------------------
def render_msg(template: str, c: dict) -> str:
    valor = fmt_moeda(c["valor"]) if c.get("valor") is not None else "—"
    venc = fmt_data(c.get("vencimento"))
    return template.format(
        nome=c.get("nome", ""),
        pacote=c.get("pacote", "seu plano"),
        valor=valor,
        vencimento=venc,
        telefone=c.get("telefone", "")
    )

@dp.callback_query(F.data.startswith("msg:"))
async def cb_msg_menu(cq: CallbackQuery, state: FSMContext):
    # msg:<cid>:cobranca|renovacao|perso
    _, cid, kind = cq.data.split(":")
    cid = int(cid)
    c = buscar_cliente_por_id(cid)
    if not c:
        await cq.answer("Cliente não encontrado", show_alert=True); return

    if kind == "cobranca":
        tpl = ("Olá {nome}! 👋\n"
               "Lembramos que a fatura do plano {pacote} no valor de {valor} "
               "vence em {vencimento}. Para manter o serviço ativo, realize o pagamento até a data. "
               "Qualquer dúvida, estou à disposição. ✅")
        await cq.message.answer(render_msg(tpl, c))
        await cq.answer(); return

    if kind == "renovacao":
        tpl = ("Olá {nome}! 👋\n"
               "Seu plano {pacote} com valor {valor} está com vencimento em {vencimento}. "
               "Podemos confirmar a renovação? Responda por aqui. 🔁")
        await cq.message.answer(render_msg(tpl, c))
        await cq.answer(); return

    if kind == "perso":
        await state.update_data(msg_cid=cid)
        await state.set_state(MsgCliente.personalizada)
        await cq.message.answer(
            "✍️ Digite a mensagem. Você pode usar variáveis: "
            "<code>{nome}</code>, <code>{pacote}</code>, <code>{valor}</code>, <code>{vencimento}</code>, <code>{telefone}</code>.",
        )
        await cq.answer(); return

@dp.message(MsgCliente.personalizada)
async def msg_personalizada(m: Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get("msg_cid")
    c = buscar_cliente_por_id(int(cid))
    if not c:
        await state.clear()
        await m.answer("Cliente não encontrado.")
        return
    text = render_msg(m.text, c)
    await state.clear()
    await m.answer(text)

# ---------------------- Cancelar ----------------------
@dp.message(F.text.casefold() == "❌ cancelar")
async def cancelar(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Operação cancelada.", reply_markup=kb_main())

# ---------------------- Main ----------------------
async def main():
    print("🚀 iniciando… limpando webhook e preparando DB")
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("✅ pronto. iniciando polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
