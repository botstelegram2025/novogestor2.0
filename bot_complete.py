# bot_complete.py
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, date

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from db import (
    init_db, add_client, get_clients, get_client,
    update_client_field, delete_client, renew_client,
    list_templates, get_template_by_offset, set_template,
    iso_to_human, human_to_iso, status_emoji, render_template, DATE_FMT, HUMAN_FMT
)


# ---------------------------
# LOGGING
# ---------------------------
def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Formato: 2025-08-20 20:31:00 | INFO | bot_complete | mensagem...
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(ch)

    # Arquivo com rotação
    fh = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(fh)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------
# CONSTS & STATES
# ---------------------------
MAIN_BTNS = [["Clientes"], ["Adicionar Cliente"], ["Templates"]]

(
    ST_ADD_NAME,
    ST_ADD_PHONE,
    ST_ADD_PACKAGE,
    ST_ADD_PRICE,
    ST_ADD_INFO,
    ST_ADD_DUE,
    ST_EDIT_FIELD_SELECT,
    ST_EDIT_FIELD_INPUT,
    ST_SEND_MESSAGE_CHOOSE,
    ST_SEND_MESSAGE_FREE,
    ST_TEMPLATE_EDIT_LABEL,
    ST_TEMPLATE_EDIT_CONTENT,
    ST_RENEW_CHOOSE_DATE,
    ST_TEMPLATE_NEW_OFFSET,
    ST_TEMPLATE_NEW_LABEL,
    ST_TEMPLATE_NEW_CONTENT,
) = range(16)

EDITABLE_FIELDS = {
    "name": "Nome",
    "phone": "Telefone",
    "package": "Pacote",
    "price": "Valor (R$)",
    "info": "Informações",
    "due_date": "Vencimento (dd/mm/aaaa)",
}


# ---------------------------
# HELPERS
# ---------------------------
def who(update: Update) -> str:
    """Retorna string curta com info de usuário/chat para log."""
    try:
        if update.effective_user:
            u = update.effective_user
            uname = f"@{u.username}" if u.username else f"{u.first_name or ''} {u.last_name or ''}".strip()
            return f"user_id={u.id} user={uname!s} chat_id={getattr(update.effective_chat,'id',None)}"
    except Exception:
        pass
    return "user=? chat=?"


def main_menu_keyboard():
    return ReplyKeyboardMarkup(MAIN_BTNS, resize_keyboard=True)


def client_button_text(c):
    return f"{status_emoji(c['due_date'])} {c['name']} - {iso_to_human(c['due_date'])}"


def client_menu_kb(client_id):
    rows = [
        [InlineKeyboardButton("✏️ Editar", callback_data=f"client:edit:{client_id}")],
        [InlineKeyboardButton("🔁 Renovar", callback_data=f"client:renewmenu:{client_id}")],
        [InlineKeyboardButton("💬 Enviar mensagem", callback_data=f"client:send:{client_id}")],
        [InlineKeyboardButton("🗑️ Excluir", callback_data=f"client:delete:{client_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back:clients")]
    ]
    return InlineKeyboardMarkup(rows)


def edit_fields_kb(client_id):
    rows = []
    for key, label in EDITABLE_FIELDS.items():
        rows.append([InlineKeyboardButton(f"{label}", callback_data=f"editfield:{client_id}:{key}")])
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")])
    return InlineKeyboardMarkup(rows)


def templates_kb():
    rows = []
    for t in list_templates():
        off = t["offset_days"]
        label = t["label"]
        rows.append([InlineKeyboardButton(f"{label} ({off:+}d)", callback_data=f"tpl:edit:{off}")])
    rows.append([InlineKeyboardButton("➕ Novo Template", callback_data="tpl:new")])
    return InlineKeyboardMarkup(rows)


def send_templates_kb(client_id):
    rows = []
    for t in list_templates():
        off = t["offset_days"]
        label = t["label"]
        rows.append([InlineKeyboardButton(f"Usar: {label}", callback_data=f"sendtpl:{client_id}:{off}")])
    rows.append([InlineKeyboardButton("Mensagem livre", callback_data=f"sendfree:{client_id}")])
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")])
    return InlineKeyboardMarkup(rows)


