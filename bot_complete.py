# bot_complete.py
import os
import asyncio
import re
import base64
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, BufferedInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import requests

from db import (
    init_db,
    buscar_usuario, inserir_usuario,
    inserir_cliente, listar_clientes, contar_clientes, buscar_cliente_por_id, deletar_cliente,
    atualizar_cliente, renovar_vencimento,
    list_templates, get_template, update_template, reset_template,
    get_setting, set_setting,
    add_wa_log, list_wa_logs, count_wa_logs
)

# ---------------------- Config ----------------------
DUE_SOON_DAYS = 5
TZ_NAME = os.getenv("TZ", "America/Sao_Paulo")
WA_API_BASE = os.getenv("WA_API_BASE")

# ---------------------- Estados (FSM) ----------------------
class CadastroUsuario(StatesGroup):
    nome = State()
    email = State()
    telefone = State()

class NovoCliente(StatesGroup):
    nome = State(); telefone = State()
    pacote = State(); pacote_personalizado = State()
    valor = State(); valor_personalizado = State()
    vencimento = State(); info = State()

class EditCliente(StatesGroup):
    nome = State(); telefone = State()
    pacote = State(); pacote_personalizado = State()
    valor = State(); valor_personalizado = State()
    vencimento = State(); info = State()

class MsgCliente(StatesGroup):
    personalizada = State()

class EditTemplate(StatesGroup):
    waiting_body = State()

class ScheduleWA(StatesGroup):
    waiting_datetime = State()  # dd/mm/aaaa HH:MM

class SchedConfig(StatesGroup):
    waiting_times = State()     # "09:00,14:30,18:00"

# ---------------------- Helpers ----------------------
def normaliza_tel(v: str | None) -> str | None:
    if not v: return None
    return "".join(c for c in v if c.isdigit() or c == "+")

def parse_valor(txt: str) -> Decimal | None:
    if not txt: return None
    s = re.sub(r"[^\d,.-]", "", txt).replace(".", "").replace(",", ".")
    try: return Decimal(s)
    except InvalidOperation: return None

def parse_vencimento(txt: str):
    if not txt: return None
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"):
        try: return datetime.strptime(txt, fmt).date()
        except ValueError: pass
    m = re.match(r"^(\d{1,2})[\/\-](\d{1,2})$", txt)
    if m:
        d, mth = map(int, m.groups())
        try: return datetime(datetime.now().year, mth, d).date()
        except ValueError: return None
    return None

def to_date(dv) -> date | None:
    if not dv: return None
    if isinstance(dv, date): return dv
    if isinstance(dv, str):
        try: return datetime.fromisoformat(dv).date()
        except ValueError: return None
    return None

def due_dot(dv) -> str:
    d = to_date(dv); today = date.today()
    if d is None: return "🟡"
    if d < today: return "🔴"
    if d <= today + timedelta(days=DUE_SOON_DAYS): return "🟡"
    return "🟢"

def fmt_moeda(v) -> str:
    return f"R$ {float(v):.2f}".replace(".", ",")

def fmt_data(dv) -> str:
    if not dv: return "—"
    if isinstance(dv, str):
        try: return datetime.fromisoformat(dv).date().strftime("%d/%m/%Y")
        except ValueError: return dv
    if isinstance(dv, date): return dv.strftime("%d/%m/%Y")
    return str(dv)

def fmt_cliente(c: dict) -> str:
    v = fmt_moeda(c["valor"]) if c.get("valor") is not None else "—"
    venc = fmt_data(c.get("vencimento")); dot = due_dot(c.get("vencimento"))
    return (
        f"{dot} <b>#{c['id']}</b> • {c.get('nome','—')}\n"
        f"📞 {c.get('telefone') or '—'} | 📦 {c.get('pacote') or '—'}\n"
        f"💰 {v} | 📅 {venc}\n"
        f"📝 {c.get('info') or '—'}"
    )

def trim(text: str, limit: int = 40) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else (text[:limit-1] + "…")

# ------------ Ordenação + Filtros da lista ------------
FILTER_LABELS = {"all": "♻️ Todos", "overdue": "🔴 Vencidos", "soon": "🟡 Próx. 3 dias"}

def _sort_clients_by_due(items: list[dict]) -> list[dict]:
    far_future = date(9999, 12, 31)
    def key(c: dict):
        d = to_date(c.get("vencimento")) or far_future
        return (d, c.get("id", 0))
    return sorted(items, key=key)

def _apply_filter(items: list[dict], flt: str) -> list[dict]:
    today = date.today()
    if flt == "overdue":
        return [c for c in items if (d := to_date(c.get("vencimento"))) and d < today]
    if flt == "soon":
        lim = today + timedelta(days=3)
        return [c for c in items if (d := to_date(c.get("vencimento"))) and today <= d <= lim]
    return items

def _get_clients_view(flt: str, offset: int, limit: int) -> tuple[list[dict], int]:
    total = contar_clientes() or 0
    if total == 0: return [], 0
    items = listar_clientes(limit=total, offset=0)
    items = _apply_filter(_sort_clients_by_due(items), flt)
    total_filtered = len(items)
    page_items = items[offset: offset + limit]
    return page_items, total_filtered

