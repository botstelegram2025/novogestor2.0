    import os, re, base64, requests, asyncio
    from datetime import datetime, date, timedelta, timezone
    from zoneinfo import ZoneInfo

    from aiogram import Bot, Dispatcher, F, types
    from aiogram.filters import Command
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import StatesGroup, State
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    import db

    BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("Defina BOT_TOKEN no ambiente")
    TZ_NAME = os.getenv("TZ", "America/Sao_Paulo")
    WA_API_BASE = os.getenv("WA_API_BASE", "http://localhost:3000")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    DUE_SOON_DAYS = 5

    # ------------- Helpers -------------
    def normaliza_tel(v: str | None) -> str | None:
        if not v: return None
        return ''.join(c for c in v if c.isdigit() or c == '+')

    def parse_valor(txt: str):
        if not txt: return None
        s = re.sub(r"[^\d,.-]", "", txt).replace(".", "").replace(",", ".")
        try:
            return float(s)
        except:
            return None

    def parse_vencimento(txt: str):
        if not txt: return None
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(txt.strip(), fmt).date()
            except ValueError:
                pass
        m = re.match(r"^(\d{1,2})/(\d{1,2})$", txt.strip())
        if m:
            d, mth = map(int, m.groups())
            try:
                return date(datetime.now().year, mth, d)
            except ValueError:
                return None
        return None

    def fmt_moeda(v):
        return f"R$ {float(v):.2f}".replace(".", ",") if v is not None else "—"

    def fmt_data(dv):
        if not dv: return "—"
        if isinstance(dv, str):
            try:
                return datetime.fromisoformat(dv).date().strftime("%d/%m/%Y")
            except:
                return dv
        if isinstance(dv, date):
            return dv.strftime("%d/%m/%Y")
        return str(dv)

    def due_dot(dv):
        d = dv if isinstance(dv, date) else (datetime.fromisoformat(dv).date() if dv else None)
        today = date.today()
        if d is None: return "🟡"
        if d < today: return "🔴"
        if d <= today + timedelta(days=DUE_SOON_DAYS): return "🟡"
        return "🟢"

    def kb_main():
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Novo Cliente"), KeyboardButton(text="📋 Clientes")],
                [KeyboardButton(text="🧩 Templates"), KeyboardButton(text="❌ Cancelar")],
                [KeyboardButton(text="🟢 WhatsApp")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )

    # ------------- Estados -------------
    class NovoCliente(StatesGroup):
        nome = State()
        telefone = State()
        email = State()
        pacote = State()
        valor = State()
        vencimento = State()
        info = State()

    # ------------- WhatsApp API -------------
    def wa_get(path):
        r = requests.get(f"{WA_API_BASE}{path}", timeout=15)
        r.raise_for_status()
        return r

    def wa_post(path, json):
        r = requests.post(f"{WA_API_BASE}{path}", json=json, timeout=20)
        r.raise_for_status()
        return r

    def _send_qr_image_to_telegram(m: types.Message, data_url: str):
        try:
            _, b64 = data_url.split(",", 1)
        except ValueError:
            return False
        raw = base64.b64decode(b64)
        file = BufferedInputFile(raw, filename="wa_qr.png")
        asyncio.create_task(m.answer_photo(file, caption="Escaneie este QR no WhatsApp para conectar."))
        return True

    # ------------- Comandos -------------
    @dp.message(Command("start"))
    async def start_cmd(m: types.Message, state: FSMContext):
        await m.answer("👋 Bem-vindo! Escolha uma opção:", reply_markup=kb_main())
        db.init_db()

    @dp.message(Command("help"))
    async def help_cmd(m: types.Message):
        await m.answer("Comandos:
/start, /help, /cancel
Use os botões do teclado para navegar.", reply_markup=kb_main())

    # CANCELAMENTO GLOBAL (qualquer estado)
    CANCEL_RE = r"(?i)^(?:/cancel|/stop|❌\s*cancelar|cancelar)$"
    @dp.message(F.text.regexp(CANCEL_RE))
    async def cancelar_global(m: types.Message, state: FSMContext):
        await state.clear()
        await m.answer("🛑 Operação cancelada. Você está no menu principal.", reply_markup=kb_main())

    # ------------- Cadastro Cliente -------------
    @dp.message(F.text.casefold() == "➕ novo cliente")
    async def nc_start(m: types.Message, state: FSMContext):
        await state.set_state(NovoCliente.nome)
        await m.answer("Qual é o <b>nome</b> do cliente?", reply_markup=kb_main())

    @dp.message(NovoCliente.nome)
    async def nc_nome(m: types.Message, state: FSMContext):
        nome = (m.text or "").strip()
        if len(nome) < 2:
            await m.answer("Nome muito curto. Tente novamente.")
            return
        await state.update_data(nome=nome)
        await state.set_state(NovoCliente.telefone)
        await m.answer("📞 Telefone (com DDD):")

    @dp.message(NovoCliente.telefone)
    async def nc_tel(m: types.Message, state: FSMContext):
        tel = normaliza_tel(m.text)
        await state.update_data(telefone=tel)
        await state.set_state(NovoCliente.email)
        await m.answer("📧 Email (pode deixar em branco):")

    @dp.message(NovoCliente.email)
    async def nc_email(m: types.Message, state: FSMContext):
        email = (m.text or "").strip()
        await state.update_data(email=email if email else None)
        await state.set_state(NovoCliente.pacote)
        await m.answer("📦 Pacote (Mensal/Trimestral/Semestral/Anual/Outro):")

    @dp.message(NovoCliente.pacote)
    async def nc_pac(m: types.Message, state: FSMContext):
        await state.update_data(pacote=(m.text or "").strip() or None)
        await state.set_state(NovoCliente.valor)
        await m.answer("💰 Valor (ex.: 49,90):")

    @dp.message(NovoCliente.valor)
    async def nc_valor(m: types.Message, state: FSMContext):
        v = parse_valor(m.text or "")
        if v is None:
            await m.answer("Valor inválido. Ex.: 49,90")
            return
        await state.update_data(valor=v)
        await state.set_state(NovoCliente.vencimento)
        await m.answer("📅 Vencimento (dd/mm/aaaa ou dd/mm):")

    @dp.message(NovoCliente.vencimento)
    async def nc_venc(m: types.Message, state: FSMContext):
        d = parse_vencimento(m.text or "")
        if not d:
            await m.answer("Data inválida. Use dd/mm/aaaa ou dd/mm.")
            return
        await state.update_data(vencimento=d.isoformat())
        await state.set_state(NovoCliente.info)
        await m.answer("📝 Informações adicionais (MAC, OTP etc.) — ou digite 'sem':")

    @dp.message(NovoCliente.info)
    async def nc_info(m: types.Message, state: FSMContext):
        info = (m.text or "").strip()
        if info.lower() == "sem":
            info = None
        data = await state.get_data()
        cid = db.add_client(
            name=data.get("nome"),
            phone=data.get("telefone"),
            email=data.get("email"),
            package=data.get("pacote"),
            value=data.get("valor"),
            due_date=data.get("vencimento"),
            info=info
        )
        await state.clear()
        await m.answer(f"✅ Cliente cadastrado com ID <b>#{cid}</b>.", reply_markup=kb_main())

    # ------------- Listagem de Clientes -------------
    def clientes_kb(items, total, offset, limit, filtro=None):
        rows = []
        for c in items:
            label = f"{due_dot(c.get('due_date'))} {c.get('name','—')} — {fmt_data(c.get('due_date'))}"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"cli:{c['id']}:view")])
        nav = []
        if offset > 0:
            prev_off = max(offset - limit, 0)
            nav.append(InlineKeyboardButton(text="⬅️ Anteriores", callback_data=f"list:{filtro or 'all'}:{prev_off}"))
        if offset + limit < total:
            next_off = offset + limit
            nav.append(InlineKeyboardButton(text="Próximos ➡️", callback_data=f"list:{filtro or 'all'}:{next_off}"))
        if nav:
            rows.append(nav)
        # filtros
        rows.append([
            InlineKeyboardButton(text="🔴 Vencidos/≤3 dias", callback_data="list:due:0"),
            InlineKeyboardButton(text="🟢 Todos", callback_data="list:all:0")
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @dp.message(F.text.casefold() == "📋 clientes")
    async def listar(m: types.Message):
        limit, offset = 10, 0
        items, total = db.list_clients(limit, offset)
        if not items:
            await m.answer("Não há clientes.", reply_markup=kb_main()); return
        await m.answer("📋 <b>Clientes</b> (ordenados por vencimento):",
                       reply_markup=clientes_kb(items, total, offset, limit))

    @dp.callback_query(F.data.startswith("list:"))
    async def cb_list(cq: types.CallbackQuery):
        _, kind, off = cq.data.split(":")
        offset = int(off)
        limit = 10
        if kind == "due":
            items, total = db.list_due_or_overdue(3, limit, offset)
        else:
            items, total = db.list_clients(limit, offset)
        await cq.message.edit_reply_markup(reply_markup=clientes_kb(items, total, offset, limit, filtro=kind))
        await cq.answer()

    # ------------- WhatsApp Painel -------------
    def wa_menu_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📲 Status", callback_data="wa:status"),
             InlineKeyboardButton(text="🔑 QR Code", callback_data="wa:qr")],
            [InlineKeyboardButton(text="📜 Logs", callback_data="wa:logs"),
             InlineKeyboardButton(text="🗑 Logout", callback_data="wa:logout")]
        ])

    @dp.message(F.text.lower().in_({"🟢 whatsapp", "whatsapp", "wa"}))
    async def open_wa(m: types.Message):
        await m.answer("📱 Painel WhatsApp", reply_markup=wa_menu_kb())

    @dp.message(Command("wa"))
    async def wa_cmd(m: types.Message):
        await open_wa(m)

    @dp.callback_query(F.data == "wa:status")
    async def wa_status(cq: types.CallbackQuery):
        try:
            r = wa_get("/status").json()
            await cq.message.answer(f"Status: <b>{r.get('status')}</b>\nUsuário: <code>{r.get('user')}</code>")
        except Exception as e:
            await cq.message.answer(f"❌ Erro: {e}")
        await cq.answer()

    @dp.callback_query(F.data == "wa:qr")
    async def wa_qr(cq: types.CallbackQuery):
        try:
            r = wa_get("/qr")
            # Se vier HTML com <img src="data:...">, extraímos a data url
            if "data:image" in r.text:
                import re as _re
                m = _re.search(r'src="(data:image/[^"]+)"', r.text)
                if m:
                    _send_qr_image_to_telegram(cq.message, m.group(1))
                    await cq.answer("QR enviado como imagem."); return
            await cq.message.answer("Abra o link do QR:
" + f"{WA_API_BASE}/qr")
        except Exception as e:
            await cq.message.answer(f"❌ Erro ao obter QR: {e}")
        await cq.answer()

    @dp.callback_query(F.data == "wa:logs")
    async def wa_logs(cq: types.CallbackQuery):
        try:
            r = wa_get("/logs").json()
            txt = "\n".join(r[-30:]) if isinstance(r, list) else str(r)
            await cq.message.answer("📜 Logs:
" + (txt or "(vazio)"))
        except Exception as e:
            await cq.message.answer(f"❌ Erro: {e}")
        await cq.answer()

    @dp.callback_query(F.data == "wa:logout")
    async def wa_logout(cq: types.CallbackQuery):
        try:
            wa_get("/logout")
            await cq.message.answer("✅ Sessão encerrada.")
        except Exception as e:
            await cq.message.answer(f"❌ Erro: {e}")
        await cq.answer()

    # ------------- Main -------------
    async def main():
        await bot.delete_webhook(drop_pending_updates=True)
        db.init_db()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    if __name__ == "__main__":
        asyncio.run(main())