def renew_menu_kb(client_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ +1 mês a partir de hoje", callback_data=f"renew:auto:{client_id}")],
        [InlineKeyboardButton("🗓️ Escolher outra data", callback_data=f"renew:custom:{client_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")]
    ])


def parse_price(text):
    s = text.replace("R$", "").replace(" ", "").replace(",", ".")
    return float(s)


# Util: somar meses (respeitando final de mês)
def add_months(base_date: date, months: int = 1) -> date:
    y = base_date.year + (base_date.month - 1 + months) // 12
    m = (base_date.month - 1 + months) % 12 + 1
    # último dia do mês destino
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    d = min(base_date.day, last_day)
    return date(y, m, d)


# ---------------------------
# ERROR HANDLER (GLOBAL)
# ---------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception | %s", who(update if isinstance(update, Update) else Update(update_id=0)))
    # resposta discreta ao usuário (sem vazar stack)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("😬 Ocorreu um erro inesperado. Já registrei nos logs.")
        except Exception:
            pass


# ---------------------------
# COMMANDS
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("START | %s", who(update))
    init_db()
    await update.message.reply_text(
        "Bem-vindo ao BOT GESTOR! Escolha uma opção:",
        reply_markup=main_menu_keyboard(),
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    logger.info("MENU | %s | text=%r", who(update), text)
    low = text.lower()

    if low == "clientes":
        return await show_clients(update, context)
    if low == "adicionar cliente":
        await update.message.reply_text("Qual o *nome* do cliente?", parse_mode="Markdown")
        return ST_ADD_NAME
    if low == "templates":
        return await show_templates(update, context)

    await update.message.reply_text("Não entendi. Use o menu 😉", reply_markup=main_menu_keyboard())


# ---------------------------
# CLIENTES - LISTAGEM E AÇÕES
# ---------------------------
async def show_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("SHOW_CLIENTS | %s", who(update))
    clients = get_clients()
    if not clients:
        await update.message.reply_text("Nenhum cliente cadastrado ainda.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    buttons = []
    for c in clients:
        buttons.append([InlineKeyboardButton(client_button_text(c), callback_data=f"client:open:{c['id']}")])

    await update.message.reply_text("Clientes:", reply_markup=InlineKeyboardMarkup(buttons))
    return ConversationHandler.END


async def client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # e.g. client:open:ID
    parts = data.split(":")
    action = parts[1]
    client_id = int(parts[2])
    logger.info("CLIENT_CB | %s | action=%s client_id=%s", who(update), action, client_id)

    c = get_client(client_id)
    if not c:
        await q.edit_message_text("Cliente não encontrado.")
        return ConversationHandler.END

    if action == "open":
        txt = (
            f"{status_emoji(c['due_date'])} *{c['name']}*\n"
            f"Telefone: {c.get('phone') or '-'}\n"
            f"Pacote: {c.get('package') or '-'}\n"
            f"Valor: R$ {float(c.get('price') or 0):.2f}\n"
            f"Vencimento: {iso_to_human(c['due_date'])}\n"
            f"Info: {c.get('info') or '-'}"
        )
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=client_menu_kb(client_id))
        return ConversationHandler.END

    if action == "edit":
        await q.edit_message_text("O que deseja editar?", reply_markup=edit_fields_kb(client_id))
        context.user_data["editing_client_id"] = client_id
        return ST_EDIT_FIELD_SELECT

    if action == "renewmenu":
        await q.edit_message_text("Como deseja renovar?", reply_markup=renew_menu_kb(client_id))
        return ConversationHandler.END

    if action == "send":
        await q.edit_message_text(
            "Escolha um template ou escreva uma mensagem livre:",
            reply_markup=send_templates_kb(client_id),
        )
        return ST_SEND_MESSAGE_CHOOSE

    if action == "delete":
        deleted = delete_client(client_id)
        logger.info("DELETE_CLIENT | client_id=%s deleted=%s", client_id, deleted)
        if deleted:
            await q.edit_message_text("Cliente excluído com sucesso.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="back:clients")]]))
        else:
            await q.edit_message_text("Não foi possível excluir.")
        return ConversationHandler.END


async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    logger.info("BACK | %s | data=%s", who(update), q.data)
    if q.data == "back:clients":
        clients = get_clients()
        if not clients:
            await q.edit_message_text("Nenhum cliente cadastrado ainda.")
            return ConversationHandler.END
        buttons = []
        for c in clients:
            buttons.append([InlineKeyboardButton(client_button_text(c), callback_data=f"client:open:{c['id']}")])
        await q.edit_message_text("Clientes:", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END


# ---------------------------
# RENOVAÇÃO (submenu)
# ---------------------------
async def renew_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, mode, client_id = q.data.split(":")  # renew:auto:ID | renew:custom:ID
    client_id = int(client_id)
    logger.info("RENEW | %s | mode=%s client_id=%s", who(update), mode, client_id)

    c = get_client(client_id)
    if not c:
        await q.edit_message_text("Cliente não encontrado.")
        return ConversationHandler.END

    if mode == "auto":
        new_due = add_months(date.today(), 1)
        ok = update_client_field(client_id, "due_date", new_due.strftime(DATE_FMT))
        logger.info("RENEW_AUTO | client_id=%s ok=%s new_due=%s", client_id, ok, new_due)
        if ok:
            await q.edit_message_text(
                f"Renovado! Novo vencimento: *{new_due.strftime(HUMAN_FMT)}*",
                parse_mode="Markdown",
                reply_markup=client_menu_kb(client_id),
            )
        else:
            await q.edit_message_text("Não foi possível renovar.", reply_markup=client_menu_kb(client_id))
        return ConversationHandler.END

    if mode == "custom":
        context.user_data["renew_client_id"] = client_id
        await q.edit_message_text(
            f"Informe a nova data de vencimento ({HUMAN_FMT.lower()}):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")]])
        )
        return ST_RENEW_CHOOSE_DATE