def clientes_inline_kb(offset: int, limit: int, total: int, items: list[dict], current_filter: str) -> InlineKeyboardMarkup:
    rows = []
    # Barra de filtro
    for key in ("all", "overdue", "soon"):
        selected = "• " if key == current_filter else ""
        rows.append([InlineKeyboardButton(text=f"{selected}{FILTER_LABELS[key]}", callback_data=f"list:filter:{key}")])
    # Itens
    for c in items:
        label = f"{due_dot(c.get('vencimento'))} {trim(c.get('nome','(sem nome)'), 38)} — {fmt_data(c.get('vencimento'))}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cli:{c['id']}:view")])
    # Navegação
    nav = []
    if offset > 0:
        prev_off = max(offset - limit, 0)
        nav.append(InlineKeyboardButton(text="⬅️ Anteriores", callback_data=f"list:page:{prev_off}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton(text="Próximos ➡️", callback_data=f"list:page:{offset+limit}"))
    if nav: rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cliente_actions_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Editar", callback_data=f"cli:{cid}:edit"),
         InlineKeyboardButton(text="🔁 Renovar", callback_data=f"cli:{cid}:renew")],
        [InlineKeyboardButton(text="💬 Mensagem", callback_data=f"cli:{cid}:msg"),
         InlineKeyboardButton(text="🗑️ Excluir", callback_data=f"cli:{cid}:del")],
        [InlineKeyboardButton(text="⬅️ Voltar à lista", callback_data="list:page:0")]
    ])

def edit_menu_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Nome", callback_data=f"edit:{cid}:nome"),
         InlineKeyboardButton(text="📞 Telefone", callback_data=f"edit:{cid}:telefone")],
        [InlineKeyboardButton(text="📦 Pacote", callback_data=f"edit:{cid}:pacote"),
         InlineKeyboardButton(text="💰 Valor", callback_data=f"edit:{cid}:valor")],
        [InlineKeyboardButton(text="📝 Informações", callback_data=f"edit:{cid}:info"),
         InlineKeyboardButton(text="📅 Vencimento", callback_data=f"edit:{cid}:venc")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")]
    ])

def renew_menu_kb(cid: int, pacote: str | None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Mensal +1M", callback_data=f"renew:{cid}:1"),
         InlineKeyboardButton(text="Trimestral +3M", callback_data=f"renew:{cid}:3")],
        [InlineKeyboardButton(text="Semestral +6M", callback_data=f"renew:{cid}:6"),
         InlineKeyboardButton(text="Anual +12M", callback_data=f"renew:{cid}:12")]
    ]
    if pacote and pacote.lower() in {"mensal", "trimestral", "semestral", "anual"}:
        rows.insert(0, [InlineKeyboardButton(text=f"Usar pacote atual ({pacote})", callback_data=f"renew:{cid}:auto")])
    rows.append([InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# --------- TEMPLATES: menus ----------
TPL_LABELS = {
    "AUTO": "✨ Sugerir automaticamente",
    "D2": "🧾 2 dias antes",
    "D1": "🧾 1 dia antes",
    "D0": "🧾 Hoje (vencimento)",
    "DA1": "🧾 1 dia após",
    "RENOV": "🔁 Renovação",
    "OUTRO": "🧰 Outro",
}
def msg_template_menu_kb(cid: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=TPL_LABELS["AUTO"], callback_data=f"tplmsg:{cid}:AUTO")],
        [InlineKeyboardButton(text=TPL_LABELS["D2"], callback_data=f"tplmsg:{cid}:D2"),
         InlineKeyboardButton(text=TPL_LABELS["D1"], callback_data=f"tplmsg:{cid}:D1")],
        [InlineKeyboardButton(text=TPL_LABELS["D0"], callback_data=f"tplmsg:{cid}:D0"),
         InlineKeyboardButton(text=TPL_LABELS["DA1"], callback_data=f"tplmsg:{cid}:DA1")],
        [InlineKeyboardButton(text=TPL_LABELS["RENOV"], callback_data=f"tplmsg:{cid}:RENOV"),
         InlineKeyboardButton(text=TPL_LABELS["OUTRO"], callback_data=f"tplmsg:{cid}:OUTRO")],
        [InlineKeyboardButton(text="✍️ Personalizada", callback_data=f"msg:{cid}:perso")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# --------- WhatsApp: menu principal ----------
def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Novo Cliente"), KeyboardButton(text="📋 Clientes")],
            [KeyboardButton(text="📲 WhatsApp"), KeyboardButton(text="🧩 Templates")],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True, resize_keyboard=True,
        input_field_placeholder="Escolha uma opção…"
    )

def wa_menu_kb(sched_enabled: bool) -> InlineKeyboardMarkup:
    status_text = "🟢 ON" if sched_enabled else "🔴 OFF"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Status", callback_data="wa:status"),
         InlineKeyboardButton(text="🧩 QR Code", callback_data="wa:qr")],
        [InlineKeyboardButton(text="🧾 Logs", callback_data="wa:logs:0"),
         InlineKeyboardButton(text="🧹 Limpar sessões", callback_data="wa:cleanup")],
        [InlineKeyboardButton(text=f"🗓️ Agendador: {status_text}", callback_data="wa:sched:toggle"),
         InlineKeyboardButton(text="⏱️ Horários", callback_data="wa:sched:times")]
    ])

PACOTE_LABELS = ["📅 Mensal", "🗓️ Trimestral", "🗓️ Semestral", "📆 Anual", "🛠️ Personalizado"]
PACOTE_MAP = {"📅 Mensal":"Mensal","🗓️ Trimestral":"Trimestral","🗓️ Semestral":"Semestral","📆 Anual":"Anual"}
def kb_pacotes() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=PACOTE_LABELS[0]), KeyboardButton(text=PACOTE_LABELS[1])],
            [KeyboardButton(text=PACOTE_LABELS[2]), KeyboardButton(text=PACOTE_LABELS[3])],
            [KeyboardButton(text=PACOTE_LABELS[4])],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True, resize_keyboard=True,
        input_field_placeholder="Escolha um pacote…"
    )