async def renew_custom_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_id = context.user_data.get("renew_client_id")
    logger.info("RENEW_CUSTOM_INPUT | %s | client_id=%s text=%r", who(update), client_id, update.message.text)
    if not client_id:
        await update.message.reply_text("Sessão perdida. Abra o cliente novamente.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    try:
        new_iso = human_to_iso(update.message.text.strip())
    except Exception:
        await update.message.reply_text(f"Data inválida. Use {HUMAN_FMT}.")
        return ST_RENEW_CHOOSE_DATE
    ok = update_client_field(client_id, "due_date", new_iso)
    logger.info("RENEW_CUSTOM_SAVE | client_id=%s ok=%s new_due_iso=%s", client_id, ok, new_iso)
    if not ok:
        await update.message.reply_text("Não foi possível atualizar o vencimento.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    await update.message.reply_text(
        f"Vencimento atualizado para *{iso_to_human(new_iso)}*",
        parse_mode="Markdown",
        reply_markup=client_menu_kb(client_id),
    )
    return ConversationHandler.END


# ---------------------------
# EDITAR CAMPOS
# ---------------------------
async def editfield_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, client_id, field = q.data.split(":")[1:]  # editfield:CID:field
    client_id = int(client_id)
    logger.info("EDITFIELD_SELECT | %s | client_id=%s field=%s", who(update), client_id, field)

    context.user_data["editing_client_id"] = client_id
    context.user_data["editing_field"] = field

    ask = EDITABLE_FIELDS.get(field, "Campo")
    await q.edit_message_text(
        f"Informe o novo valor para *{ask}*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")]])
    )
    return ST_EDIT_FIELD_INPUT