VALORES_LABELS = ["💵 25,00","💵 30,00","💵 35,00","💵 40,00","💵 45,00","💵 50,00","💵 60,00","💵 70,00","💵 75,00","💵 90,00","✍️ Outro valor"]
def kb_valores() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=VALORES_LABELS[0]), KeyboardButton(text=VALORES_LABELS[1]), KeyboardButton(text=VALORES_LABELS[2])],
            [KeyboardButton(text=VALORES_LABELS[3]), KeyboardButton(text=VALORES_LABELS[4]), KeyboardButton(text=VALORES_LABELS[5])],
            [KeyboardButton(text=VALORES_LABELS[6]), KeyboardButton(text=VALORES_LABELS[7]), KeyboardButton(text=VALORES_LABELS[8])],
            [KeyboardButton(text=VALORES_LABELS[9]), KeyboardButton(text=VALORES_LABELS[10])],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        is_persistent=True, resize_keyboard=True,
        input_field_placeholder="Escolha um valor…"
    )

# ---------------------- Boot ----------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: raise RuntimeError("Defina BOT_TOKEN no ambiente")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------------------- WhatsApp microserviço ----------------------
def wa_format_to_jid(phone: str | None) -> str | None:
    if not phone: return None
    p = "".join(ch for ch in phone if ch.isdigit())
    if p.startswith("0"): p = p.lstrip("0")
    if not p.startswith("55") and not (phone or "").startswith("+"):
        p = "55" + p
    return p

def wa_send_now(to_phone: str, text: str) -> tuple[bool, str]:
    if not WA_API_BASE: return False, "WA_API_BASE não configurado"
    try:
        r = requests.post(f"{WA_API_BASE}/send", json={"to": to_phone, "text": text}, timeout=20)
        if r.status_code == 200: return True, "Enviado com sucesso"
        return False, f"Erro {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Falha ao conectar: {e}"

def wa_schedule_at(to_phone: str, text: str, dt_iso_utc: str) -> tuple[bool, str]:
    if not WA_API_BASE: return False, "WA_API_BASE não configurado"
    try:
        r = requests.post(f"{WA_API_BASE}/schedule", json={"to": to_phone, "text": text, "send_at": dt_iso_utc}, timeout=20)
        if r.status_code == 200: return True, "Agendado com sucesso"
        return False, f"Erro {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Falha ao conectar: {e}"

def wa_get_health() -> tuple[bool, dict | None, str | None]:
    if not WA_API_BASE: return False, None, "WA_API_BASE não configurado"
    try:
        r = requests.get(f"{WA_API_BASE}/health", timeout=10)
        if r.status_code != 200: return False, None, f"HTTP {r.status_code}"
        return True, r.json(), None
    except Exception as e:
        return False, None, str(e)

def wa_get_qr() -> tuple[bool, dict | None, str | None]:
    if not WA_API_BASE: return False, None, "WA_API_BASE não configurado"
    try:
        r = requests.get(f"{WA_API_BASE}/qr", timeout=15)
        if r.status_code == 200: return True, r.json(), None
        return False, None, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, None, str(e)

def wa_cleanup_sessions() -> tuple[bool, str]:
    if not WA_API_BASE: return False, "WA_API_BASE não configurado"
    try:
        r = requests.post(f"{WA_API_BASE}/cleanup", timeout=20)
        if r.status_code == 200: return True, "Sessões antigas limpas."
        if r.status_code == 404:
            r2 = requests.post(f"{WA_API_BASE}/logout", timeout=20)
            if r2.status_code == 200: return True, "Conexões desconectadas."
        return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Falha ao conectar: {e}"

def parse_br_datetime(s: str) -> datetime | None:
    s = s.strip()
    try:
        dt_naive = datetime.strptime(s, "%d/%m/%Y %H:%M")
        return dt_naive.replace(tzinfo=ZoneInfo(TZ_NAME))
    except ValueError:
        return None

def _send_qr_image_to_telegram(m: Message, data_url: str):
    try: _, b64 = data_url.split(",", 1)
    except ValueError: return False
    raw = base64.b64decode(b64)
    file = BufferedInputFile(raw, filename="wa_qr.png")
    asyncio.create_task(m.answer_photo(file, caption="Escaneie este QR no WhatsApp para conectar."))
    return True

# ---------------------- Handlers: Usuário ----------------------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    user = buscar_usuario(m.from_user.id)
    if user:
        await m.answer(f"👋 Olá, {user.get('nome') or m.from_user.first_name}! O que deseja fazer?", reply_markup=kb_main())
    else:
        await m.answer("👋 Bem-vindo! Antes de usar, preciso do seu cadastro.\nQual é o seu <b>nome</b>?", reply_markup=kb_main())
        await state.set_state(CadastroUsuario.nome)

@dp.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(
        "<b>Comandos:</b>\n"
        "• /start — menu principal\n"
        "• /help — ajuda\n"
        "• /templates — gerenciar templates\n"
        "• /wa — utilidades WhatsApp\n"
        "• /id 123 — detalhes do cliente por ID\n",
        reply_markup=kb_main()
    )

# ====== Menu WhatsApp ======
def _sched_enabled() -> bool:
    return (get_setting("scheduler_enabled", "1") or "1") == "1"

def _sched_times() -> list[str]:
    raw = get_setting("schedule_times", "09:00,18:00") or "09:00,18:00"
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    valid = []
    for p in parts:
        try:
            datetime.strptime(p, "%H:%M")
            valid.append(p)
        except ValueError:
            continue
    return valid or ["09:00"]

def _times_human() -> str:
    return ", ".join(_sched_times())

@dp.message(Command("wa"))
@dp.message(F.text.casefold() == "📲 whatsapp")
async def cmd_wa(m: Message):
    await m.answer("📲 <b>WhatsApp • Baileys</b>\nEscolha uma ação:", reply_markup=wa_menu_kb(_sched_enabled()))

@dp.callback_query(F.data == "wa:status")
async def cb_wa_status(cq: CallbackQuery):
    if not WA_API_BASE:
        await cq.message.answer("❌ <b>WhatsApp:</b> WA_API_BASE não configurado.")
        await cq.answer(); return
    ok, health, err = wa_get_health()
    if not ok:
        await cq.message.answer(f"❌ Falha ao consultar /health: {err}")
    else:
        if health.get("connected"):
            await cq.message.answer("✅ WhatsApp conectado.\n<code>/health</code> OK.")
        else:
            await cq.message.answer("ℹ️ WhatsApp <b>não conectado</b>.\nUse o QR Code para conectar.")
    await cq.answer()

@dp.callback_query(F.data == "wa:qr")
async def cb_wa_qr(cq: CallbackQuery):
    if not WA_API_BASE:
        await cq.message.answer("❌ <b>WhatsApp:</b> WA_API_BASE não configurado.")
        await cq.answer(); return
    ok, qr, err = wa_get_qr()
    if ok and qr and qr.get("qr"):
        _send_qr_image_to_telegram(cq.message, qr["qr"])
    else:
        await cq.message.answer(f"❌ Não consegui obter QR agora. Detalhes: {err or 'indisponível'}")
    await cq.answer()

@dp.callback_query(F.data.startswith("wa:logs:"))
async def cb_wa_logs(cq: CallbackQuery):
    _, _, off = cq.data.split(":")
    offset = int(off); limit = 10
    total = count_wa_logs()
    logs = list_wa_logs(limit=limit, offset=offset)
    if not logs:
        await cq.message.answer("🧾 Sem logs para mostrar.")
        await cq.answer(); return
    tz = ZoneInfo(TZ_NAME)
    lines = ["🧾 <b>Logs de envios (WhatsApp)</b>"]
    for l in logs:
        ok = "✅" if l["ok"] else "❌"
        when = l["created_at"].astimezone(tz).strftime("%d/%m %H:%M")
        cliente = l.get("cliente_nome") or "-"
        lines.append(f"{ok} {when} • {cliente} • {l.get('phone') or '-'}\n{(l.get('info') or '')[:120]}")
    txt = "\n\n".join(lines)
    nav = []
    if offset > 0:
        prev_off = max(offset - limit, 0)
        nav.append(InlineKeyboardButton(text="⬅️ Anteriores", callback_data=f"wa:logs:{prev_off}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton(text="Próximos ➡️", callback_data=f"wa:logs:{offset+limit}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[nav] if nav else [])
    await cq.message.answer(txt, reply_markup=kb)
    await cq.answer()

@dp.callback_query(F.data == "wa:cleanup")
async def cb_wa_cleanup(cq: CallbackQuery):
    ok, msg = wa_cleanup_sessions()
    status = "✅" if ok else "❌"
    await cq.message.answer(f"{status} {msg}")
    await cq.answer()

@dp.callback_query(F.data == "wa:sched:toggle")
async def cb_sched_toggle(cq: CallbackQuery):
    enabled = _sched_enabled()
    set_setting("scheduler_enabled", "0" if enabled else "1")
    await cq.message.answer(f"🗓️ Agendador agora está: {'🟢 ON' if not enabled else '🔴 OFF'}")
    await restart_scheduler()
    await cq.message.answer("📲 <b>WhatsApp • Baileys</b>", reply_markup=wa_menu_kb(_sched_enabled()))
    await cq.answer()

@dp.callback_query(F.data == "wa:sched:times")
async def cb_sched_times(cq: CallbackQuery, state: FSMContext):
    await state.set_state(SchedConfig.waiting_times)
    await cq.message.answer(
        f"⏱️ Horários atuais: <b>{_times_human()}</b>\n"
        "Envie novos horários no formato <code>HH:MM,HH:MM,...</code> (ex.: <code>09:00,14:30,18:00</code>)"
    )
    await cq.answer()

@dp.message(SchedConfig.waiting_times)
async def msg_sched_set_times(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    valid = []
    for p in parts:
        try: datetime.strptime(p, "%H:%M"); valid.append(p)
        except ValueError: pass
    if not valid:
        await m.answer("Formato inválido. Ex.: <code>09:00,14:30,18:00</code>")
        return
    set_setting("schedule_times", ",".join(valid))
    await state.clear()
    await m.answer(f"✅ Horários atualizados para: <b>{', '.join(valid)}</b>")
    await restart_scheduler()

# ---------------------- Cadastro de usuário ----------------------
@dp.message(CadastroUsuario.nome)
async def cad_nome(m: Message, state: FSMContext):
    nome = m.text.strip()
    if len(nome) < 2:
        await m.answer("Nome muito curto. Informe seu <b>nome</b> completo."); return
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
    inserir_usuario(m.from_user.id, data["nome"], data["email"], data["telefone"] or "")
    await state.clear()
    await m.answer("✅ Cadastro concluído! Use os botões abaixo.", reply_markup=kb_main())

# ---------------------- Clientes: cadastro guiado ----------------------
@dp.message(F.text.casefold() == "➕ novo cliente")
async def novo_cliente_start(m: Message, state: FSMContext):
    await m.answer("Vamos cadastrar um cliente.\nQual é o <b>nome</b>?", reply_markup=kb_main())
    await state.set_state(NovoCliente.nome)

@dp.message(NovoCliente.nome)
async def nc_nome(m: Message, state: FSMContext):
    nome = m.text.strip()
    if len(nome) < 2:
        await m.answer("Nome muito curto. Informe o <b>nome</b> completo."); return
    await state.update_data(nome=nome)
    await m.answer("📞 Informe o <b>telefone</b> (com DDD).", reply_markup=kb_main())
    await state.set_state(NovoCliente.telefone)

@dp.message(NovoCliente.telefone)
async def nc_tel(m: Message, state: FSMContext):
    tel = normaliza_tel(m.text)
    if tel and (len(tel) < 10 or len(tel) > 16):
        await m.answer("Telefone inválido. Ex.: +55 11 99999-0000"); return
    await state.update_data(telefone=tel)
    await m.answer("📦 Escolha um <b>pacote</b> ou toque em Personalizado:", reply_markup=kb_pacotes())
    await state.set_state(NovoCliente.pacote)

@dp.message(NovoCliente.pacote)
async def nc_pacote(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    if "personalizado" in txt.lower():
        await m.answer("🛠️ Digite o <b>nome do pacote</b> desejado:", reply_markup=kb_main())
        await state.set_state(NovoCliente.pacote_personalizado); return
    await state.update_data(pacote=PACOTE_MAP.get(txt, txt if txt else None))
    await m.answer("💰 Escolha um <b>valor</b> ou toque em Outro valor:", reply_markup=kb_valores())
    await state.set_state(NovoCliente.valor)

@dp.message(NovoCliente.pacote_personalizado)
async def nc_pacote_perso(m: Message, state: FSMContext):
    pacote = m.text.strip()
    if not pacote:
        await m.answer("Informe um <b>nome de pacote</b> válido."); return
    await state.update_data(pacote=pacote)
    await m.answer("💰 Escolha um <b>valor</b> ou toque em Outro valor:", reply_markup=kb_valores())
    await state.set_state(NovoCliente.valor)

@dp.message(NovoCliente.valor)
async def nc_valor(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    if "outro valor" in txt.lower():
        await m.answer("✍️ Digite o <b>valor</b> (ex.: 89,90):", reply_markup=kb_main())
        await state.set_state(NovoCliente.valor_personalizado); return
    valor = parse_valor(txt)
    if valor is None:
        await m.answer("Valor inválido. Tente algo como <code>89,90</code> ou escolha um botão."); return
    await state.update_data(valor=float(valor))
    await m.answer("📅 Qual é a <b>data de vencimento</b>? (ex.: 10/09/2025 ou 10/09)", reply_markup=kb_main())
    await state.set_state(NovoCliente.vencimento)

@dp.message(NovoCliente.valor_personalizado)
async def nc_valor_perso(m: Message, state: FSMContext):
    valor = parse_valor(m.text)
    if valor is None:
        await m.answer("Valor inválido. Ex.: <code>89,90</code>."); return
    await state.update_data(valor=float(valor))
    await m.answer("📅 Qual é a <b>data de vencimento</b>? (ex.: 10/09/2025 ou 10/09)", reply_markup=kb_main())
    await state.set_state(NovoCliente.vencimento)

@dp.message(NovoCliente.vencimento)
async def nc_venc(m: Message, state: FSMContext):
    data_v = parse_vencimento(m.text)
    if data_v is None:
        await m.answer("Data inválida. Use <code>dd/mm/aaaa</code>, <code>dd/mm</code> ou <code>aaaa-mm-dd</code>."); return
    await state.update_data(vencimento=data_v.isoformat())
    await m.answer("📝 Outras informações (MAC, OTP etc.). Se não houver, digite <i>sem</i>.", reply_markup=kb_main())
    await state.set_state(NovoCliente.info)

@dp.message(NovoCliente.info)
async def nc_info(m: Message, state: FSMContext):
    info = (m.text or "").strip()
    info = None if info.lower() == "sem" else info
    data = await state.update_data(info=info)
    cid = inserir_cliente(
        nome=data.get("nome"), telefone=data.get("telefone"),
        pacote=data.get("pacote"), valor=data.get("valor"),
        vencimento=data.get("vencimento"), info=data.get("info"),
    )
    await state.clear()
    resumo = {"id": cid, **data}
    await m.answer(f"✅ Cliente cadastrado com ID <b>#{cid}</b>.\n\n{fmt_cliente(resumo)}", reply_markup=kb_main())

# ---------------------- Listagem Inline e Ações ----------------------
@dp.message(F.text.casefold() == "📋 clientes")
async def ver_clientes(m: Message, state: FSMContext):
    limit, offset = 10, 0
    await state.update_data(list_filter="all", list_offset=0)
    items, total = _get_clients_view("all", offset, limit)
    if total == 0:
        await m.answer("Ainda não há clientes.", reply_markup=kb_main()); return
    await m.answer(
        "📋 <b>Selecione um cliente</b> (ordenado por vencimento, mais próximo → mais distante):",
        reply_markup=clientes_inline_kb(offset, limit, total, items, "all")
    )

@dp.callback_query(F.data.startswith("list:filter:"))
async def cb_list_filter(cq: CallbackQuery, state: FSMContext):
    flt = cq.data.split(":")[2]; limit = 10; offset = 0
    await state.update_data(list_filter=flt, list_offset=offset)
    items, total = _get_clients_view(flt, offset, limit)
    if total == 0:
        await cq.message.edit_text("Nenhum cliente para este filtro.")
        await cq.message.edit_reply_markup(reply_markup=clientes_inline_kb(offset, limit, total, [], flt))
        await cq.answer(); return
    await cq.message.edit_reply_markup(reply_markup=clientes_inline_kb(offset, limit, total, items, flt))
    await cq.answer()

@dp.callback_query(F.data.startswith("list:page:"))
async def cb_list_page(cq: CallbackQuery, state: FSMContext):
    _, _, off = cq.data.split(":")
    offset = int(off); limit = 10
    data = await state.get_data(); flt = data.get("list_filter", "all")
    await state.update_data(list_offset=offset)
    items, total = _get_clients_view(flt, offset, limit)
    if not items and offset != 0:
        offset = 0; await state.update_data(list_offset=0)
        items, total = _get_clients_view(flt, offset, limit)
    await cq.message.edit_reply_markup(reply_markup=clientes_inline_kb(offset, limit, total, items, flt))
    await cq.answer()

@dp.callback_query(F.data.startswith("cli:"))
async def cb_cli_router(cq: CallbackQuery, state: FSMContext):
    _, cid, action = cq.data.split(":"); cid = int(cid)
    c = buscar_cliente_por_id(cid)
    if not c:
        await cq.answer("Cliente não encontrado", show_alert=True); return
    if action == "view":
        await cq.message.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_actions_kb(cid)); await cq.answer(); return
    if action == "edit":
        await cq.message.answer(f"✏️ Editar cliente #{cid}:\n\n{fmt_cliente(c)}", reply_markup=edit_menu_kb(cid)); await cq.answer(); return
    if action == "renew":
        await cq.message.answer(f"🔁 Renovar plano do cliente #{cid}:\n\n{fmt_cliente(c)}", reply_markup=renew_menu_kb(cid, c.get("pacote"))); await cq.answer(); return
    if action == "msg":
        await cq.message.answer(f"💬 Mensagem para cliente #{cid} ({c['nome']}):\nEscolha um template", reply_markup=msg_template_menu_kb(cid)); await cq.answer(); return
    if action == "del":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❗ Confirmar exclusão", callback_data=f"delc:{cid}")],
            [InlineKeyboardButton(text="Cancelar", callback_data=f"cli:{cid}:view")]
        ])
        await cq.message.answer(f"Tem certeza que deseja excluir o cliente #{cid}?", reply_markup=kb); await cq.answer(); return

@dp.callback_query(F.data.startswith("delc:"))
async def cb_del_confirm(cq: CallbackQuery):
    cid = int(cq.data.split(":")[1]); deletar_cliente(cid)
    await cq.message.answer(f"🗑️ Cliente #{cid} excluído.", reply_markup=kb_main()); await cq.answer()

# ---------------------- Editar Cliente ----------------------
@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit_select(cq: CallbackQuery, state: FSMContext):
    _, cid, campo = cq.data.split(":"); cid = int(cid)
    await state.update_data(edit_cid=cid)
    if campo == "nome":
        await state.set_state(EditCliente.nome); await cq.message.answer("Informe o <b>novo nome</b>:", reply_markup=kb_main()); await cq.answer(); return
    if campo == "telefone":
        await state.set_state(EditCliente.telefone); await cq.message.answer("Informe o <b>novo telefone</b>:", reply_markup=kb_main()); await cq.answer(); return
    if campo == "pacote":
        await state.set_state(EditCliente.pacote); await cq.message.answer("Escolha o <b>pacote</b> (ou Personalizado):", reply_markup=kb_pacotes()); await cq.answer(); return
    if campo == "valor":
        await state.set_state(EditCliente.valor); await cq.message.answer("Escolha o <b>valor</b> (ou Outro valor):", reply_markup=kb_valores()); await cq.answer(); return
    if campo == "venc":
        await state.set_state(EditCliente.vencimento); await cq.message.answer("Informe a <b>nova data de vencimento</b> (dd/mm/aaaa):", reply_markup=kb_main()); await cq.answer(); return
    if campo == "info":
        await state.set_state(EditCliente.info); await cq.message.answer("Digite as <b>informações</b> (MAC, OTP etc.):", reply_markup=kb_main()); await cq.answer(); return

@dp.message(EditCliente.nome)
async def edit_nome(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); atualizar_cliente(cid, nome=m.text.strip())
    await state.clear(); await m.answer("✅ Nome atualizado.")

@dp.message(EditCliente.telefone)
async def edit_tel(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); atualizar_cliente(cid, telefone=normaliza_tel(m.text))
    await state.clear(); await m.answer("✅ Telefone atualizado.")

@dp.message(EditCliente.pacote)
async def edit_pacote(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); txt = (m.text or "").strip()
    if "personalizado" in txt.lower():
        await state.set_state(EditCliente.pacote_personalizado); await m.answer("🛠️ Digite o <b>nome do pacote</b>:", reply_markup=kb_main()); return
    atualizar_cliente(cid, pacote=PACOTE_MAP.get(txt, txt)); await state.clear(); await m.answer("✅ Pacote atualizado.")

@dp.message(EditCliente.pacote_personalizado)
async def edit_pacote_perso(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); atualizar_cliente(cid, pacote=m.text.strip())
    await state.clear(); await m.answer("✅ Pacote atualizado.")

@dp.message(EditCliente.valor)
async def edit_valor(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); txt = (m.text or "").strip()
    if "outro valor" in txt.lower():
        await state.set_state(EditCliente.valor_personalizado); await m.answer("✍️ Digite o <b>valor</b> (ex.: 89,90):", reply_markup=kb_main()); return
    valor = parse_valor(txt)
    if valor is None:
        await m.answer("Valor inválido. Escolha um botão ou digite ex.: 89,90."); return
    atualizar_cliente(cid, valor=float(valor)); await state.clear(); await m.answer("✅ Valor atualizado.")

@dp.message(EditCliente.valor_personalizado)
async def edit_valor_perso(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); valor = parse_valor(m.text)
    if valor is None:
        await m.answer("Valor inválido. Ex.: 89,90."); return
    atualizar_cliente(cid, valor=float(valor)); await state.clear(); await m.answer("✅ Valor atualizado.")

@dp.message(EditCliente.vencimento)
async def edit_venc(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); d = parse_vencimento(m.text)
    if not d:
        await m.answer("Data inválida. Use dd/mm/aaaa, dd/mm ou aaaa-mm-dd."); return
    atualizar_cliente(cid, vencimento=d.isoformat()); await state.clear(); await m.answer("✅ Vencimento atualizado.")

@dp.message(EditCliente.info)
async def edit_info(m: Message, state: FSMContext):
    cid = (await state.get_data()).get("edit_cid"); info = (m.text or "").strip()
    atualizar_cliente(cid, info=None if info.lower() == "sem" else info); await state.clear(); await m.answer("✅ Informações atualizadas.")

# ---------------------- Renovar Plano ----------------------
PACOTE_TO_MONTHS = {"mensal":1,"trimestral":3,"semestral":6,"anual":12}
@dp.callback_query(F.data.startswith("renew:"))
async def cb_renew(cq: CallbackQuery):
    _, cid, opt = cq.data.split(":"); cid = int(cid)
    c = buscar_cliente_por_id(cid)
    if not c: await cq.answer("Cliente não encontrado", show_alert=True); return
    months = PACOTE_TO_MONTHS.get((c.get("pacote") or "").lower()) if opt == "auto" else int(opt)
    if not months: await cq.answer("Pacote não reconhecido. Escolha 1/3/6/12 meses.", show_alert=True); return
    new_date = renovar_vencimento(cid, months)
    await cq.message.answer(f"🔁 Renovado!\nCliente: <b>{c['nome']}</b>\nNovo vencimento: <b>{fmt_data(new_date)}</b>", reply_markup=cliente_actions_kb(cid))
    await cq.answer()

# ---------------------- Mensagens (Templates + WhatsApp) ----------------------
def compute_key_auto(venc) -> str:
    d = to_date(venc); 
    if not d: return "OUTRO"
    today = date.today(); delta = (d - today).days
    if delta == 2: return "D2"
    if delta == 1: return "D1"
    if delta == 0: return "D0"
    if delta == -1: return "DA1"
    return "OUTRO"

def render_template_text(body: str, c: dict) -> str:
    venc = to_date(c.get("vencimento")); today = date.today()
    dias_para_vencer = (venc - today).days if venc else None
    dias_atraso = (today - venc).days if (venc and today > venc) else None
    return body.format(
        nome=c.get("nome", ""),
        pacote=c.get("pacote", "seu plano"),
        valor=fmt_moeda(c["valor"]) if c.get("valor") is not None else "—",
        vencimento=fmt_data(venc),
        telefone=c.get("telefone", ""),
        dias_para_vencer=str(dias_para_vencer) if dias_para_vencer is not None else "—",
        dias_atraso=str(dias_atraso) if dias_atraso is not None else "—",
    )

def msg_send_options_kb(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 WhatsApp • Enviar agora", callback_data=f"wa:send:{cid}")],
        [InlineKeyboardButton(text="🗓️ WhatsApp • Agendar", callback_data=f"wa:schedule:{cid}")],
        [InlineKeyboardButton(text="📣 Telegram • Enviar aqui", callback_data=f"tg:send:{cid}")],
        [InlineKeyboardButton(text="⬅️ Voltar", callback_data=f"cli:{cid}:view")]
    ])