async def editfield_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_id = context.user_data.get("editing_client_id")
    field = context.user_data.get("editing_field")
    logger.info("EDITFIELD_INPUT | %s | client_id=%s field=%s value=%r", who(update), client_id, field, update.message.text)

    if not client_id or not field:
        await update.message.reply_text("Sessão de edição perdida. Abra o cliente novamente.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    val = update.message.text.strip()
    try:
        if field == "price":
            val = parse_price(val)
        if field == "due_date":
            val = human_to_iso(val)
        ok = update_client_field(client_id, field, val)
        if not ok:
            raise ValueError("Falha ao atualizar")
    except Exception as e:
        logger.warning("EDITFIELD_ERROR | client_id=%s field=%s err=%s", client_id, field, e)
        await update.message.reply_text(f"Valor inválido: {e}")
        return ST_EDIT_FIELD_INPUT

    c = get_client(client_id)
    await update.message.reply_text("Atualizado com sucesso!", reply_markup=main_menu_keyboard())
    txt = (
        f"{status_emoji(c['due_date'])} *{c['name']}*\n"
        f"Telefone: {c.get('phone') or '-'}\n"
        f"Pacote: {c.get('package') or '-'}\n"
        f"Valor: R$ {float(c.get('price') or 0):.2f}\n"
        f"Vencimento: {iso_to_human(c['due_date'])}\n"
        f"Info: {c.get('info') or '-'}"
    )
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=client_menu_kb(client_id))
    return ConversationHandler.END


# ---------------------------
# ENVIAR MENSAGEM
# ---------------------------
async def send_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    parts = data.split(":")
    action = parts[0]  # sendtpl / sendfree
    client_id = int(parts[1])
    logger.info("SEND_CHOOSE | %s | action=%s client_id=%s", who(update), action, client_id)

    c = get_client(client_id)
    if not c:
        await q.edit_message_text("Cliente não encontrado.")
        return ConversationHandler.END

    if action == "sendtpl":
        offset = int(parts[2])
        tpl = get_template_by_offset(offset)
        if not tpl:
            await q.edit_message_text("Template não encontrado.")
            return ConversationHandler.END
        msg = render_template(tpl["content"], c, ref_days=offset)
        await q.edit_message_text(
            f"*Prévia da mensagem:*\n\n{msg}\n\n*(copie e envie manualmente ao cliente)*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:send:{client_id}")]]),
        )
        return ConversationHandler.END

    if action == "sendfree":
        context.user_data["sending_client_id"] = client_id
        await q.edit_message_text(
            "Digite a mensagem que deseja enviar:\n\n"
            "_Dica: use {nome}, {vencimento}, {valor}, {pacote}, etc._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data=f"client:open:{client_id}")]]),
        )
        return ST_SEND_MESSAGE_FREE


async def send_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_id = context.user_data.get("sending_client_id")
    logger.info("SEND_FREE_TEXT | %s | client_id=%s text=%r", who(update), client_id, update.message.text)
    c = get_client(client_id) if client_id else None
    if not c:
        await update.message.reply_text("Cliente não encontrado.")
        return ConversationHandler.END
    raw = update.message.text
    msg = render_template(raw, c)
    await update.message.reply_text(
        f"*Prévia da mensagem:*\n\n{msg}\n\n*(copie e envie manualmente ao cliente)*",
        parse_mode="Markdown",
        reply_markup=client_menu_kb(client_id),
    )
    return ConversationHandler.END


# ---------------------------
# ADICIONAR CLIENTE (WIZARD)
# ---------------------------
async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"] = {}
    context.user_data["new_client"]["name"] = update.message.text.strip()
    logger.info("ADD_NAME | %s | name=%r", who(update), context.user_data["new_client"]["name"])
    await update.message.reply_text("Telefone (opcional):")
    return ST_ADD_PHONE


async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["phone"] = update.message.text.strip()
    logger.info("ADD_PHONE | %s | phone=%r", who(update), context.user_data["new_client"]["phone"])
    await update.message.reply_text("Pacote (ex: Plano Mensal):")
    return ST_ADD_PACKAGE


async def add_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["package"] = update.message.text.strip()
    logger.info("ADD_PACKAGE | %s | package=%r", who(update), context.user_data["new_client"]["package"])
    await update.message.reply_text("Valor (ex: 49,90):")
    return ST_ADD_PRICE


async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = update.message.text.strip()
        context.user_data["new_client"]["price"] = float(price.replace("R$", "").replace(" ", "").replace(",", "."))
        logger.info("ADD_PRICE | %s | price=%s", who(update), context.user_data["new_client"]["price"])
    except Exception:
        logger.warning("ADD_PRICE_INVALID | %s | text=%r", who(update), update.message.text)
        await update.message.reply_text("Valor inválido. Tente novamente (ex: 49,90).")
        return ST_ADD_PRICE
    await update.message.reply_text("Informações adicionais (opcional):")
    return ST_ADD_INFO