@dp.callback_query(F.data.startswith("tplmsg:"))
async def cb_tplmsg(cq: CallbackQuery, state: FSMContext):
    _, cid, key = cq.data.split(":"); cid = int(cid)
    c = buscar_cliente_por_id(cid)
    if not c: await cq.answer("Cliente não encontrado", show_alert=True); return
    if key == "AUTO": key = compute_key_auto(c.get("vencimento"))
    tpl = get_template(key)
    if not tpl: await cq.answer("Template não encontrado.", show_alert=True); return
    text = render_template_text(tpl["body"], c)
    await state.update_data(preview_cid=cid, preview_text=text)
    await cq.message.answer("📝 <b>Prévia da mensagem</b>:\n\n" + text, reply_markup=msg_send_options_kb(cid))
    await cq.answer()

@dp.callback_query(F.data.startswith("tg:send:"))
async def cb_tg_send(cq: CallbackQuery, state: FSMContext):
    _, cid = cq.data.split(":")[1:]
    data = await state.get_data(); text = data.get("preview_text")
    if not text: await cq.answer("Prévia indisponível. Selecione o template novamente.", show_alert=True); return
    await cq.message.answer(text); await cq.answer("Enviado no Telegram ✅")

@dp.callback_query(F.data.startswith("wa:send:"))
async def cb_wa_send_now(cq: CallbackQuery, state: FSMContext):
    _, _, cid = cq.data.split(":"); cid = int(cid)
    c = buscar_cliente_por_id(cid); data = await state.get_data()
    text = data.get("preview_text"); phone = wa_format_to_jid(c.get("telefone"))
    if not phone: await cq.answer("Telefone do cliente ausente/ inválido.", show_alert=True); return
    ok, msg = wa_send_now(phone, text); add_wa_log(cid, phone, text, ok, msg)
    status = "✅" if ok else "❌"
    await cq.message.answer(f"{status} WhatsApp: {msg}"); await cq.answer()