async def add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["info"] = update.message.text.strip()
    logger.info("ADD_INFO | %s | info_len=%d", who(update), len(context.user_data["new_client"]["info"]))
    await update.message.reply_text(f"Data de vencimento ({HUMAN_FMT.lower()}):")
    return ST_ADD_DUE


async def add_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        due_iso = human_to_iso(update.message.text.strip())
    except Exception:
        logger.warning("ADD_DUE_INVALID | %s | text=%r", who(update), update.message.text)
        await update.message.reply_text(f"Data inválida. Use {HUMAN_FMT}.")
        return ST_ADD_DUE

    d = context.user_data["new_client"]
    cid = add_client(
        name=d.get("name"),
        phone=d.get("phone"),
        package=d.get("package"),
        price=d.get("price"),
        info=d.get("info"),
        due_date_iso=due_iso,
    )
    logger.info("ADD_CLIENT_DONE | %s | client_id=%s", who(update), cid)
    await update.message.reply_text(f"Cliente cadastrado! ID: {cid}", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ---------------------------
# TEMPLATES - LISTAR / EDITAR / CRIAR
# ---------------------------
async def show_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("SHOW_TEMPLATES | %s", who(update))
    tpls = list_templates()
    if not tpls:
        await update.message.reply_text("Nenhum template cadastrado.", reply_markup=templates_kb())
        return ConversationHandler.END

    lines = ["*Templates configurados:*"]
    for t in tpls:
        lines.append(f"- {t['label']} ({t['offset_days']:+}d)")
    lines.append("\nToque para editar ou use ➕ Novo Template.")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=templates_kb(),
    )
    return ConversationHandler.END


async def template_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")  # ["tpl","new"] OU ["tpl","edit","OFF"]
    logger.info("TPL_CHOOSE | %s | data=%s", who(update), q.data)

    # Novo template
    if len(parts) == 2 and parts[1] == "new":
        await q.edit_message_text(
            "Criar novo template\n\n"
            "1) Envie o *offset em dias* relativo ao vencimento (ex: -2, -1, 0, 1, 30).\n"
            "_Obs.: cada offset pode ter apenas 1 template._",
            parse_mode="Markdown"
        )
        return ST_TEMPLATE_NEW_OFFSET

    # Editar existente
    if len(parts) == 3 and parts[1] == "edit":
        off = int(parts[2])
        tpl = get_template_by_offset(off)
        if not tpl:
            await q.edit_message_text("Template não encontrado.")
            return ConversationHandler.END

        context.user_data["tpl_offset"] = off
        context.user_data["tpl_label"] = tpl["label"]
        context.user_data["tpl_content"] = tpl["content"]

        text = (
            f"*Editando template:*\n"
            f"Rótulo: {tpl['label']}\n"
            f"Offset: {off:+} dias\n\n"
            f"*Conteúdo atual:*\n{tpl['content']}\n\n"
            f"_Responda com o novo rótulo (ou envie /pular para manter)._"
        )
        await q.edit_message_text(text, parse_mode="Markdown")
        return ST_TEMPLATE_EDIT_LABEL

    await q.edit_message_text("Ação inválida.")
    return ConversationHandler.END


async def template_edit_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt != "/pular":
        context.user_data["tpl_label"] = txt
    logger.info("TPL_EDIT_LABEL | %s | new_label=%r", who(update), context.user_data.get("tpl_label"))
    await update.message.reply_text(
        "Envie o *novo conteúdo* do template.\n\n"
        "Placeholders disponíveis: {nome}, {telefone}, {pacote}, {valor}, {info}, {vencimento}, {dias}",
        parse_mode="Markdown",
    )
    return ST_TEMPLATE_EDIT_CONTENT