@dp.callback_query(F.data.startswith("wa:schedule:"))
async def cb_wa_schedule_ask(cq: CallbackQuery, state: FSMContext):
    _, _, cid = cq.data.split(":"); await state.update_data(schedule_cid=int(cid))
    await state.set_state(ScheduleWA.waiting_datetime)
    await cq.message.answer("🗓️ Informe <b>data e hora</b> (dd/mm/aaaa HH:MM) para agendar o WhatsApp:"); await cq.answer()

@dp.message(ScheduleWA.waiting_datetime)
async def cb_wa_schedule_set(m: Message, state: FSMContext):
    dt = parse_br_datetime(m.text or "")
    if not dt: await m.answer("Formato inválido. Use: <code>dd/mm/aaaa HH:MM</code>"); return
    dt_utc = dt.astimezone(timezone.utc); data = await state.get_data()
    cid = int(data.get("schedule_cid")); c = buscar_cliente_por_id(cid)
    text = data.get("preview_text"); phone = wa_format_to_jid(c.get("telefone"))
    if not phone: await state.clear(); await m.answer("Telefone do cliente ausente/ inválido."); return
    ok, msg = wa_schedule_at(phone, text, dt_utc.isoformat()); add_wa_log(cid, phone, text, ok, f"Agendado: {msg}")
    await state.clear(); status = "✅" if ok else "❌"; await m.answer(f"{status} Agendamento: {msg}")

# Mensagem personalizada
@dp.callback_query(F.data.startswith("msg:"))
async def cb_msg_personalizada(cq: CallbackQuery, state: FSMContext):
    parts = cq.data.split(":")
    if len(parts) >= 3 and parts[2] == "perso":
        cid = int(parts[1]); await state.update_data(msg_cid=cid)
        await state.set_state(MsgCliente.personalizada)
        await cq.message.answer("✍️ Digite a mensagem personalizada.\nVariáveis: {nome}, {pacote}, {valor}, {vencimento}, {telefone}, {dias_para_vencer}, {dias_atraso}")
        await cq.answer()

@dp.message(MsgCliente.personalizada)
async def msg_personalizada(m: Message, state: FSMContext):
    data = await state.get_data(); cid = data.get("msg_cid")
    c = buscar_cliente_por_id(int(cid)) if cid else None
    if not c: await state.clear(); await m.answer("Cliente não encontrado."); return
    text = render_template_text(m.text, c)
    await state.update_data(preview_cid=int(cid), preview_text=text)
    await m.answer("📝 <b>Prévia da mensagem</b>:\n\n" + text, reply_markup=msg_send_options_kb(int(cid)))

# ---------------------- Comandos utilitários ----------------------
@dp.message(Command("id"))
async def cmd_id(m: Message, command: CommandObject):
    if not command.args or not command.args.strip().isdigit():
        await m.answer("Uso: <code>/id 123</code>"); return
    cid = int(command.args.strip()); c = buscar_cliente_por_id(cid)
    if not c: await m.answer(f"Cliente #{cid} não encontrado."); return
    await m.answer("🗂️ Detalhes do cliente:\n\n" + fmt_cliente(c), reply_markup=cliente_actions_kb(cid))