async def template_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    off = context.user_data.get("tpl_offset")
    label = context.user_data.get("tpl_label")
    logger.info("TPL_EDIT_CONTENT | %s | off=%s label=%r", who(update), off, label)
    if off is None or not label:
        await update.message.reply_text("Sessão perdida. Abra os templates novamente.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    set_template(off, label, content)
    await update.message.reply_text("Template atualizado!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# Novo Template (wizard)
async def template_new_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    try:
        off = int(txt)
    except ValueError:
        logger.warning("TPL_NEW_OFFSET_INVALID | %s | text=%r", who(update), txt)
        await update.message.reply_text("Offset inválido. Envie um número inteiro (ex: -2, 0, 1, 30).")
        return ST_TEMPLATE_NEW_OFFSET
    context.user_data["new_tpl_offset"] = off
    logger.info("TPL_NEW_OFFSET | %s | off=%s", who(update), off)
    await update.message.reply_text(
        'Agora envie o *rótulo* (ex: "2 dias antes", "No dia", "Agradecimento").',
        parse_mode="Markdown"
    )
    return ST_TEMPLATE_NEW_LABEL


async def template_new_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_tpl_label"] = update.message.text.strip()
    logger.info("TPL_NEW_LABEL | %s | label=%r", who(update), context.user_data["new_tpl_label"])
    await update.message.reply_text(
        "Por fim, envie o *conteúdo* do template.\n\n"
        "Dica: use variáveis como {nome}, {telefone}, {pacote}, {valor}, {info}, {vencimento}, {dias}",
        parse_mode="Markdown"
    )
    return ST_TEMPLATE_NEW_CONTENT


async def template_new_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    off = context.user_data.get("new_tpl_offset")
    label = context.user_data.get("new_tpl_label")
    logger.info("TPL_NEW_SAVE | %s | off=%s label=%r", who(update), off, label)
    if off is None or not label:
        await update.message.reply_text("Sessão perdida. Abra os templates novamente.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    # Se já existir template nesse offset, substitui (regra do schema atual: UNIQUE(offset_days))
    set_template(off, label, content)
    await update.message.reply_text("Novo template salvo!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ---------------------------
# APP
# ---------------------------
def build_application():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina a variável de ambiente TELEGRAM_BOT_TOKEN com o token do seu bot.")

    app = ApplicationBuilder().token(token).build()

    # Global error handler
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))

    # Menu principal por texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    # Callbacks genéricos
    app.add_handler(CallbackQueryHandler(client_callback, pattern=r"^client:(open|edit|renewmenu|send|delete):"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern=r"^back:clients$"))
    app.add_handler(CallbackQueryHandler(editfield_select, pattern=r"^editfield:\d+:(name|phone|package|price|info|due_date)$"))
    app.add_handler(CallbackQueryHandler(send_choose, pattern=r"^(sendtpl|sendfree):\d+"))
    app.add_handler(CallbackQueryHandler(renew_callback, pattern=r"^renew:(auto|custom):\d+$"))

    # IMPORTANTE: regex corrigido para aceitar "tpl:new" OU "tpl:edit:-?\d+"
    app.add_handler(CallbackQueryHandler(template_choose, pattern=r"^tpl:(?:new|edit:-?\d+)$"))

    conv = ConversationHandler(
        entry_points=[],
        states={
            ST_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ST_ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ST_ADD_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_package)],
            ST_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            ST_ADD_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_info)],
            ST_ADD_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_due)],

            ST_EDIT_FIELD_SELECT: [CallbackQueryHandler(editfield_select, pattern=r"^editfield:\d+:(name|phone|package|price|info|due_date)$")],
            ST_EDIT_FIELD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, editfield_input)],

            ST_SEND_MESSAGE_CHOOSE: [CallbackQueryHandler(send_choose, pattern=r"^(sendtpl|sendfree):\d+")],
            ST_SEND_MESSAGE_FREE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_free_text)],

            ST_RENEW_CHOOSE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, renew_custom_date_input)],

            ST_TEMPLATE_EDIT_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_edit_label)],
            ST_TEMPLATE_EDIT_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_edit_content)],

            ST_TEMPLATE_NEW_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_new_offset)],
            ST_TEMPLATE_NEW_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_new_label)],
            ST_TEMPLATE_NEW_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_new_content)],
        },
        fallbacks=[],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(conv)
    return app


if __name__ == "__main__":
    init_db()
    application = build_application()
    logger.info("BOT GESTOR iniciado. Versão de PTB compatível (>=20).")
    # Correção: remover close_loop=False (pode lançar TypeError em algumas versões)
    application.run_polling()