@dp.message(F.text.casefold() == "❌ cancelar")
async def cancelar(m: Message, state: FSMContext):
    await state.clear(); await m.answer("Operação cancelada.", reply_markup=kb_main())

# ---------------------- Agendador interno (usa /schedule) ----------------------
SCHED_TASK: asyncio.Task | None = None

def _parse_times_to_datetimes(times: list[str], now: datetime) -> list[datetime]:
    tz = ZoneInfo(TZ_NAME); out = []
    for t in times:
        hh, mm = map(int, t.split(":"))
        dt = datetime(year=now.year, month=now.month, day=now.day, hour=hh, minute=mm, tzinfo=tz)
        if dt <= now: dt = dt + timedelta(days=1)
        out.append(dt)
    return sorted(out)

def _next_run_datetime(now: datetime) -> datetime:
    times = _sched_times()
    future_list = _parse_times_to_datetimes(times, now)
    return future_list[0]

async def send_due_messages():
    """Agenda no serviço externo (endpoint /schedule) as mensagens D-2, D-1, D0, D+1 para envio imediato."""
    total = contar_clientes()
    if total == 0: return
    clients = listar_clientes(limit=total, offset=0)
    today = date.today()
    valid_keys = {"D2","D1","D0","DA1"}
    # Agendar para alguns segundos à frente (garantia de processamento no serviço)
    now_local = datetime.now(ZoneInfo(TZ_NAME))
    send_at_local = now_local + timedelta(seconds=5)
    dt_utc_iso = send_at_local.astimezone(timezone.utc).isoformat()

    for c in clients:
        d = to_date(c.get("vencimento"))
        if not d: continue
        delta = (d - today).days
        key = None
        if delta == 2: key = "D2"
        elif delta == 1: key = "D1"
        elif delta == 0: key = "D0"
        elif delta == -1: key = "DA1"
        if key and key in valid_keys:
            tpl = get_template(key)
            if not tpl: continue
            text = render_template_text(tpl["body"], c)
            phone = wa_format_to_jid(c.get("telefone"))
            if not phone:
                add_wa_log(c.get("id"), None, text, False, "Telefone ausente/ inválido")
                continue
            ok, msg = wa_schedule_at(phone, text, dt_utc_iso)
            info = f"Agendado para {send_at_local.strftime('%d/%m %H:%M')} (local). {msg}"
            add_wa_log(c.get("id"), phone, text, ok, info)

async def scheduler_loop():
    while True:
        try:
            if not _sched_enabled():
                await asyncio.sleep(30)
                continue
            now = datetime.now(ZoneInfo(TZ_NAME))
            nxt = _next_run_datetime(now)
            sleep_s = (nxt - now).total_seconds()
            print(f"[SCHED] Próxima execução às {nxt.isoformat()} (em {int(sleep_s)}s)")
            await asyncio.sleep(sleep_s)
            print("[SCHED] Agendando mensagens via /schedule…")
            await send_due_messages()
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[SCHED] Erro: {e}")
            await asyncio.sleep(10)

async def start_scheduler():
    global SCHED_TASK
    if SCHED_TASK and not SCHED_TASK.done(): return
    SCHED_TASK = asyncio.create_task(scheduler_loop())

async def stop_scheduler():
    global SCHED_TASK
    if SCHED_TASK and not SCHED_TASK.done():
        SCHED_TASK.cancel()
        try: await SCHED_TASK
        except: pass
    SCHED_TASK = None

async def restart_scheduler():
    await stop_scheduler(); await start_scheduler()

# ---------------------- Main ----------------------
async def main():
    print("🚀 iniciando… limpando webhook e preparando DB")
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("⏱️ iniciando agendador…")
    await start_scheduler()
    print("✅ pronto. iniciando polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
