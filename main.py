import logging
import os
import asyncio
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import configurations and services
from config import Config
from services.database_service import db_service
from services.scheduler_service import scheduler_service
from services.whatsapp_service import whatsapp_service
from services.payment_service import payment_service
from models import User, Client, Subscription, MessageTemplate, MessageLog

# Conversation states
WAITING_FOR_PHONE = 1
WAITING_CLIENT_NAME = 2
WAITING_CLIENT_PHONE = 3
WAITING_CLIENT_PACKAGE = 4
WAITING_CLIENT_PLAN = 5
WAITING_CLIENT_PRICE_SELECTION = 6
WAITING_CLIENT_PRICE = 7
WAITING_CLIENT_SERVER = 8
WAITING_CLIENT_DUE_DATE_SELECTION = 9
WAITING_CLIENT_DUE_DATE = 10
WAITING_CLIENT_OTHER_INFO = 11

# Edit client states
EDIT_WAITING_FIELD = 12
EDIT_WAITING_NAME = 13
EDIT_WAITING_PHONE = 14
EDIT_WAITING_PACKAGE = 15
EDIT_WAITING_PRICE = 16
EDIT_WAITING_SERVER = 17
EDIT_WAITING_DUE_DATE = 18
EDIT_WAITING_OTHER_INFO = 19

# Renew client states
RENEW_WAITING_CUSTOM_DATE = 20
RENEW_WAITING_SEND_MESSAGE = 21

# Template states
TEMPLATE_WAITING_TYPE = 22
TEMPLATE_WAITING_NAME = 23
TEMPLATE_WAITING_CONTENT = 24

# Schedule configuration states
SCHEDULE_WAITING_MORNING_TIME = 25
SCHEDULE_WAITING_REPORT_TIME = 26

# Main menu keyboard
def get_main_keyboard(db_user=None):
    """Get main menu persistent keyboard"""
    keyboard = [
        [KeyboardButton("👥 Clientes"), KeyboardButton("📊 Dashboard")],
        [KeyboardButton("📋 Ver Templates"), KeyboardButton("⏰ Horários")],
        [KeyboardButton("💳 Assinatura")],
        [KeyboardButton("📱 WhatsApp"), KeyboardButton("❓ Ajuda")]
    ]
    
    # Add early payment button for trial users
    if db_user and db_user.is_trial and db_user.is_active:
        keyboard.insert(-1, [KeyboardButton("🚀 PAGAMENTO ANTECIPADO")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Client management keyboard
def get_client_keyboard():
    """Get client management persistent keyboard"""
    keyboard = [
        [KeyboardButton("➕ Adicionar Cliente"), KeyboardButton("📋 Ver Clientes")],
        [KeyboardButton("📊 Dashboard"), KeyboardButton("🏠 Menu Principal")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_price_selection_keyboard():
    """Get price selection keyboard"""
    keyboard = [
        [KeyboardButton("💰 R$ 25"), KeyboardButton("💰 R$ 30"), KeyboardButton("💰 R$ 35")],
        [KeyboardButton("💰 R$ 40"), KeyboardButton("💰 R$ 45"), KeyboardButton("💰 R$ 50")],
        [KeyboardButton("💰 R$ 60"), KeyboardButton("💰 R$ 70"), KeyboardButton("💰 R$ 90")],
        [KeyboardButton("💸 Outro valor")],
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_server_keyboard():
    """Get server selection keyboard"""
    keyboard = [
        [KeyboardButton("🖥️ FAST TV"), KeyboardButton("🖥️ EITV"), KeyboardButton("🖥️ ZTECH")],
        [KeyboardButton("🖥️ UNITV"), KeyboardButton("🖥️ GENIAL"), KeyboardButton("🖥️ SLIM PLAY")],
        [KeyboardButton("🖥️ LIVE 21"), KeyboardButton("🖥️ X SERVER")],
        [KeyboardButton("📦 OUTRO SERVIDOR")],
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_name_keyboard():
    """Get keyboard for adding client name step"""
    keyboard = [
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_phone_keyboard():
    """Get keyboard for adding client phone step"""
    keyboard = [
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_package_keyboard():
    """Get keyboard for package selection"""
    keyboard = [
        [KeyboardButton("📅 MENSAL"), KeyboardButton("📅 TRIMESTRAL")],
        [KeyboardButton("📅 SEMESTRAL"), KeyboardButton("📅 ANUAL")],
        [KeyboardButton("📦 Outros pacotes")],
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_plan_keyboard():
    """Get keyboard for custom plan name"""
    keyboard = [
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_custom_price_keyboard():
    """Get keyboard for custom price input"""
    keyboard = [
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_due_date_keyboard():
    """Get keyboard for custom due date input"""
    keyboard = [
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_add_client_other_info_keyboard():
    """Get keyboard for other info input"""
    keyboard = [
        [KeyboardButton("Pular")],
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_due_date_keyboard(months):
    """Get due date selection keyboard based on package"""
    from datetime import datetime, timedelta
    
    today = datetime.now()
    
    # Calculate dates based on package
    if months == 1:  # Mensal
        date1 = today + timedelta(days=30)
        date2 = today + timedelta(days=31)
        label1 = f"📅 {date1.strftime('%d/%m/%Y')} (30 dias)"
        label2 = f"📅 {date2.strftime('%d/%m/%Y')} (31 dias)"
    elif months == 3:  # Trimestral
        date1 = today + timedelta(days=90)
        date2 = today + timedelta(days=91)
        label1 = f"📅 {date1.strftime('%d/%m/%Y')} (3 meses)"
        label2 = f"📅 {date2.strftime('%d/%m/%Y')} (3 meses +1)"
    elif months == 6:  # Semestral
        date1 = today + timedelta(days=180)
        date2 = today + timedelta(days=181)
        label1 = f"📅 {date1.strftime('%d/%m/%Y')} (6 meses)"
        label2 = f"📅 {date2.strftime('%d/%m/%Y')} (6 meses +1)"
    elif months == 12:  # Anual
        date1 = today + timedelta(days=365)
        date2 = today + timedelta(days=366)
        label1 = f"📅 {date1.strftime('%d/%m/%Y')} (1 ano)"
        label2 = f"📅 {date2.strftime('%d/%m/%Y')} (1 ano +1)"
    else:  # Outro/padrão
        date1 = today + timedelta(days=30)
        date2 = today + timedelta(days=31)
        label1 = f"📅 {date1.strftime('%d/%m/%Y')} (30 dias)"
        label2 = f"📅 {date2.strftime('%d/%m/%Y')} (31 dias)"
    
    keyboard = [
        [KeyboardButton(label1)],
        [KeyboardButton(label2)],
        [KeyboardButton("📝 Outra data")],
        [KeyboardButton("🔙 Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Bot Handlers

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if db_user:
                # Check if user is active
                if db_user.is_active:
                    await show_main_menu(update, context)
                else:
                    # User exists but inactive (trial expired)
                    await show_reactivation_screen(update, context)
            else:
                await start_registration(update, context)
                
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        if update.message:
            await update.message.reply_text("❌ Erro interno. Tente novamente.")

async def show_reactivation_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment options for expired trial users"""
    user = update.effective_user
    
    message = f"""
⚠️ **Olá {user.first_name}, sua conta está inativa!**

Seu período de teste gratuito de 7 dias expirou. Para continuar usando todas as funcionalidades do bot, você precisa ativar a assinatura mensal.

💰 **Assinatura:** R$ 20,00/mês via PIX
✅ **Inclui:**
• Gestão ilimitada de clientes
• Lembretes automáticos via WhatsApp  
• Controle de vencimentos
• Relatórios detalhados
• Suporte prioritário

🎯 **Seus dados permanecem salvos!**
Todos os clientes e configurações já cadastradas serão mantidos após a ativação.

Deseja reativar sua conta?
"""
    
    keyboard = [
        [InlineKeyboardButton("💳 Assinar Agora (PIX)", callback_data="subscribe_now")],
        [InlineKeyboardButton("📋 Ver Detalhes", callback_data="subscription_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start user registration process"""
    user = update.effective_user
    
    welcome_message = f"""
🎉 **Bem-vindo ao Bot de Gestão de Clientes!**

Olá {user.first_name}! 

Este bot te ajuda a:
✅ Gerenciar seus clientes
✅ Enviar lembretes automáticos via WhatsApp
✅ Controlar vencimentos de planos
✅ Receber pagamentos via PIX

🆓 **Teste Grátis por 7 dias!**
Após o período de teste, a assinatura custa apenas R$ 20,00/mês.

📱 Para continuar, preciso do seu número de telefone.
Digite seu número com DDD (ex: 11999999999):
"""
    
    if update.message:
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    return WAITING_FOR_PHONE

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input during registration"""
    if not update.effective_user or not update.message:
        return
        
    user = update.effective_user
    phone_number = update.message.text or ""
    
    # Validate phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) < 10 or len(clean_phone) > 11:
        await update.message.reply_text(
            "❌ Número inválido. Digite apenas números com DDD.\n**Exemplo:** 11999999999",
            parse_mode='Markdown'
        )
        return WAITING_FOR_PHONE
    
    try:
        with db_service.get_session() as session:
            # Create new user with 7-day trial
            new_user = User(
                telegram_id=str(user.id),
                first_name=user.first_name or 'Usuário',
                last_name=user.last_name or '',
                username=user.username or '',
                phone_number=clean_phone,
                trial_start_date=datetime.utcnow(),
                trial_end_date=datetime.utcnow() + timedelta(days=7),
                is_trial=True,
                is_active=True
            )
            
            session.add(new_user)
            session.commit()
            
            # Create default templates for new user
            try:
                await create_default_templates_in_db(new_user.id)
                logger.info(f"Default templates created for user {new_user.id}")
            except Exception as e:
                logger.error(f"Error creating default templates for new user: {e}")
            
            success_message = f"""
✅ **Cadastro realizado com sucesso!**

🆓 Seu período de teste de 7 dias já começou!
📅 Válido até: {new_user.trial_end_date.strftime('%d/%m/%Y às %H:%M')}

🚀 **Próximos passos:**
1. Cadastre seus primeiros clientes
2. Configure os lembretes automáticos
3. Teste todas as funcionalidades

Use o teclado abaixo para começar:
"""
            
            await update.message.reply_text(success_message, parse_mode='Markdown')
            await show_main_menu(update, context)
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error saving user: {e}")
        await update.message.reply_text("❌ Erro ao cadastrar. Tente novamente.")
        return WAITING_FOR_PHONE

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu to user"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                if update.message:
                    await update.message.reply_text("❌ Usuário não encontrado.")
                return
            
            # Get trial info
            trial_days_left = 0
            if db_user.is_trial:
                # Calculate trial days based on created_at + 7 days
                trial_end = db_user.created_at.date() + timedelta(days=7)
                trial_days_left = max(0, (trial_end - datetime.utcnow().date()).days)
            
            status_text = "🎁 Teste" if db_user.is_trial else "💎 Premium"
            if db_user.is_trial:
                status_text += f" ({trial_days_left} dias restantes)"
            
            menu_text = f"""
🏠 **Menu Principal**

👋 Olá, {user.first_name}!

📊 **Status:** {status_text}
{'⚠️ Conta inativa' if not db_user.is_active else '✅ Conta ativa'}

O que deseja fazer?
"""
            
            reply_markup = get_main_keyboard(db_user)
            
            if update.message:
                await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
            elif update.callback_query:
                await update.callback_query.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
                
    except Exception as e:
        logger.error(f"Error showing main menu: {e}")
        if update.message:
            await update.message.reply_text("❌ Erro ao carregar menu.")
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text("❌ Erro ao carregar menu.")

async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dashboard callback"""
    if not update.callback_query or not update.callback_query.from_user:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            # Get statistics
            total_clients = session.query(Client).filter_by(user_id=db_user.id).count()
            active_clients = session.query(Client).filter_by(user_id=db_user.id, status='active').count()
            
            # Get clients expiring soon
            today = date.today()
            expiring_soon = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date <= today + timedelta(days=7),
                Client.due_date >= today
            ).count()
            
            # Monthly statistics - current month
            from calendar import monthrange
            current_year = today.year
            current_month = today.month
            month_start = date(current_year, current_month, 1)
            month_end = date(current_year, current_month, monthrange(current_year, current_month)[1])
            
            # Monthly financial calculations - clients due this month
            clients_due_query = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date >= month_start,
                Client.due_date <= month_end
            )
            clients_to_pay = clients_due_query.count()
            
            # Calculate total revenue for the month (all clients due)
            monthly_revenue_total = sum(client.plan_price or 0 for client in clients_due_query.all())
            
            # Clients that already paid this month (due date passed)
            clients_paid_query = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date >= month_start,
                Client.due_date < today  # Already passed due date (paid)
            )
            clients_paid = clients_paid_query.count()
            
            # Calculate revenue from clients who already paid
            revenue_paid = sum(client.plan_price or 0 for client in clients_paid_query.all())
            
            # Revenue still to be collected
            revenue_pending = monthly_revenue_total - revenue_paid
            
            dashboard_text = f"""
📊 **Dashboard - Visão Geral**

👥 **Clientes:**
• Total: {total_clients}
• Ativos: {active_clients}
• Inativos: {total_clients - active_clients}

💰 **Mês Atual ({month_start.strftime('%m/%Y')}):**
• 📈 Pagos: {clients_paid} (R$ {revenue_paid:.2f})
• 📋 A Pagar: {clients_to_pay - clients_paid} (R$ {revenue_pending:.2f})
• 💵 Faturamento Total: R$ {monthly_revenue_total:.2f}

⏰ **Vencimentos:**
• Próximos 7 dias: {expiring_soon}

📱 **WhatsApp:**
• Status: {"✅ Conectado" if whatsapp_service.check_instance_status(db_user.id).get('connected') else "❌ Desconectado"}

💳 **Assinatura:**
• Status: {"🆓 Teste" if db_user.is_trial else "💎 Premium"}
"""
            
            dashboard_text += "\n📲 Use o teclado abaixo para navegar"
            
            reply_markup = get_main_keyboard()
            
            await query.message.reply_text(
                dashboard_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error showing dashboard: {e}")
        await query.edit_message_text("❌ Erro ao carregar dashboard.")

async def manage_clients_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manage clients callback"""
    if not update.callback_query or not update.callback_query.from_user:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            if not db_user.is_active:
                await query.edit_message_text("⚠️ Conta inativa. Assine o plano para continuar.")
                return
            
            # Get clients
            clients = session.query(Client).filter_by(user_id=db_user.id).order_by(Client.created_at.desc()).all()
            
            if not clients:
                text = """
👥 **Gerenciar Clientes**

📋 Nenhum cliente cadastrado ainda.

Comece adicionando seu primeiro cliente!

📲 Use o teclado abaixo para navegar:
➕ **Adicionar Cliente** - Cadastrar novo cliente
🏠 **Menu Principal** - Voltar ao menu
"""
            else:
                text = f"👥 **Gerenciar Clientes**\n\n📋 **{len(clients)} cliente(s) cadastrado(s):**\n\n"
                
                for client in clients[:10]:  # Show max 10 clients
                    status_emoji = "✅" if client.status == 'active' else "❌"
                    text += f"{status_emoji} **{client.name}**\n"
                    text += f"📱 {client.phone_number}\n"
                    text += f"📦 {client.plan_name}\n"
                    text += f"💰 R$ {client.plan_price:.2f}\n"
                    text += f"📅 Vence: {client.due_date.strftime('%d/%m/%Y')}\n\n"
                
                text += "\n📲 Use o teclado abaixo para navegar"
            
            reply_markup = get_client_keyboard()
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error managing clients: {e}")
        await query.edit_message_text("❌ Erro ao carregar clientes.")

async def search_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search client callback - Ask user to type client name"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            text = """🔍 **Buscar Cliente**

Digite o nome do cliente que você quer encontrar:

💡 *Pode digitar apenas parte do nome*"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Lista Clientes", callback_data="manage_clients")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # Set user state for search
            context.user_data['searching_client'] = True
            
    except Exception as e:
        logger.error(f"Error starting client search: {e}")
        await query.edit_message_text("❌ Erro ao iniciar busca.")

async def process_client_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str):
    """Process client search from user input"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Import Client model
            from models import Client
            
            # Search clients by name (case insensitive) using ILIKE for PostgreSQL
            search_pattern = f"%{search_term}%"
            clients = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.name.ilike(search_pattern)
            ).order_by(Client.due_date.desc()).all()
            
            if not clients:
                text = f"""🔍 **Resultado da Busca**

❌ Nenhum cliente encontrado com "{search_term}"

Tente buscar com outro nome ou parte do nome."""
                
                keyboard = [
                    [InlineKeyboardButton("🔍 Buscar Novamente", callback_data="search_client")],
                    [InlineKeyboardButton("📋 Lista Clientes", callback_data="manage_clients")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            # Show search results
            from datetime import date
            today = date.today()
            
            text = f"""🔍 **Resultado da Busca**

Encontrados {len(clients)} cliente(s) com "{search_term}":"""
            
            keyboard = []
            for client in clients:
                # Status indicator
                if client.status == 'active':
                    if client.due_date < today:
                        status = "🔴"  # Overdue
                    elif (client.due_date - today).days <= 7:
                        status = "🟡"  # Due soon
                    else:
                        status = "🟢"  # Active
                else:
                    status = "⚫"  # Inactive
                
                # Format button text
                due_str = client.due_date.strftime('%d/%m')
                button_text = f"{status} {client.name} - {due_str}"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"client_{client.id}")])
            
            # Add navigation buttons
            keyboard.extend([
                [InlineKeyboardButton("🔍 Buscar Novamente", callback_data="search_client")],
                [InlineKeyboardButton("📋 Lista Clientes", callback_data="manage_clients")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error searching clients: {e}")
        await update.message.reply_text("❌ Erro ao buscar clientes.")
    finally:
        # Clear search state
        if 'searching_client' in context.user_data:
            del context.user_data['searching_client']

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current conversation and return to main menu"""
    try:
        # Clear any user data
        context.user_data.clear()
        
        # Send cancellation message
        if update.message:
            await update.message.reply_text(
                "❌ **Operação cancelada.**\n\nVoltando ao menu principal...",
                parse_mode='Markdown'
            )
            await show_main_menu(update, context)
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "❌ **Operação cancelada.**\n\nVoltando ao menu principal...",
                parse_mode='Markdown'
            )
            # Show main menu in new message
            if update.effective_user:
                await show_main_menu_message(update.callback_query.message, context)
        
        logger.info(f"Conversation cancelled by user {update.effective_user.id if update.effective_user else 'Unknown'}")
        
    except Exception as e:
        logger.error(f"Error cancelling conversation: {e}")
    
    return ConversationHandler.END

async def show_main_menu_message(message, context):
    """Helper to show main menu as new message"""
    try:
        keyboard = get_main_keyboard()
        await message.reply_text(
            "🏠 **Menu Principal**\n\nEscolha uma opção:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing main menu: {e}")

async def add_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add client callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    text = """
➕ **Adicionar Cliente**

Vamos cadastrar um novo cliente! 

Por favor, envie o **nome do cliente**:
"""
    
    await query.edit_message_text(text, parse_mode='Markdown')
    
    # Send keyboard in a separate message
    await query.message.reply_text(
        "📝 **Digite o nome do cliente:**",
        reply_markup=get_add_client_name_keyboard(),
        parse_mode='Markdown'
    )
    
    return WAITING_CLIENT_NAME

async def handle_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client name input"""
    if not update.message:
        return
        
    client_name = update.message.text or ""
    client_name = client_name.strip()
    
    # Check for cancel/menu options
    if client_name in ["🔙 Cancelar", "🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    if len(client_name) < 2:
        await update.message.reply_text(
            "❌ Nome muito curto. Digite um nome válido.",
            reply_markup=get_add_client_name_keyboard()
        )
        return WAITING_CLIENT_NAME
    
    # Store client name in context
    context.user_data['client_name'] = client_name
    
    await update.message.reply_text(
        f"✅ Nome: **{client_name}**\n\n📱 Agora digite o número de telefone (com DDD):\n**Exemplo:** 11999999999",
        reply_markup=get_add_client_phone_keyboard(),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_PHONE

async def handle_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client phone input"""
    if not update.message:
        return
        
    phone_number = update.message.text or ""
    phone_number = phone_number.strip()
    
    # Check for cancel/menu options
    if phone_number in ["🔙 Cancelar", "🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Validate phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) < 10 or len(clean_phone) > 11:
        await update.message.reply_text(
            "❌ Número inválido. Digite apenas números com DDD.\n**Exemplo:** 11999999999",
            reply_markup=get_add_client_phone_keyboard(),
            parse_mode='Markdown'
        )
        return WAITING_CLIENT_PHONE
    
    # Store phone in context
    context.user_data['client_phone'] = clean_phone
    
    await update.message.reply_text(
        f"✅ Telefone: **{clean_phone}**\n\n📦 Agora escolha o pacote:",
        reply_markup=get_add_client_package_keyboard(),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_PACKAGE

async def handle_client_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client package selection"""
    if not update.message:
        return
        
    package_text = update.message.text or ""
    package_text = package_text.strip()
    
    # Check for cancel
    if package_text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Define package options and their values
    package_options = {
        "📅 MENSAL": ("Plano Mensal", 1),
        "📅 TRIMESTRAL": ("Plano Trimestral", 3),
        "📅 SEMESTRAL": ("Plano Semestral", 6),
        "📅 ANUAL": ("Plano Anual", 12),
        "📦 Outros pacotes": ("Outro", 0)
    }
    
    if package_text in package_options:
        plan_name, months = package_options[package_text]
        
        # Store package info in context
        context.user_data['client_package'] = package_text
        context.user_data['client_plan'] = plan_name
        context.user_data['client_months'] = months
        
        if package_text == "📦 Outros pacotes":
            # Ask for custom plan name
            await update.message.reply_text(
                f"✅ Pacote: **{package_text}**\n\n📦 Digite o nome do plano personalizado:\n**Exemplo:** Plano Básico",
                reply_markup=get_add_client_plan_keyboard(),
                parse_mode='Markdown'
            )
            return WAITING_CLIENT_PLAN
        else:
            # Go to price selection
            await update.message.reply_text(
                f"✅ Pacote: **{plan_name}**\n\n💰 Escolha o valor:",
                reply_markup=get_price_selection_keyboard(),
                parse_mode='Markdown'
            )
            return WAITING_CLIENT_PRICE_SELECTION
    else:
        # Invalid selection
        await update.message.reply_text(
            "❌ Opção inválida. Escolha uma das opções do teclado:",
            reply_markup=get_add_client_package_keyboard()
        )
        return WAITING_CLIENT_PACKAGE

async def handle_client_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client plan input"""
    if not update.message:
        return
        
    plan_name = update.message.text or ""
    plan_name = plan_name.strip()
    
    # Check for cancel
    if plan_name == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    if len(plan_name) < 2:
        await update.message.reply_text(
            "❌ Nome do plano muito curto. Digite um nome válido.",
            reply_markup=get_add_client_plan_keyboard()
        )
        return WAITING_CLIENT_PLAN
    
    # Store plan in context
    context.user_data['client_plan'] = plan_name
    
    await update.message.reply_text(
        f"✅ Plano: **{plan_name}**\n\n💰 Escolha o valor:",
        reply_markup=get_price_selection_keyboard(),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_PRICE_SELECTION

async def handle_client_price_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client price selection"""
    if not update.message:
        return
        
    price_text = update.message.text or ""
    price_text = price_text.strip()
    
    # Check for cancel
    if price_text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Define price options
    price_options = {
        "💰 R$ 25": 25.0,
        "💰 R$ 30": 30.0,
        "💰 R$ 35": 35.0,
        "💰 R$ 40": 40.0,
        "💰 R$ 45": 45.0,
        "💰 R$ 50": 50.0,
        "💰 R$ 60": 60.0,
        "💰 R$ 70": 70.0,
        "💰 R$ 90": 90.0,
        "💸 Outro valor": 0.0
    }
    
    if price_text in price_options:
        if price_text == "💸 Outro valor":
            # Ask for custom price
            await update.message.reply_text(
                f"✅ Opção: **{price_text}**\n\n💰 Digite o valor personalizado:\n**Exemplo:** 75.00",
                reply_markup=get_add_client_custom_price_keyboard(),
                parse_mode='Markdown'
            )
            return WAITING_CLIENT_PRICE
        else:
            # Use predefined price
            price = price_options[price_text]
            context.user_data['client_price'] = price
            
            await update.message.reply_text(
                f"✅ Valor: **R$ {price:.2f}**\n\n🖥️ Agora escolha o servidor:",
                reply_markup=get_server_keyboard(),
                parse_mode='Markdown'
            )
            return WAITING_CLIENT_SERVER
    else:
        # Invalid selection
        await update.message.reply_text(
            "❌ Opção inválida. Escolha uma das opções do teclado:",
            reply_markup=get_price_selection_keyboard()
        )
        return WAITING_CLIENT_PRICE_SELECTION

async def handle_client_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client price input"""
    if not update.message:
        return
        
    price_text = update.message.text or ""
    price_text = price_text.strip().replace(',', '.')
    
    # Check for cancel
    if price_text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Handle custom price input - clean the text first
    import re
    
    # Remove all non-digit and non-decimal characters except comma and dot
    clean_price_text = re.sub(r'[^\d,.]', '', price_text)
    clean_price_text = clean_price_text.replace(',', '.')
    
    # Handle cases like "50" or "50.00" or "50,00"
    try:
        price = float(clean_price_text) if clean_price_text else 0
        if price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Digite apenas números.\n**Exemplos:** 50 ou 50.00 ou 50,00",
            reply_markup=get_add_client_custom_price_keyboard()
        )
        return WAITING_CLIENT_PRICE
    
    # Store price in context
    context.user_data['client_price'] = price
    
    await update.message.reply_text(
        f"✅ Valor: **R$ {price:.2f}**\n\n🖥️ Agora escolha o servidor:",
        reply_markup=get_server_keyboard(),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_SERVER

async def handle_client_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client server selection"""
    if not update.message:
        return
        
    text = update.message.text or ""
    text = text.strip()
    
    # Check for cancel
    if text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Extract server name from button text
    if text.startswith("🖥️"):
        server = text.replace("🖥️ ", "")
    elif "OUTRO SERVIDOR" in text:
        await update.message.reply_text(
            "📦 Digite o nome do servidor:",
            reply_markup=get_add_client_plan_keyboard()
        )
        return WAITING_CLIENT_SERVER
    else:
        server = text  # Manual input
    
    # Store server selection
    context.user_data['client_server'] = server
    
    # Show date selection
    months = context.user_data.get('client_months', 1)
    await update.message.reply_text(
        f"✅ Servidor: **{server}**\n\n📅 Escolha a data de vencimento:",
        reply_markup=get_due_date_keyboard(months),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_DUE_DATE_SELECTION

async def handle_client_due_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client due date selection"""
    if not update.message:
        return
        
    date_text = update.message.text or ""
    date_text = date_text.strip()
    
    # Check for cancel
    if date_text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    if date_text == "📝 Outra data":
        # Ask for custom date
        await update.message.reply_text(
            f"✅ Opção: **{date_text}**\n\n📅 Digite a data de vencimento (DD/MM/AAAA):\n**Exemplo:** 25/12/2024",
            reply_markup=get_add_client_due_date_keyboard(),
            parse_mode='Markdown'
        )
        return WAITING_CLIENT_DUE_DATE
    elif date_text.startswith("📅"):
        # Extract date from selected option
        import re
        from datetime import datetime
        
        # Extract date part (DD/MM/YYYY) from the button text
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', date_text)
        if date_match:
            try:
                date_str = date_match.group(1)
                due_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                
                # Ask for other information
                context.user_data['client_due_date'] = due_date
                await update.message.reply_text(
                    f"✅ Data: **{due_date.strftime('%d/%m/%Y')}**\n\n📝 Digite outras informações (MAC, OTP, chaves, etc.):",
                    reply_markup=get_add_client_other_info_keyboard(),
                    parse_mode='Markdown'
                )
                return WAITING_CLIENT_OTHER_INFO
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Erro ao processar data. Tente novamente:",
                    reply_markup=get_due_date_keyboard(context.user_data.get('client_months', 1))
                )
                return WAITING_CLIENT_DUE_DATE_SELECTION
    else:
        # Invalid selection
        await update.message.reply_text(
            "❌ Opção inválida. Escolha uma das opções do teclado:",
            reply_markup=get_due_date_keyboard(context.user_data.get('client_months', 1))
        )
        return WAITING_CLIENT_DUE_DATE_SELECTION

async def handle_client_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client due date input and save client"""
    if not update.message or not update.effective_user:
        return
        
    date_text = update.message.text or ""
    date_text = date_text.strip()
    
    # Check for cancel
    if date_text == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    try:
        due_date = datetime.strptime(date_text, '%d/%m/%Y').date()
        if due_date <= date.today():
            await update.message.reply_text(
                "❌ Data deve ser futura. Digite uma data válida.\n**Exemplo:** 25/12/2024",
                reply_markup=get_add_client_due_date_keyboard()
            )
            return WAITING_CLIENT_DUE_DATE
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida. Use o formato DD/MM/AAAA.\n**Exemplo:** 25/12/2024",
            reply_markup=get_add_client_due_date_keyboard()
        )
        return WAITING_CLIENT_DUE_DATE
    
    # Ask for other information
    context.user_data['client_due_date'] = due_date
    await update.message.reply_text(
        f"✅ Data: **{due_date.strftime('%d/%m/%Y')}**\n\n📝 Digite outras informações (MAC, OTP, chaves, etc.):",
        reply_markup=get_add_client_other_info_keyboard(),
        parse_mode='Markdown'
    )
    return WAITING_CLIENT_OTHER_INFO

async def handle_client_other_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client other information input and save client"""
    if not update.message or not update.effective_user:
        return
        
    other_info = update.message.text or ""
    other_info = other_info.strip()
    
    # Check for cancel
    if other_info == "🔙 Cancelar":
        await update.message.reply_text("❌ Operação cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # If user wants to skip
    if other_info.lower() in ['pular', 'skip', ''] or other_info == "Pular":
        other_info = ""
    
    # Store other info
    context.user_data['client_other_info'] = other_info
    
    # Get due date from context
    due_date = context.user_data.get('client_due_date')
    
    # Save client to database
    await save_client_to_database(update, context, due_date)
    return ConversationHandler.END

async def save_client_to_database(update: Update, context: ContextTypes.DEFAULT_TYPE, due_date):
    """Save client to database"""
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa. Assine o plano para continuar.")
                return ConversationHandler.END
            
            # Get data from context
            client_name = context.user_data.get('client_name', '')
            client_phone = context.user_data.get('client_phone', '')
            client_plan = context.user_data.get('client_plan', '')
            client_price = context.user_data.get('client_price', 0)
            client_server = context.user_data.get('client_server', '')
            client_other_info = context.user_data.get('client_other_info', '')
            
            if not client_name or not client_phone or not client_plan or not client_price or not client_server:
                await update.message.reply_text("❌ Dados incompletos. Tente novamente.")
                return ConversationHandler.END
            
            # Create client
            client = Client(
                user_id=db_user.id,
                name=client_name,
                phone_number=client_phone,
                plan_name=client_plan,
                plan_price=client_price,
                server=client_server,
                other_info=client_other_info,
                due_date=due_date,
                status='active'
            )
            
            session.add(client)
            session.commit()
            session.refresh(client)  # Refresh to get updated data
            
            # Send welcome message within session
            await send_welcome_message_with_session(session, client, db_user.id)
            
            # Build success message
            other_info_display = f"\n📝 {client.other_info}" if client.other_info else ""
            
            success_message = f"""
✅ **Cliente cadastrado com sucesso!**

👤 **{client.name}**
📱 {client.phone_number}
📦 {client.plan_name}
🖥️ {client.server}
💰 R$ {client.plan_price:.2f}
📅 Vence: {client.due_date.strftime('%d/%m/%Y')}{other_info_display}

📱 Mensagem de boas-vindas enviada via WhatsApp!
"""
            
            keyboard = [
                [InlineKeyboardButton("➕ Adicionar Outro", callback_data="add_client")],
                [InlineKeyboardButton("📋 Ver Clientes", callback_data="manage_clients")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(success_message, reply_markup=reply_markup, parse_mode='Markdown')
            
            # Clear context
            context.user_data.clear()
            
    except Exception as e:
        logger.error(f"Error saving client: {e}")
        await update.message.reply_text("❌ Erro ao cadastrar cliente. Tente novamente.")
        return ConversationHandler.END

async def subscription_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription info callback"""
    if not update.callback_query or not update.callback_query.from_user:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            # Get subscription info
            trial_days_left = 0
            if db_user.is_trial:
                # Calculate trial days based on created_at + 7 days
                trial_end = db_user.created_at.date() + timedelta(days=7)
                trial_days_left = max(0, (trial_end - datetime.utcnow().date()).days)
            
            subscription_days_left = 0
            if db_user.next_due_date:
                subscription_days_left = max(0, (db_user.next_due_date - datetime.utcnow()).days)
            
            if db_user.is_trial:
                status_text = f"""
💳 **Informações da Assinatura**

🎁 **Período de Teste Ativo**
📅 Dias restantes: **{trial_days_left}**

💎 **Plano Premium - R$ 20,00/mês**

✅ **Funcionalidades incluídas:**
• Gestão ilimitada de clientes
• Lembretes automáticos via WhatsApp  
• Controle de vencimentos
• Templates personalizáveis
• Suporte prioritário

{"⚠️ **Seu teste expira em breve!**" if trial_days_left <= 2 else ""}

💡 **Pode pagar antecipadamente para garantir continuidade!**
"""
                keyboard = [
                    [InlineKeyboardButton("💳 Assinar Agora (PIX)", callback_data="subscribe_now")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
            else:
                status_text = f"""
💳 **Informações da Assinatura**

💎 **Plano Premium Ativo**
💰 Valor: R$ 20,00/mês
📅 Próximo vencimento: {db_user.next_due_date.strftime('%d/%m/%Y') if db_user.next_due_date else 'N/A'}
⏰ Dias restantes: {subscription_days_left}

✅ **Status:** {'Ativa' if db_user.is_active else 'Inativa'}
"""
                keyboard = [
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing subscription info: {e}")
        await query.edit_message_text("❌ Erro ao carregar informações da assinatura.")

async def whatsapp_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle WhatsApp status callback and show QR code if needed"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    try:
        # Get user info
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado. Use /start para se registrar.")
                return
            
            status = whatsapp_service.check_instance_status(db_user.id)
            
            if status.get('success') and status.get('connected'):
                # Connected - show connected status
                status_text = """✅ **WhatsApp Conectado**

🟢 Status: Conectado e funcionando
📱 Pronto para enviar mensagens automáticas
⏰ Sistema de lembretes ativo"""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Atualizar", callback_data="whatsapp_status")],
                    [InlineKeyboardButton("🔌 Desconectar", callback_data="whatsapp_disconnect")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                
            elif status.get('success') and status.get('qrCode'):
                # Not connected but has QR - show QR status
                status_text = """📱 **WhatsApp - Aguardando Conexão**

🔄 Escaneie o QR Code para conectar
📲 Use o WhatsApp do seu celular"""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Novo QR", callback_data="whatsapp_status")],
                    [InlineKeyboardButton("🔌 Reconectar", callback_data="whatsapp_reconnect")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                
                # Send QR image if available
                try:
                    qr_code = status.get('qrCode')
                    if qr_code.startswith('data:image'):
                        qr_data = qr_code.split(',')[1]
                    else:
                        qr_data = qr_code
                    
                    import base64, io
                    qr_bytes = base64.b64decode(qr_data)
                    qr_photo = io.BytesIO(qr_bytes)
                    qr_photo.name = 'whatsapp_qr.png'
                    
                    await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=qr_photo,
                        caption="📲 **QR Code WhatsApp**\n\nEscaneie para conectar"
                    )
                    return
                    
                except Exception as qr_error:
                    logger.error(f"Error sending QR: {qr_error}")
                    
            else:
                # Disconnected or error
                status_text = """❌ **WhatsApp Desconectado**

🔴 Status: Desconectado
📱 Escolha como conectar:"""
                
                keyboard = [
                    [InlineKeyboardButton("📱 QR Code", callback_data="whatsapp_reconnect")],
                    [InlineKeyboardButton("🔐 Código", callback_data="whatsapp_pairing_code")],
                    [InlineKeyboardButton("🔄 Atualizar", callback_data="whatsapp_status")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in whatsapp_status_callback: {e}")
        await query.edit_message_text("❌ Erro ao verificar status do WhatsApp.")

async def whatsapp_disconnect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle WhatsApp disconnect"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    try:
        # Get user info
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado. Use /start para se registrar.")
                return
            
            result = whatsapp_service.disconnect_whatsapp(db_user.id)
            
            if result.get('success'):
                status_text = """🔌 **WhatsApp Desconectado**

✅ Desconectado com sucesso
🔴 Status: Offline"""
            else:
                status_text = f"""❌ **Erro ao Desconectar**

🔧 Erro: {result.get('error', 'Desconhecido')}"""
            
            keyboard = [
                [InlineKeyboardButton("📱 QR Code", callback_data="whatsapp_reconnect")],
                [InlineKeyboardButton("🔐 Código", callback_data="whatsapp_pairing_code")],
                [InlineKeyboardButton("🔄 Verificar Status", callback_data="whatsapp_status")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error disconnecting WhatsApp: {e}")
        await query.edit_message_text("❌ Erro ao desconectar WhatsApp.")

async def whatsapp_reconnect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle WhatsApp reconnect and generate new QR code"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    logger.info("🔄 WhatsApp reconnect requested - generating new QR code")
    
    # Show reconnecting message first
    await query.edit_message_text("🔄 **Gerando Novo QR Code...**\n\n⏳ Aguarde alguns segundos...", parse_mode='Markdown')
    
    try:
        import asyncio
        
        # Get user info
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado. Use /start para se registrar.")
                return
            
            user_id = db_user.id  # Get the ID while inside the session
            
        # FORCE GENERATE NEW QR CODE - GUARANTEED TO WORK
        logger.info("🚀 FORCING NEW QR CODE GENERATION...")
        result = whatsapp_service.force_new_qr(user_id)
        logger.info(f"Force QR result: {result}")
        
        qr_code = None
        if result.get('success') and result.get('qrCode'):
            qr_code = result.get('qrCode')
            logger.info(f"✅ QR Code forcefully generated! Length: {len(qr_code)}")
        else:
            logger.error(f"❌ Force QR failed: {result.get('error', 'Unknown error')}")
            # Fallback to old method if force QR fails
            logger.info("Trying fallback reconnect method...")
            fallback_result = whatsapp_service.reconnect_whatsapp(user_id)
            if fallback_result.get('success'):
                await asyncio.sleep(5)
                status = whatsapp_service.check_instance_status(user_id)
                if status.get('qrCode'):
                    qr_code = status.get('qrCode')
                    logger.info(f"✅ Fallback QR Code found! Length: {len(qr_code)}")
        
        # Process QR code if found (either immediate or after reconnect)
        if qr_code:
            logger.info(f"✅ Processing QR Code! Length: {len(qr_code)}")
            
            try:
                # Send QR code as photo immediately
                import base64
                import io
                
                logger.info("Converting QR Code to image...")
                
                # Convert base64 QR code to bytes
                if qr_code.startswith('data:image'):
                    qr_data = qr_code.split(',')[1]
                    logger.info("✅ Removed data URL prefix")
                else:
                    qr_data = qr_code
                    
                qr_bytes = base64.b64decode(qr_data)
                qr_photo = io.BytesIO(qr_bytes)
                qr_photo.name = 'whatsapp_qr_fresh.png'
                
                logger.info(f"✅ QR code image prepared: {len(qr_bytes)} bytes")
                
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_photo,
                    caption="""📲 **QR Code WhatsApp Atualizado**

✅ QR Code gerado com sucesso!
📱 Escaneie este código com seu WhatsApp para conectar.

**Instruções:**
1. Abra WhatsApp no celular
2. Toque nos 3 pontos (⋮)
3. Toque em "Dispositivos conectados"
4. Toque em "Conectar um dispositivo"
5. Escaneie este QR Code""",
                    parse_mode='Markdown'
                )
                
                logger.info("🎉 QR code sent successfully!")
                
                # Update message to success
                success_text = """✅ **QR Code Gerado!**

📲 O QR Code foi enviado como imagem acima.
📱 Escaneie com seu WhatsApp para conectar."""
                
                success_keyboard = [
                    [InlineKeyboardButton("🔄 Gerar Novo QR", callback_data="whatsapp_reconnect")],
                    [InlineKeyboardButton("🔄 Verificar Status", callback_data="whatsapp_status")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                
                success_markup = InlineKeyboardMarkup(success_keyboard)
                await query.edit_message_text(success_text, reply_markup=success_markup, parse_mode='Markdown')
                
            except Exception as qr_error:
                logger.error(f"❌ Error sending QR code: {qr_error}")
                await query.edit_message_text(
                    f"❌ **Erro ao enviar QR Code**\n\nErro: {str(qr_error)}",
                    parse_mode='Markdown'
                )
        else:
            logger.warning("❌ No QR code available")
            error_text = """❌ **QR Code não disponível**

O servidor WhatsApp pode estar reiniciando.
Tente novamente em alguns segundos."""
            
            error_keyboard = [
                [InlineKeyboardButton("🔄 Tentar Novamente", callback_data="whatsapp_reconnect")],
                [InlineKeyboardButton("🔄 Verificar Status", callback_data="whatsapp_status")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            
            error_markup = InlineKeyboardMarkup(error_keyboard)
            await query.edit_message_text(error_text, reply_markup=error_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Error in whatsapp_reconnect_callback: {e}")
        await query.edit_message_text("❌ Erro ao reconectar WhatsApp.")

async def whatsapp_pairing_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start pairing code process"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    logger.info("🔐 WhatsApp pairing code requested")
    
    # Explain pairing code process
    explanation_text = """🔐 **Conexão por Código de Pareamento**

✨ **Como funciona:**
• Você digita seu número de telefone completo
• Geramos um código de 8 dígitos 
• Você digita o código no seu WhatsApp
• Conecta sem precisar escanear QR!

📱 **Digite seu número completo com DDD:**
Exemplo: 5561999887766"""
    
    await query.edit_message_text(explanation_text, parse_mode='Markdown')
    return "WAITING_PHONE_NUMBER"

async def handle_pairing_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number for pairing code"""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Por favor, digite um número válido.")
        return "WAITING_PHONE_NUMBER"
        
    phone_number = update.message.text.strip()
    
    # Basic validation
    if not phone_number.isdigit() or len(phone_number) < 10:
        await update.message.reply_text("""❌ **Número inválido!**

📱 Digite o número completo com DDD.
Exemplo: 5561999887766

Tente novamente:""", parse_mode='Markdown')
        return "WAITING_PHONE_NUMBER"
    
    # Show processing message
    await update.message.reply_text("🔐 **Gerando código de pareamento...**\n\n⏳ Aguarde alguns segundos...", parse_mode='Markdown')
    
    try:
        # Get user info
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado. Use /start para se registrar.")
                return ConversationHandler.END
            
            # Request pairing code
            result = whatsapp_service.request_pairing_code(db_user.id, phone_number)
            
            if result.get('success'):
                pairing_code = result.get('pairing_code')
                
                success_text = f"""✅ **Código Gerado!**

🔐 **Seu código de pareamento:** `{pairing_code}`

📱 **Como usar:**
1️⃣ Abra o WhatsApp no seu celular
2️⃣ Vá em Configurações > Aparelhos conectados
3️⃣ Clique em "Conectar um aparelho"
4️⃣ Clique em "Conectar com código de pareamento"
5️⃣ Digite o código: `{pairing_code}`

⏱️ **O código expira em alguns minutos!**"""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Verificar Status", callback_data="whatsapp_status")],
                    [InlineKeyboardButton("🆕 Novo Código", callback_data="whatsapp_pairing_code")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
                
            else:
                error_msg = result.get('error', 'Erro desconhecido')
                error_text = f"""❌ **Erro ao gerar código**

🔧 **Erro:** {error_msg}

Tente novamente ou use QR Code."""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Tentar Novamente", callback_data="whatsapp_pairing_code")],
                    [InlineKeyboardButton("📱 Usar QR Code", callback_data="whatsapp_reconnect")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(error_text, reply_markup=reply_markup, parse_mode='Markdown')
                
    except Exception as e:
        logger.error(f"Error in pairing code process: {e}")
        await update.message.reply_text("""❌ **Erro interno**

Tente usar QR Code ou contate o suporte.""")
    
    return ConversationHandler.END

async def cancel_pairing_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel pairing code process"""
    await update.message.reply_text("❌ Processo cancelado.")
    return ConversationHandler.END

async def schedule_settings_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show schedule settings menu"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Get current schedule settings
            from models import UserScheduleSettings
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if not schedule_settings:
                # Create default settings
                schedule_settings = UserScheduleSettings(
                    user_id=db_user.id,
                    morning_reminder_time='09:00',
                    daily_report_time='08:00'
                )
                session.add(schedule_settings)
                session.commit()
            
            text = f"""⏰ **Configurações de Horários**

📅 **Horários Atuais:**
• 🌅 Lembretes matinais: **{schedule_settings.morning_reminder_time}**
• 📊 Relatório diário: **{schedule_settings.daily_report_time}**

⚙️ **O que você deseja fazer?**"""
            
            keyboard = [
                [InlineKeyboardButton("🌅 Alterar Horário Matinal", callback_data="set_morning_time")],
                [InlineKeyboardButton("📊 Alterar Horário Relatório", callback_data="set_report_time")],
                [InlineKeyboardButton("📋 Ver Fila de Envios", callback_data="view_sending_queue")],
                [InlineKeyboardButton("❌ Cancelar Envio Específico", callback_data="cancel_specific_sending")],
                [InlineKeyboardButton("🔄 Resetar para Padrão", callback_data="reset_schedule")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing schedule settings: {e}")
        await update.message.reply_text("❌ Erro ao carregar configurações de horários.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help command"""
    help_text = """
❓ **Ajuda - Bot WhatsApp**

🤖 **Como usar:**
• Digite /start para começar
• Use os botões do menu para navegar
• Cadastre clientes e configure lembretes

📋 **Comandos disponíveis:**
• /start - Iniciar ou voltar ao menu
• /help - Mostrar esta ajuda

✨ **Funcionalidades:**
• 👥 Gestão de clientes
• 📅 Controle de vencimentos
• 📱 Lembretes automáticos via WhatsApp
• 💰 Sistema de pagamentos PIX

🎁 **Teste grátis:** 7 dias
💎 **Plano Premium:** R$ 20,00/mês

📞 **Suporte:** @seunick_suporte
"""
    
    help_text += "\n\n📲 Use o teclado abaixo para navegar"
    
    reply_markup = get_main_keyboard()
    
    if update.message:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def send_welcome_message_with_session(session, client, user_id):
    """Send welcome message to new client using existing session"""
    try:
        template = session.query(MessageTemplate).filter_by(
            template_type='welcome',
            is_active=True
        ).first()
        
        if template:
            from templates.message_templates import format_welcome_message
            message_content = format_welcome_message(
                template.content,
                client_name=client.name,
                plan_name=client.plan_name,
                plan_price=client.plan_price,
                due_date=client.due_date.strftime('%d/%m/%Y')
            )
            
            # Send via WhatsApp
            result = whatsapp_service.send_message(client.phone_number, message_content, user_id)
            
            if result.get('success'):
                logger.info(f"Welcome message sent to {client.name}")
            else:
                logger.error(f"Failed to send welcome message to {client.name}: {result.get('error')}")
    
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

async def send_welcome_message(client, user_id):
    """Send welcome message to new client"""
    try:
        with db_service.get_session() as session:
            await send_welcome_message_with_session(session, client, user_id)
    
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu callback"""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()
    await show_main_menu(update, context)

async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown callback queries"""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer("❌ Comando não reconhecido.")

# Keyboard button handlers
async def handle_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle persistent keyboard button presses"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    
    # Check if user is creating a template (new step-by-step system)
    creating_step = context.user_data.get('creating_template_step')
    
    if creating_step:
        await process_template_creation(update, context, text)
        return
    
    # Check if user is editing a template
    if context.user_data.get('editing_template'):
        await process_template_edit(update, context, text)
        return
    
    # Check if user is searching for a client
    if context.user_data.get('searching_client'):
        # Clear the search state first to avoid loops
        del context.user_data['searching_client']
        await process_client_search(update, context, text)
        return
    
    
    # Debug all button presses
    logger.info(f"handle_keyboard_buttons: Received text '{text}' from user {update.effective_user.id if update.effective_user else 'None'}")
    
    # Main menu buttons
    if text == "👥 Clientes":
        await manage_clients_message(update, context)
    elif text == "📊 Dashboard":
        await dashboard_message(update, context)
    elif text == "📱 WhatsApp":
        await whatsapp_status_message(update, context)
    elif text == "💳 Assinatura":
        await subscription_info_message(update, context)
    elif text == "📋 Ver Templates":
        await templates_list_message(update, context)
    elif text == "⏰ Horários":
        await schedule_settings_message(update, context)
    elif text == "➕ Adicionar Cliente":
        await add_client_message(update, context)
    elif text == "❓ Ajuda":
        await help_command(update, context)
    elif text == "🏠 Menu Principal":
        await show_main_menu(update, context)
    elif text == "📋 Ver Clientes":
        await manage_clients_message(update, context)
    elif text == "🚀 PAGAMENTO ANTECIPADO":
        logger.info(f"🚀 PAGAMENTO ANTECIPADO button pressed by user {update.effective_user.id}")
        await early_payment_message(update, context)
    else:
        # Log unknown button presses
        logger.warning(f"handle_keyboard_buttons: Unknown button pressed: '{text}' by user {update.effective_user.id if update.effective_user else 'None'}")

async def early_payment_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle early payment for trial users - Direct to payment"""
    logger.info(f"early_payment_message called by user {update.effective_user.id if update.effective_user else 'None'}")
    
    if not update.effective_user:
        logger.error("early_payment_message: No effective_user found")
        return
        
    user = update.effective_user
    logger.info(f"Processing early payment for user {user.id} ({user.first_name})")
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                logger.error(f"early_payment_message: User {user.id} not found in database")
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
                
            logger.info(f"early_payment_message: User {user.id} found, is_trial={db_user.is_trial}, is_active={db_user.is_active}")
                
            if not db_user.is_trial:
                logger.warning(f"early_payment_message: User {user.id} is not in trial mode")
                await update.message.reply_text("❌ Esta opção está disponível apenas para usuários em teste.")
                return
            
            # Calculate trial days left
            trial_end = db_user.created_at.date() + timedelta(days=7)
            trial_days_left = max(0, (trial_end - datetime.utcnow().date()).days)
            
            message = f"""
🚀 **PAGAMENTO ANTECIPADO**

🎁 Você ainda tem **{trial_days_left} dias** de teste restantes!

✅ **Vantagens de pagar agora:**
• Garante continuidade sem interrupções
• Evita perder acesso às funcionalidades
• Seus dados ficam sempre salvos

💰 **Valor:** R$ 20,00/mês via PIX
📅 **Duração:** 30 dias a partir do pagamento

Deseja continuar com o pagamento antecipado?
"""
            
            keyboard = [
                [InlineKeyboardButton("💳 SIM, PAGAR AGORA!", callback_data="subscribe_now")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.info(f"early_payment_message: Sending early payment message to user {user.id}")
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            logger.info(f"early_payment_message: Early payment message sent successfully to user {user.id}")
            
    except Exception as e:
        logger.error(f"Error showing early payment: {e}")
        await update.message.reply_text("❌ Erro ao carregar opções de pagamento.")

async def manage_clients_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manage clients from keyboard - Show client list with inline buttons"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
            
            if not db_user.is_active:
                await update.message.reply_text("⚠️ Conta inativa. Assine o plano para continuar.")
                return
            
            # Get clients ordered by due date (descending - most urgent first)
            clients = session.query(Client).filter_by(user_id=db_user.id).order_by(Client.due_date.desc()).all()
            
            if not clients:
                text = """
👥 **Lista de Clientes**

📋 Nenhum cliente cadastrado ainda.

Comece adicionando seu primeiro cliente!
"""
                keyboard = [
                    [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                    [InlineKeyboardButton("🔍 Buscar Cliente", callback_data="search_client")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            # Create client list with inline buttons
            from datetime import date
            today = date.today()
            
            text = f"👥 **Lista de Clientes** ({len(clients)} total)\n\n📋 Selecione um cliente para gerenciar:"
            
            keyboard = []
            for client in clients:
                # Status indicator
                if client.status == 'active':
                    if client.due_date < today:
                        status = "🔴"  # Overdue
                    elif (client.due_date - today).days <= 7:
                        status = "🟡"  # Due soon
                    else:
                        status = "🟢"  # Active
                else:
                    status = "⚫"  # Inactive
                
                # Format button text
                due_str = client.due_date.strftime('%d/%m')
                button_text = f"{status} {client.name} - {due_str}"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"client_{client.id}")])
            
            # Add navigation buttons
            keyboard.extend([
                [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                [InlineKeyboardButton("🔍 Buscar Cliente", callback_data="search_client")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error managing clients: {e}")
        await update.message.reply_text("❌ Erro ao carregar clientes.")

async def client_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show client details and submenu"""
    if not update.callback_query or not update.callback_query.from_user:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa. Assine o plano para continuar.")
                return
            
            # Get client details
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Format client details
            from datetime import date
            today = date.today()
            
            # Status indicator and text
            if client.status == 'active':
                if client.due_date < today:
                    status_icon = "🔴"
                    status_text = "Em atraso"
                elif (client.due_date - today).days <= 7:
                    status_icon = "🟡"
                    status_text = "Vence em breve"
                else:
                    status_icon = "🟢"
                    status_text = "Ativo"
            else:
                status_icon = "⚫"
                status_text = "Inativo"
            
            # Build client info text
            other_info_display = f"\n📝 {client.other_info}" if client.other_info else ""
            
            # Auto reminders status
            auto_reminders_status = getattr(client, 'auto_reminders_enabled', True)
            reminders_emoji = "✅" if auto_reminders_status else "❌"
            reminders_text = "Ativados" if auto_reminders_status else "Desativados"
            
            text = f"""
{status_icon} **{client.name}**

📱 {client.phone_number}
📦 {client.plan_name}
🖥️ {client.server or 'Não definido'}
💰 R$ {client.plan_price:.2f}
📅 Vence: {client.due_date.strftime('%d/%m/%Y')}
📊 Status: {status_text}
🤖 Lembretes: {reminders_emoji} {reminders_text}{other_info_display}

🔧 **Escolha uma ação:**
"""
            
            # Create submenu buttons
            # Dynamic button for auto reminders toggle
            reminders_button_text = "❌ Desativar Lembretes" if auto_reminders_status else "✅ Ativar Lembretes"
            reminders_callback = f"toggle_reminders_{client.id}"
            
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Editar", callback_data=f"edit_{client.id}"),
                    InlineKeyboardButton("🔄 Renovar", callback_data=f"renew_{client.id}")
                ],
                [
                    InlineKeyboardButton("💬 Mensagem", callback_data=f"message_{client.id}"),
                    InlineKeyboardButton("🗑️ Excluir", callback_data=f"delete_{client.id}")
                ],
                [
                    InlineKeyboardButton(reminders_button_text, callback_data=reminders_callback)
                ],
                [
                    InlineKeyboardButton("📦 Arquivar", callback_data=f"archive_{client.id}"),
                    InlineKeyboardButton("🔙 Voltar", callback_data="back_to_clients")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing client details: {e}")
        await query.edit_message_text("❌ Erro ao carregar detalhes do cliente.")

async def back_to_clients_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to client list"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    # Simulate the original manage_clients_message but for callback
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get clients ordered by due date (descending)
            clients = session.query(Client).filter_by(user_id=db_user.id).order_by(Client.due_date.desc()).all()
            
            if not clients:
                text = """
👥 **Lista de Clientes**

📋 Nenhum cliente cadastrado ainda.

Comece adicionando seu primeiro cliente!
"""
                keyboard = [
                    [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                    [InlineKeyboardButton("🔍 Buscar Cliente", callback_data="search_client")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            # Create client list with inline buttons
            from datetime import date
            today = date.today()
            
            text = f"👥 **Lista de Clientes** ({len(clients)} total)\n\n📋 Selecione um cliente para gerenciar:"
            
            keyboard = []
            for client in clients:
                # Status indicator
                if client.status == 'active':
                    if client.due_date < today:
                        status = "🔴"  # Overdue
                    elif (client.due_date - today).days <= 7:
                        status = "🟡"  # Due soon
                    else:
                        status = "🟢"  # Active
                else:
                    status = "⚫"  # Inactive
                
                # Format button text
                due_str = client.due_date.strftime('%d/%m')
                button_text = f"{status} {client.name} - {due_str}"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"client_{client.id}")])
            
            # Add navigation buttons
            keyboard.extend([
                [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                [InlineKeyboardButton("🔍 Buscar Cliente", callback_data="search_client")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error returning to client list: {e}")
        await query.edit_message_text("❌ Erro ao carregar lista de clientes.")

async def delete_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client deletion"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Delete client
            session.delete(client)
            session.commit()
            
            await query.edit_message_text(f"✅ Cliente **{client.name}** foi excluído com sucesso.", parse_mode='Markdown')
            
            # Auto return to client list after 2 seconds
            import asyncio
            await asyncio.sleep(2)
            await back_to_clients_callback(update, context)
            
    except Exception as e:
        logger.error(f"Error deleting client: {e}")
        await query.edit_message_text("❌ Erro ao excluir cliente.")

async def archive_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client archiving"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Archive client (change status to inactive)
            old_status = client.status
            client.status = 'inactive' if client.status == 'active' else 'active'
            session.commit()
            
            action = "arquivado" if client.status == 'inactive' else "reativado"
            await query.edit_message_text(f"✅ Cliente **{client.name}** foi {action} com sucesso.", parse_mode='Markdown')
            
            # Auto return to client list after 2 seconds
            import asyncio
            await asyncio.sleep(2)
            await back_to_clients_callback(update, context)
            
    except Exception as e:
        logger.error(f"Error archiving client: {e}")
        await query.edit_message_text("❌ Erro ao arquivar cliente.")

async def edit_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client editing - show edit options menu"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client details
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Store client ID in context for editing
            context.user_data['edit_client_id'] = client_id
            
            text = f"""
✏️ **Editar Cliente: {client.name}**

📋 Escolha o que deseja editar:
"""
            
            # Create edit options menu
            keyboard = [
                [InlineKeyboardButton("👤 Nome", callback_data=f"edit_field_name_{client_id}")],
                [InlineKeyboardButton("📱 Telefone", callback_data=f"edit_field_phone_{client_id}")],
                [InlineKeyboardButton("📦 Plano", callback_data=f"edit_field_package_{client_id}")],
                [InlineKeyboardButton("💰 Valor", callback_data=f"edit_field_price_{client_id}")],
                [InlineKeyboardButton("🖥️ Servidor", callback_data=f"edit_field_server_{client_id}")],
                [InlineKeyboardButton("📅 Vencimento", callback_data=f"edit_field_due_date_{client_id}")],
                [InlineKeyboardButton("📝 Informações Extras", callback_data=f"edit_field_other_info_{client_id}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data=f"client_{client_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing edit menu: {e}")
        await query.edit_message_text("❌ Erro ao carregar menu de edição.")

# Template management functions
def get_default_templates():
    """Get default message templates"""
    return {
        'welcome': {
            'name': 'Boas-vindas',
            'content': """🎉 Bem-vindo(a), {nome}!

📺 Seu plano {plano} foi ativado com sucesso!
💰 Valor: R$ {valor}
📅 Vencimento: {vencimento}
🖥️ Servidor: {servidor}

{informacoes_extras}

Obrigado pela confiança! 🙏"""
        },
        'reminder_2_days': {
            'name': 'Lembrete 2 dias antes',
            'content': """🔔 Lembrete - {nome}

📺 Seu plano {plano} vence em 2 dias.
📅 Data de vencimento: {vencimento}
💰 Valor: R$ {valor}

Para renovar, entre em contato conosco! 📱"""
        },
        'reminder_1_day': {
            'name': 'Lembrete 1 dia antes',
            'content': """⚠️ Atenção - {nome}

📺 Seu plano {plano} vence AMANHÃ!
📅 Data de vencimento: {vencimento}
💰 Valor: R$ {valor}

Renove hoje para evitar interrupção! 🚨"""
        },
        'reminder_due_date': {
            'name': 'Vencimento hoje',
            'content': """🚨 VENCIMENTO HOJE - {nome}

📺 Seu plano {plano} vence HOJE!
📅 Data de vencimento: {vencimento}
💰 Valor: R$ {valor}

Renove agora para manter o serviço ativo! ⏰"""
        },
        'reminder_overdue': {
            'name': 'Em atraso',
            'content': """❌ SERVIÇO EM ATRASO - {nome}

📺 Seu plano {plano} está vencido!
📅 Venceu em: {vencimento}
💰 Valor: R$ {valor}

Renove urgentemente para reativar! 🔄"""
        },
        'renewal': {
            'name': 'Renovação realizada',
            'content': """✅ Renovação Confirmada - {nome}

📺 Plano {plano} renovado com sucesso!
📅 Nova data de vencimento: {vencimento}
💰 Valor: R$ {valor}

Obrigado pela renovação! 🎉"""
        }
    }

def replace_template_variables(template_content, client):
    """Replace template variables with client data"""
    from datetime import date
    
    variables = {
        '{nome}': client.name,
        '{plano}': client.plan_name,
        '{valor}': f"{client.plan_price:.2f}",
        '{vencimento}': client.due_date.strftime('%d/%m/%Y'),
        '{servidor}': client.server or 'Não definido',
        '{informacoes_extras}': client.other_info or ''
    }
    
    # Replace all variables
    result = template_content
    for var, value in variables.items():
        result = result.replace(var, str(value))
    
    # Remove empty lines for informacoes_extras when empty
    if not client.other_info:
        result = result.replace('\n\n\n', '\n\n')
    
    return result.strip()

async def create_default_templates_in_db(user_id):
    """Create default templates in database for user"""
    try:
        db_service.create_default_templates(user_id)
        logger.info(f"Default templates created successfully for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating default templates for user {user_id}: {e}")
        return False

async def restore_default_templates_for_user(user_id):
    """Restore all default templates to original state"""
    try:
        db_service.restore_default_templates(user_id)
        logger.info(f"Default templates restored for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error restoring default templates for user {user_id}: {e}")
        return False

async def ensure_all_users_have_templates():
    """Ensure all existing users have default templates"""
    try:
        with db_service.get_session() as session:
            # Get all users
            users = session.query(User).all()
            
            for user in users:
                # Check if user has any templates
                template_count = session.query(MessageTemplate).filter_by(user_id=user.id).count()
                
                if template_count == 0:
                    logger.info(f"Creating default templates for existing user {user.id}")
                    await create_default_templates_in_db(user.id)
                    
        logger.info("Template verification completed for all users")
        return True
    except Exception as e:
        logger.error(f"Error ensuring templates for all users: {e}")
        return False

async def templates_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show templates management menu"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Create default templates if they don't exist
            await create_default_templates_in_db(db_user.id)
            
            text = """📝 *Gerenciar Templates*

📋 Gerencie suas mensagens automáticas:

🔧 *Variáveis disponíveis:*
• {nome} - Nome do cliente
• {plano} - Nome do plano  
• {valor} - Valor em R$
• {vencimento} - Data de vencimento
• {servidor} - Servidor do cliente
• {informacoes_extras} - Informações extras

📲 *Escolha uma opção:*"""
            
            keyboard = [
                [InlineKeyboardButton("📋 Ver Templates", callback_data="templates_list")],
                [InlineKeyboardButton("✏️ Editar Template", callback_data="templates_edit")],
                [InlineKeyboardButton("➕ Criar Template", callback_data="templates_create")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing templates menu: {e}")
        await query.edit_message_text("❌ Erro ao carregar menu de templates.")

async def templates_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of templates"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get all templates for user
            templates = session.query(MessageTemplate).filter_by(user_id=db_user.id).all()
            
            if not templates:
                await query.edit_message_text("❌ Nenhum template encontrado.")
                return
            
            text = "📋 *Seus Templates*\n\n"
            
            keyboard = []
            for template in templates:
                status = "✅" if template.is_active else "❌"
                text += f"{status} *{template.name}* ({template.template_type})\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"📝 {template.name}", 
                        callback_data=f"template_view_{template.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="templates_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        await query.edit_message_text("❌ Erro ao listar templates.")

async def template_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show individual template details"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            status = "✅ Ativo" if template.is_active else "❌ Inativo"
            
            text = f"""📝 *{template.name}*

🏷️ *Tipo:* {template.template_type}
📊 *Status:* {status}
📅 *Criado:* {template.created_at.strftime('%d/%m/%Y')}

📄 *Conteúdo:*
{template.content}"""
            
            keyboard = [
                [InlineKeyboardButton("✏️ Editar", callback_data=f"edit_template_{template.id}")],
                [InlineKeyboardButton("🔄 Ativar/Desativar", callback_data=f"toggle_template_{template.id}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="templates_list")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error viewing template: {e}")
        await query.edit_message_text("❌ Erro ao carregar template.")

async def toggle_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle template active status"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # Toggle status
            template.is_active = not template.is_active
            session.commit()
            
            status = "✅ Ativo" if template.is_active else "❌ Inativo"
            
            text = f"""📝 *{template.name}*

🏷️ *Tipo:* {template.template_type}
📊 *Status:* {status}
📅 *Criado:* {template.created_at.strftime('%d/%m/%Y')}

📄 *Conteúdo:*
{template.content}"""
            
            keyboard = [
                [InlineKeyboardButton("✏️ Editar", callback_data=f"edit_template_{template.id}")],
                [InlineKeyboardButton("🔄 Ativar/Desativar", callback_data=f"toggle_template_{template.id}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="templates_list")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error toggling template: {e}")
        await query.edit_message_text("❌ Erro ao alterar status do template.")

async def send_renewal_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send renewal message to client"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[3])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client and renewal template
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            template = session.query(MessageTemplate).filter_by(
                user_id=db_user.id, 
                template_type='renewal',
                is_active=True
            ).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            if not template:
                await query.edit_message_text("❌ Template de renovação não encontrado.")
                return
            
            # Replace variables and send message
            message_content = replace_template_variables(template.content, client)
            
            # Send via WhatsApp
            success = await whatsapp_service.send_message(client.phone_number, message_content, db_user.id)
            
            if success:
                # Log message
                message_log = MessageLog(
                    user_id=db_user.id,
                    client_id=client.id,
                    template_id=template.id,
                    message_content=message_content,
                    sent_at=datetime.now(),
                    status='sent'
                )
                session.add(message_log)
                session.commit()
                
                await query.edit_message_text(
                    f"✅ Mensagem de renovação enviada com sucesso!\n\n"
                    f"📱 **Cliente:** {client.name}\n"
                    f"📞 **Telefone:** {client.phone_number}\n"
                    f"📝 **Template:** {template.name}",
                    parse_mode='Markdown'
                )
                
                # Auto return to client list after 2 seconds
                import asyncio
                await asyncio.sleep(2)
                await back_to_clients_callback(update, context)
            else:
                await query.edit_message_text("❌ Erro ao enviar mensagem via WhatsApp.")
            
    except Exception as e:
        logger.error(f"Error sending renewal message: {e}")
        await query.edit_message_text("❌ Erro ao enviar mensagem de renovação.")

async def renewal_no_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle not sending renewal message"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("✅ Renovação concluída sem envio de mensagem.")
    
    # Auto return to client list after 1 second
    import asyncio
    await asyncio.sleep(1)
    await back_to_clients_callback(update, context)

async def renew_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client renewal - show renewal options"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Store client ID in context
            context.user_data['renew_client_id'] = client_id
            
            # Calculate suggested renewal date
            from datetime import date, timedelta
            
            if client.due_date < date.today():
                # If overdue, renew from today
                suggested_date = date.today() + timedelta(days=30)
            else:
                # If not overdue, renew from current due date
                suggested_date = client.due_date + timedelta(days=30)
            
            text = f"""
🔄 **Renovar Cliente: {client.name}**

📅 Vencimento atual: **{client.due_date.strftime('%d/%m/%Y')}**
📅 Data sugerida: **{suggested_date.strftime('%d/%m/%Y')}** (+30 dias)

🔧 **Escolha como renovar:**
"""
            
            # Create renewal options
            keyboard = [
                [InlineKeyboardButton("📅 Renovar por 30 dias", callback_data=f"renew_auto_{client_id}")],
                [InlineKeyboardButton("📝 Escolher data personalizada", callback_data=f"renew_custom_{client_id}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data=f"client_{client_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing renewal options: {e}")
        await query.edit_message_text("❌ Erro ao carregar opções de renovação.")

async def renew_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle automatic 30-day renewal"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Renew client for 30 days from current due date
            from datetime import date, timedelta
            
            old_due_date = client.due_date
            
            if client.due_date < date.today():
                # If overdue, renew from today
                new_due_date = date.today() + timedelta(days=30)
            else:
                # If not overdue, renew from current due date
                new_due_date = client.due_date + timedelta(days=30)
            
            client.due_date = new_due_date
            client.status = 'active'  # Reactivate if inactive
            session.commit()
            
            # Store client info for message sending
            context.user_data['renewed_client_id'] = client_id
            context.user_data['renewal_type'] = 'auto'
            
            text = f"""✅ Cliente **{client.name}** renovado automaticamente!

📅 **Antes:** {old_due_date.strftime('%d/%m/%Y')}
📅 **Agora:** {new_due_date.strftime('%d/%m/%Y')}
⏰ **Renovação:** +30 dias

🎉 **Dashboard atualizado com novas estatísticas!**

📲 **Deseja enviar mensagem de renovação via WhatsApp?**"""
            
            keyboard = [
                [InlineKeyboardButton("✅ Sim, enviar mensagem", callback_data=f"send_renewal_message_{client_id}")],
                [InlineKeyboardButton("📊 Ver Dashboard", callback_data="dashboard")],
                [InlineKeyboardButton("❌ Não enviar", callback_data="back_to_clients")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error auto-renewing client: {e}")
        await query.edit_message_text("❌ Erro ao renovar cliente automaticamente.")

async def renew_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom date renewal"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    # Extract client ID and store in context
    client_id = int(query.data.split('_')[2])
    context.user_data['renew_client_id'] = client_id
    
    text = """
📝 **Data Personalizada**

📅 Digite a nova data de vencimento no formato DD/MM/AAAA

**Exemplo:** 31/12/2024

Ou clique em 🏠 Menu Principal para cancelar.
"""
    
    await query.edit_message_text(text, parse_mode='Markdown')
    
    return RENEW_WAITING_CUSTOM_DATE

async def handle_renew_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom renewal date input"""
    if not update.message:
        return
        
    date_text = update.message.text.strip()
    
    # Check for cancel
    if date_text in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Renovação cancelada.", reply_markup=get_client_keyboard())
        return ConversationHandler.END
    
    try:
        from datetime import datetime, date
        new_due_date = datetime.strptime(date_text, '%d/%m/%Y').date()
        
        if new_due_date <= date.today():
            await update.message.reply_text("❌ Data deve ser futura. Digite uma data válida (DD/MM/AAAA):")
            return RENEW_WAITING_CUSTOM_DATE
    except ValueError:
        await update.message.reply_text("❌ Data inválida. Use o formato DD/MM/AAAA (ex: 31/12/2024):")
        return RENEW_WAITING_CUSTOM_DATE
    
    try:
        client_id = context.user_data.get('renew_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_due_date = client.due_date
                client.due_date = new_due_date
                client.status = 'active'  # Reactivate if inactive
                session.commit()
                
                # Store client info for message sending
                context.user_data['renewed_client_id'] = client_id
                context.user_data['renewal_type'] = 'custom'
                
                text = f"""✅ Cliente **{client.name}** renovado com data personalizada!

📅 **Antes:** {old_due_date.strftime('%d/%m/%Y')}
📅 **Agora:** {new_due_date.strftime('%d/%m/%Y')}
📝 **Renovação:** Data personalizada

🎉 **Dashboard atualizado com novas estatísticas!**

📲 **Deseja enviar mensagem de renovação via WhatsApp?**

Escolha uma opção:"""
                
                keyboard = [
                    [InlineKeyboardButton("✅ Sim, enviar mensagem", callback_data=f"send_renewal_message_{client_id}")],
                    [InlineKeyboardButton("📊 Ver Dashboard", callback_data="dashboard")],
                    [InlineKeyboardButton("❌ Não enviar", callback_data="renewal_no_message")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error custom renewing client: {e}")
        await update.message.reply_text("❌ Erro ao renovar cliente com data personalizada.")
    
    return ConversationHandler.END

async def message_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sending message to client - show template selection"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Get all active templates for user
            templates = session.query(MessageTemplate).filter_by(
                user_id=db_user.id,
                is_active=True
            ).all()
            
            if not templates:
                await query.edit_message_text(
                    f"❌ *Nenhum template ativo encontrado*\n\n"
                    f"📝 Crie templates primeiro para enviar mensagens personalizadas!\n\n"
                    f"👤 *Cliente:* {client.name}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")]
                    ]),
                    parse_mode='Markdown'
                )
                return
            
            text = f"📱 *Enviar Mensagem*\n\n👤 *Cliente:* {client.name}\n📞 *Telefone:* {client.phone_number}\n\n📋 *Selecione o template:*"
            
            keyboard = []
            for template in templates:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📝 {template.name}",
                        callback_data=f"send_template_to_{client_id}_{template.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing template selection: {e}")
        await query.edit_message_text("❌ Erro ao carregar templates.")

# Edit field callbacks
async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edit field selection"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Parse callback data: edit_field_fieldname_clientid
        parts = query.data.split('_')
        
        # Handle composite field names like "other_info" and "due_date"
        if len(parts) == 5:  # edit_field_other_info_{client_id} or edit_field_due_date_{client_id}
            field_name = f"{parts[2]}_{parts[3]}"
            client_id = int(parts[4])
        elif len(parts) == 4:  # edit_field_{field_name}_{client_id}
            field_name = parts[2]
            client_id = int(parts[3])
        else:
            logger.error(f"Invalid callback data format: {query.data}")
            await query.edit_message_text("❌ Erro no formato do callback.")
            return ConversationHandler.END
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client details
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Store edit context
            context.user_data['edit_client_id'] = client_id
            context.user_data['edit_field'] = field_name
            
            # Show appropriate prompt based on field
            field_prompts = {
                'name': f"✏️ **Editar Nome**\n\nNome atual: **{client.name}**\n\n📝 Digite o novo nome:",
                'phone': f"✏️ **Editar Telefone**\n\nTelefone atual: **{client.phone_number}**\n\n📱 Digite o novo telefone (apenas números com DDD):",
                'package': f"✏️ **Editar Plano**\n\nPlano atual: **{client.plan_name}**\n\n📦 Digite o novo nome do plano:",
                'price': f"✏️ **Editar Valor**\n\nValor atual: **R$ {client.plan_price:.2f}**\n\n💰 Digite o novo valor (ex: 50.00):",
                'server': f"✏️ **Editar Servidor**\n\nServidor atual: **{client.server or 'Não definido'}**\n\n🖥️ Escolha o novo servidor:",
                'due_date': f"✏️ **Editar Vencimento**\n\nVencimento atual: **{client.due_date.strftime('%d/%m/%Y')}**\n\n📅 Digite a nova data (DD/MM/AAAA):",
                'other_info': f"✏️ **Editar Informações Extras**\n\nInformações atuais: **{client.other_info or 'Nenhuma'}**\n\n📝 Digite as novas informações extras (ou 'pular' para remover):"
            }
            
            text = field_prompts.get(field_name, "Campo não reconhecido.")
            
            # Special handling for server field
            if field_name == 'server':
                keyboard = [
                    [KeyboardButton("🚀 FAST TV"), KeyboardButton("📺 EITV")],
                    [KeyboardButton("⚡ ZTECH"), KeyboardButton("🔵 UNITV")],
                    [KeyboardButton("✨ GENIAL"), KeyboardButton("🎯 SLIM PLAY")],
                    [KeyboardButton("📡 LIVE 21"), KeyboardButton("🔥 X SERVER")],
                    [KeyboardButton("🖥️ OUTRO SERVIDOR")],
                    [KeyboardButton("🏠 Menu Principal")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                
                await query.edit_message_text(text, parse_mode='Markdown')
                
                # Send a follow-up message with keyboard
                await query.message.reply_text("👆 Use os botões ou digite o nome do servidor:", reply_markup=reply_markup)
                
                return EDIT_WAITING_SERVER
            else:
                await query.edit_message_text(text, parse_mode='Markdown')
                
                # Return appropriate state
                state_map = {
                    'name': EDIT_WAITING_NAME,
                    'phone': EDIT_WAITING_PHONE,
                    'package': EDIT_WAITING_PACKAGE,
                    'price': EDIT_WAITING_PRICE,
                    'due_date': EDIT_WAITING_DUE_DATE,
                    'other_info': EDIT_WAITING_OTHER_INFO
                }
                
                return state_map.get(field_name, ConversationHandler.END)
                
    except Exception as e:
        logger.error(f"Error handling edit field: {e}")
        await query.edit_message_text("❌ Erro ao processar edição.")
        return ConversationHandler.END

# Edit handlers for each field
async def handle_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle name editing"""
    if not update.message:
        return
        
    new_name = update.message.text.strip()
    
    # Check for cancel
    if new_name in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    if len(new_name) < 2:
        await update.message.reply_text("❌ Nome muito curto. Digite um nome válido:")
        return EDIT_WAITING_NAME
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_name = client.name
                client.name = new_name
                session.commit()
                
                await update.message.reply_text(
                    f"✅ Nome atualizado com sucesso!\n\n"
                    f"**Antes:** {old_name}\n"
                    f"**Agora:** {new_name}",
                    parse_mode='Markdown'
                )
                
                # Return to client details after 2 seconds
                import asyncio
                await asyncio.sleep(2)
                
                # Simulate callback to return to client details
                context.user_data['edit_client_id'] = client_id
                
                # Show client details again
                from telegram import CallbackQuery
                mock_query = type('MockQuery', (), {
                    'answer': lambda: None,
                    'from_user': user,
                    'data': f'client_{client_id}',
                    'edit_message_text': update.message.reply_text,
                    'message': update.message
                })()
                
                mock_update = type('MockUpdate', (), {
                    'callback_query': mock_query,
                    'effective_user': user
                })()
                
                await client_details_callback(mock_update, context)
                
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing name: {e}")
        await update.message.reply_text("❌ Erro ao atualizar nome.")
    
    return ConversationHandler.END

async def handle_edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone editing"""
    if not update.message:
        return
        
    phone_number = update.message.text.strip()
    
    # Check for cancel
    if phone_number in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Validate phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) < 10 or len(clean_phone) > 11:
        await update.message.reply_text("❌ Número inválido. Digite apenas números com DDD (ex: 11999999999):")
        return EDIT_WAITING_PHONE
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_phone = client.phone_number
                client.phone_number = clean_phone
                session.commit()
                
                await update.message.reply_text(
                    f"✅ Telefone atualizado com sucesso!\n\n"
                    f"**Antes:** {old_phone}\n"
                    f"**Agora:** {clean_phone}",
                    parse_mode='Markdown',
                    reply_markup=get_client_keyboard()
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing phone: {e}")
        await update.message.reply_text("❌ Erro ao atualizar telefone.")
    
    return ConversationHandler.END

async def handle_edit_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle package editing"""
    if not update.message:
        return
        
    new_package = update.message.text.strip()
    
    # Check for cancel
    if new_package in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    if len(new_package) < 2:
        await update.message.reply_text("❌ Nome do plano muito curto. Digite um nome válido:")
        return EDIT_WAITING_PACKAGE
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_package = client.plan_name
                client.plan_name = new_package
                session.commit()
                
                await update.message.reply_text(
                    f"✅ Plano atualizado com sucesso!\n\n"
                    f"**Antes:** {old_package}\n"
                    f"**Agora:** {new_package}",
                    parse_mode='Markdown',
                    reply_markup=get_client_keyboard()
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing package: {e}")
        await update.message.reply_text("❌ Erro ao atualizar plano.")
    
    return ConversationHandler.END

async def handle_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price editing"""
    if not update.message:
        return
        
    price_text = update.message.text.strip()
    
    # Check for cancel
    if price_text in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    try:
        new_price = float(price_text.replace(',', '.').replace('R$', '').strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valor inválido. Digite um número válido (ex: 50.00):")
        return EDIT_WAITING_PRICE
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_price = client.plan_price
                client.plan_price = new_price
                session.commit()
                
                await update.message.reply_text(
                    f"✅ Valor atualizado com sucesso!\n\n"
                    f"**Antes:** R$ {old_price:.2f}\n"
                    f"**Agora:** R$ {new_price:.2f}",
                    parse_mode='Markdown',
                    reply_markup=get_client_keyboard()
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing price: {e}")
        await update.message.reply_text("❌ Erro ao atualizar valor.")
    
    return ConversationHandler.END

async def handle_edit_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle server editing"""
    if not update.message:
        return
        
    text = update.message.text.strip()
    
    # Check for cancel
    if text in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Extract server name from button text or use as-is
    server_mappings = {
        "🚀 FAST TV": "FAST TV",
        "📺 EITV": "EITV",
        "⚡ ZTECH": "ZTECH",
        "🔵 UNITV": "UNITV",
        "✨ GENIAL": "GENIAL",
        "🎯 SLIM PLAY": "SLIM PLAY",
        "📡 LIVE 21": "LIVE 21",
        "🔥 X SERVER": "X SERVER",
        "🖥️ OUTRO SERVIDOR": "OUTRO SERVIDOR"
    }
    
    new_server = server_mappings.get(text, text)
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_server = client.server or 'Não definido'
                client.server = new_server
                session.commit()
                
                await update.message.reply_text(
                    f"✅ Servidor atualizado com sucesso!\n\n"
                    f"**Antes:** {old_server}\n"
                    f"**Agora:** {new_server}",
                    parse_mode='Markdown',
                    reply_markup=get_client_keyboard()
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing server: {e}")
        await update.message.reply_text("❌ Erro ao atualizar servidor.")
    
    return ConversationHandler.END

async def handle_edit_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle due date editing"""
    if not update.message:
        return
        
    date_text = update.message.text.strip()
    
    # Check for cancel
    if date_text in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    try:
        from datetime import datetime, date
        new_due_date = datetime.strptime(date_text, '%d/%m/%Y').date()
        
        if new_due_date <= date.today():
            await update.message.reply_text("❌ Data deve ser futura. Digite uma data válida (DD/MM/AAAA):")
            return EDIT_WAITING_DUE_DATE
    except ValueError:
        await update.message.reply_text("❌ Data inválida. Use o formato DD/MM/AAAA (ex: 31/12/2024):")
        return EDIT_WAITING_DUE_DATE
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_due_date = client.due_date
                client.due_date = new_due_date
                session.commit()
                
                keyboard = [
                    [InlineKeyboardButton("📊 Ver Dashboard", callback_data="dashboard")],
                    [InlineKeyboardButton("👥 Ver Clientes", callback_data="manage_clients")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ Data de vencimento atualizada com sucesso!\n\n"
                    f"**Antes:** {old_due_date.strftime('%d/%m/%Y')}\n"
                    f"**Agora:** {new_due_date.strftime('%d/%m/%Y')}\n\n"
                    f"🎉 **Dashboard atualizado com novas estatísticas!**",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing due date: {e}")
        await update.message.reply_text("❌ Erro ao atualizar data de vencimento.")
    
    return ConversationHandler.END

async def handle_edit_other_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle other info editing"""
    if not update.message:
        return
        
    new_info = update.message.text.strip()
    
    # Check for cancel
    if new_info in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Edição cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    # Handle skip/remove
    if new_info.lower() in ['pular', 'skip', 'remover', 'remove', '']:
        new_info = None
    
    try:
        client_id = context.user_data.get('edit_client_id')
        user = update.effective_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if client:
                old_info = client.other_info or 'Nenhuma'
                client.other_info = new_info
                session.commit()
                
                new_info_display = new_info or 'Nenhuma'
                
                await update.message.reply_text(
                    f"✅ Informações extras atualizadas com sucesso!\n\n"
                    f"**Antes:** {old_info}\n"
                    f"**Agora:** {new_info_display}",
                    parse_mode='Markdown',
                    reply_markup=get_client_keyboard()
                )
            else:
                await update.message.reply_text("❌ Cliente não encontrado.")
                
    except Exception as e:
        logger.error(f"Error editing other info: {e}")
        await update.message.reply_text("❌ Erro ao atualizar informações extras.")
    
    return ConversationHandler.END

async def dashboard_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dashboard from keyboard"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
            
            # Get statistics
            total_clients = session.query(Client).filter_by(user_id=db_user.id).count()
            active_clients = session.query(Client).filter_by(user_id=db_user.id, status='active').count()
            
            # Get clients expiring soon
            today = date.today()
            expiring_soon = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date <= today + timedelta(days=7),
                Client.due_date >= today
            ).count()
            
            # Monthly statistics - current month
            from calendar import monthrange
            current_year = today.year
            current_month = today.month
            month_start = date(current_year, current_month, 1)
            month_end = date(current_year, current_month, monthrange(current_year, current_month)[1])
            
            # Monthly financial calculations - clients due this month
            clients_due_query = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date >= month_start,
                Client.due_date <= month_end
            )
            clients_to_pay = clients_due_query.count()
            
            # Calculate total revenue for the month (all clients due)
            monthly_revenue_total = sum(client.plan_price or 0 for client in clients_due_query.all())
            
            # Clients that already paid this month (due date passed)
            clients_paid_query = session.query(Client).filter(
                Client.user_id == db_user.id,
                Client.status == 'active',
                Client.due_date >= month_start,
                Client.due_date < today  # Already passed due date (paid)
            )
            clients_paid = clients_paid_query.count()
            
            # Calculate revenue from clients who already paid
            revenue_paid = sum(client.plan_price or 0 for client in clients_paid_query.all())
            
            # Revenue still to be collected
            revenue_pending = monthly_revenue_total - revenue_paid
            
            dashboard_text = f"""
📊 **Dashboard - Visão Geral**

👥 **Clientes:**
• Total: {total_clients}
• Ativos: {active_clients}
• Inativos: {total_clients - active_clients}

💰 **Mês Atual ({month_start.strftime('%m/%Y')}):**
• 📈 Pagos: {clients_paid} (R$ {revenue_paid:.2f})
• 📋 A Pagar: {clients_to_pay - clients_paid} (R$ {revenue_pending:.2f})
• 💵 Faturamento Total: R$ {monthly_revenue_total:.2f}

⏰ **Vencimentos:**
• Próximos 7 dias: {expiring_soon}

📱 **WhatsApp:**
• Status: {"✅ Conectado" if whatsapp_service.check_instance_status(db_user.id).get('connected') else "❌ Desconectado"}

💳 **Assinatura:**
• Status: {"🆓 Teste" if db_user.is_trial else "💎 Premium"}

📲 Use o teclado abaixo para navegar
"""
            
            reply_markup = get_main_keyboard()
            await update.message.reply_text(dashboard_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing dashboard: {e}")
        await update.message.reply_text("❌ Erro ao carregar dashboard.")

async def whatsapp_status_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle WhatsApp status from keyboard - SIMPLIFIED VERSION"""
    logger.info("📱 WhatsApp button pressed - checking status...")
    
    try:
        # Get user info
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado. Use /start para se registrar.")
                return
            
            status = whatsapp_service.check_instance_status(db_user.id)
            logger.info(f"WhatsApp status received: {status}")
            
            if status.get('success') and status.get('connected'):
                # Connected
                status_text = """✅ **WhatsApp Conectado**

🟢 Status: Conectado e funcionando
📱 Pronto para enviar mensagens automáticas"""
                
                keyboard = [[InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]]
                
            else:
                # Disconnected or error
                status_text = """❌ **WhatsApp Desconectado**

🔴 Status: Desconectado
📱 Escolha como conectar:"""
                
                keyboard = [
                    [InlineKeyboardButton("📱 QR Code", callback_data="whatsapp_reconnect")],
                    [InlineKeyboardButton("🔐 Código", callback_data="whatsapp_pairing_code")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in whatsapp_status_message: {e}")
        await update.message.reply_text("❌ Erro ao verificar status do WhatsApp.")

async def templates_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle templates menu message command"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    logger.info(f"Templates menu called by user {user.id}")
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
                
            if not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Create default templates if they don't exist
            try:
                await create_default_templates_in_db(db_user.id)
            except Exception as e:
                logger.error(f"Error creating default templates: {e}")
                # Continue without failing
            
            text = "TEMPLATES\n\nEscolha uma opcao:"
            
            logger.info("Creating simple templates keyboard...")
            keyboard = [
                [InlineKeyboardButton("Ver Templates", callback_data="templates_list")],
                [InlineKeyboardButton("Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.info(f"Sending templates menu with {len(keyboard)} button rows...")
            await update.message.reply_text(text, reply_markup=reply_markup)
            logger.info("Templates menu sent successfully")
            
    except Exception as e:
        logger.error(f"Error showing templates menu: {e}")
        try:
            await update.message.reply_text("❌ Erro ao carregar menu de templates.")
        except:
            pass

async def templates_list_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle templates list from keyboard - Show template list with inline buttons"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
                
            if not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Get all templates ordered by name
            templates = session.query(MessageTemplate).filter_by(user_id=db_user.id).order_by(MessageTemplate.name).all()
            
            if not templates:
                text = """📋 LISTA DE TEMPLATES

📋 Nenhum template encontrado ainda.

Use 'Criar Template' para criar seu primeiro template!"""
                keyboard = [
                    [InlineKeyboardButton("➕ Criar Template", callback_data="template_create_new")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(text, reply_markup=reply_markup)
                return
            
            # Create template list with buttons
            text = f"""📋 LISTA DE TEMPLATES

📝 Total: {len(templates)} templates

👆 Clique em um template para ver opções:"""
            
            keyboard = []
            for template in templates:
                status = "✅" if template.is_active else "❌"
                button_text = f"{status} {template.name} ({template.template_type})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"template_{template.id}")])
            
            # Add action buttons
            keyboard.append([InlineKeyboardButton("➕ Criar Template", callback_data="template_create_new")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error showing templates list: {e}")
        await update.message.reply_text("❌ Erro ao carregar lista de templates.")

async def templates_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle templates edit from keyboard"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
                
            if not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Get all templates
            templates = session.query(MessageTemplate).filter_by(user_id=db_user.id).order_by(MessageTemplate.name).all()
            
            if not templates:
                text = "✏️ EDITAR TEMPLATES\n\nNenhum template encontrado para edição.\n\nUse 'Criar Template' primeiro."
            else:
                text = "✏️ EDITAR TEMPLATES\n\nSelecione um template para editar:\n\n"
                for i, template in enumerate(templates, 1):
                    status = "✅" if template.is_active else "❌"
                    text += f"{i}. {status} {template.name}\n"
                    text += f"   Tipo: {template.template_type}\n\n"
                text += "Digite o número do template que deseja editar:"
            
            await update.message.reply_text(text)
            
    except Exception as e:
        logger.error(f"Error showing templates edit: {e}")
        await update.message.reply_text("❌ Erro ao carregar edição de templates.")

async def templates_create_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle templates create from keyboard"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
                
            if not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            text = """➕ CRIAR TEMPLATE

📝 Digite as informações do template no formato:

TIPO|NOME|CONTEUDO

Tipos disponíveis:
- welcome (boas-vindas)
- reminder_2_days (lembrete 2 dias)
- reminder_1_day (lembrete 1 dia)  
- reminder_due_date (lembrete vencimento)
- reminder_overdue (lembrete em atraso)
- renewal (renovação)

Variáveis disponíveis:
{nome}, {plano}, {valor}, {vencimento}, {servidor}, {informacoes_extras}

Exemplo:
welcome|Boas-vindas|Olá {nome}! Bem-vindo ao {plano}."""
            
            await update.message.reply_text(text)
            
    except Exception as e:
        logger.error(f"Error showing templates create: {e}")
        await update.message.reply_text("❌ Erro ao carregar criação de templates.")

async def template_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template details callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[1])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            status = "✅ Ativo" if template.is_active else "❌ Inativo"
            
            # Determine if it's a system template (default templates)
            is_system_template = template.template_type in [
                'welcome', 'reminder_2_days', 'reminder_1_day', 
                'reminder_due_date', 'reminder_overdue', 'renewal'
            ]
            
            # Escape special characters in template content for display
            content_display = template.content.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace('`', '\\`')
            
            text = f"""📝 DETALHES DO TEMPLATE

🏷️ Nome: {template.name}
🔧 Tipo: {template.template_type}
📊 Status: {status}
🖥️ Sistema: {'Sim' if is_system_template else 'Não'}

📄 Conteúdo:
{content_display}

🔧 Opções disponíveis:"""
            
            keyboard = [
                [InlineKeyboardButton("📝 Editar", callback_data=f"template_edit_{template.id}")],
                [InlineKeyboardButton("🔄 Ativar/Desativar", callback_data=f"template_toggle_{template.id}")],
                [InlineKeyboardButton("📤 Enviar para Cliente", callback_data=f"template_send_{template.id}")],
                [InlineKeyboardButton("📋 Copiar", callback_data=f"template_copy_{template.id}")]
            ]
            
            # Only add delete button for non-system templates
            if not is_system_template:
                keyboard.append([InlineKeyboardButton("🗑️ Excluir", callback_data=f"template_delete_{template.id}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Lista Templates", callback_data="back_to_templates")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error showing template details: {e}")
        await query.edit_message_text("❌ Erro ao carregar detalhes do template.")

async def back_to_templates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to templates list callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    # Simulate message for templates_list_message function
    class MockUpdate:
        def __init__(self, query):
            self.effective_user = query.from_user
            self.message = query.message
            
    mock_update = MockUpdate(query)
    
    try:
        user = query.from_user
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get all templates ordered by name
            templates = session.query(MessageTemplate).filter_by(user_id=db_user.id).order_by(MessageTemplate.name).all()
            
            if not templates:
                text = """📋 LISTA DE TEMPLATES

📋 Nenhum template encontrado ainda.

Use 'Criar Template' para criar seu primeiro template!"""
                keyboard = [
                    [InlineKeyboardButton("➕ Criar Template", callback_data="template_create_new")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup)
                return
            
            # Create template list with buttons
            text = f"""📋 LISTA DE TEMPLATES

📝 Total: {len(templates)} templates

👆 Clique em um template para ver opções:"""
            
            keyboard = []
            for template in templates:
                status = "✅" if template.is_active else "❌"
                button_text = f"{status} {template.name} ({template.template_type})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"template_{template.id}")])
            
            # Add action buttons
            keyboard.append([InlineKeyboardButton("➕ Criar Template", callback_data="template_create_new")])
            keyboard.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error returning to templates list: {e}")
        await query.edit_message_text("❌ Erro ao carregar lista de templates.")

async def template_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template toggle active/inactive callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # Toggle status
            template.is_active = not template.is_active
            session.commit()
            
            status_text = "ativado" if template.is_active else "desativado"
            await query.edit_message_text(f"✅ Template '{template.name}' foi {status_text} com sucesso!")
            
    except Exception as e:
        logger.error(f"Error toggling template: {e}")
        await query.edit_message_text("❌ Erro ao alterar status do template.")

async def template_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template delete callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # Check if it's a system template
            is_system_template = template.template_type in [
                'welcome', 'reminder_2_days', 'reminder_1_day', 
                'reminder_due_date', 'reminder_overdue', 'renewal'
            ]
            
            if is_system_template:
                await query.edit_message_text("❌ Templates do sistema não podem ser excluídos.")
                return
            
            # Delete template
            template_name = template.name
            session.delete(template)
            session.commit()
            
            await query.edit_message_text(f"🗑️ Template '{template_name}' foi excluído com sucesso!")
            
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        await query.edit_message_text("❌ Erro ao excluir template.")

async def template_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template send to client callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # Get user's clients
            clients = session.query(Client).filter_by(user_id=db_user.id, status='active').all()
            
            if not clients:
                await query.edit_message_text("❌ Nenhum cliente ativo encontrado para enviar o template.")
                return
            
            text = f"""📤 ENVIAR TEMPLATE: {template.name}

👥 Selecione um cliente para enviar o template:"""
            
            keyboard = []
            for client in clients:
                keyboard.append([InlineKeyboardButton(
                    f"📱 {client.name}", 
                    callback_data=f"send_template_to_{client.id}_{template_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 Detalhes Template", callback_data=f"template_{template.id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error showing template send options: {e}")
        await query.edit_message_text("❌ Erro ao carregar opções de envio.")

async def send_template_to_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle send template to specific client callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client and template IDs from callback data
        parts = query.data.split('_')
        client_id = int(parts[3])
        template_id = int(parts[4])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client and template
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            template = session.query(MessageTemplate).filter_by(id=template_id, user_id=db_user.id).first()
            
            if not client or not template:
                await query.edit_message_text("❌ Cliente ou template não encontrado.")
                return
            
            # Prepare template content with variables
            message_content = template.content
            
            # Replace variables in template
            variables = {
                '{nome}': client.name,
                '{plano}': client.plan_name or 'Não informado',
                '{valor}': f"R$ {client.plan_price:.2f}" if client.plan_price else 'Não informado',
                '{vencimento}': client.due_date.strftime('%d/%m/%Y'),
                '{servidor}': client.server or 'Não informado',
                '{informacoes_extras}': client.other_info or 'N/A'
            }
            
            for var, value in variables.items():
                message_content = message_content.replace(var, value)
            
            # Send WhatsApp message
            from services.whatsapp_service import whatsapp_service
            
            success = whatsapp_service.send_message(client.phone_number, message_content, db_user.id)
            
            if success:
                # Log the message
                message_log = MessageLog(
                    user_id=db_user.id,
                    client_id=client.id,
                    template_type=template.template_type,
                    recipient_phone=client.phone_number,
                    message_content=message_content,
                    status='sent'
                )
                session.add(message_log)
                session.commit()
                
                await query.edit_message_text(f"✅ Template '{template.name}' enviado para {client.name} com sucesso!")
            else:
                await query.edit_message_text(f"❌ Falha ao enviar template para {client.name}. Verifique a conexão WhatsApp.")
            
    except Exception as e:
        logger.error(f"Error sending template to client: {e}")
        await query.edit_message_text("❌ Erro ao enviar template.")

async def template_create_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle create new template callback - Step 1: Ask for name"""
    
    if not update.callback_query:
        logger.error("DEBUG: No callback_query in update")
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    logger.warning(f"DEBUG: Processing template creation for user {user.id}")
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                logger.error(f"DEBUG: User {user.id} not found in database")
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
                
            if not db_user.is_active:
                logger.error(f"DEBUG: User {user.id} account inactive")
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            logger.warning(f"DEBUG: User {user.id} validated, showing step 1")
            
            text = """➕ CRIAR NOVO TEMPLATE - Etapa 1/3

📝 Digite o nome do template:

⚠️ Não clique nos botões do menu abaixo - apenas digite o nome!

❌ Digite 'cancelar' para cancelar a criação."""
            
            # Edit the inline message without changing keyboard
            await query.edit_message_text(text)
            
            # Initialize template creation state
            context.user_data['creating_template_step'] = 'name'
            context.user_data['template_data'] = {}
            
            logger.warning(f"DEBUG: Template creation initialized for user {user.id}, step=name")
            
    except Exception as e:
        logger.error(f"CRITICAL ERROR in template_create_new_callback: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        try:
            await query.edit_message_text("❌ Erro ao iniciar criação do template.")
        except:
            logger.error("Failed to send error message to user")

async def process_template_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process step-by-step template creation"""
    logger.warning(f"DEBUG: process_template_creation called with text='{text}' for user {update.effective_user.id if update.effective_user else 'Unknown'}")
    
    if not update.effective_user:
        logger.error("DEBUG: No effective_user in update")
        return
        
    user = update.effective_user
    
    step = context.user_data.get('creating_template_step')
    logger.warning(f"DEBUG: Current step='{step}' for user {user.id}")
    
    try:
        # Define botões do teclado persistente que devem ser ignorados
        keyboard_buttons = [
            "👥 Clientes", "📊 Dashboard", "📱 WhatsApp", "💳 Assinatura", 
            "📋 Ver Templates", "⏰ Horários", "➕ Adicionar Cliente", 
            "❓ Ajuda", "🏠 Menu Principal", "📋 Ver Clientes", "🚀 PAGAMENTO ANTECIPADO"
        ]
        
        # Check if user clicked a keyboard button instead of typing
        if text in keyboard_buttons:
            await update.message.reply_text("❌ Por favor, digite o nome do template (não clique nos botões do menu).")
            return
        
        # Check if user wants to cancel
        if text.lower() == 'cancelar':
            context.user_data.pop('creating_template_step', None)
            context.user_data.pop('template_data', None)
            # Restore main keyboard
            reply_markup = get_main_keyboard()
            await update.message.reply_text("❌ Criação de template cancelada.", reply_markup=reply_markup)
            return
            
        step = context.user_data.get('creating_template_step')
        template_data = context.user_data.get('template_data', {})
        
        if step == 'name':
            # Step 1: Store name and move to type selection
            name = text.strip()
            if not name:
                await update.message.reply_text("❌ Nome não pode estar vazio. Digite o nome do template:")
                return
            
            # Store name and move to type selection
            template_data['name'] = name
            context.user_data['template_data'] = template_data
            context.user_data['creating_template_step'] = 'type'
            
            # Show type selection buttons
            await show_template_type_selection(update, name)
            
        elif step == 'content':
            # Step 3: Store content and create template
            content = text.strip()
            if not content:
                await update.message.reply_text("❌ Conteúdo não pode estar vazio. Digite o conteúdo do template:")
                return
            
            template_data['content'] = content
            
            # Create the template
            await create_template_final(update, context, template_data)
            
    except Exception as e:
        logger.error(f"Error processing template creation: {e}")
        # Clear creation state on error
        context.user_data.pop('creating_template_step', None)
        context.user_data.pop('template_data', None)
        # Restore main keyboard
        reply_markup = get_main_keyboard()
        await update.message.reply_text("❌ Erro ao processar criação do template.", reply_markup=reply_markup)

async def show_template_type_selection(update: Update, template_name: str):
    """Show template type selection buttons - Step 2"""
    text = f"""➕ CRIAR NOVO TEMPLATE - Etapa 2/3

📝 Nome: {template_name}

🏷️ Selecione o tipo do template:"""
    
    keyboard = [
        [InlineKeyboardButton("🎉 Boas-vindas", callback_data="template_type_welcome")],
        [InlineKeyboardButton("📅 Lembrete 2 dias antes", callback_data="template_type_reminder_2days")],
        [InlineKeyboardButton("⏰ Lembrete 1 dia antes", callback_data="template_type_reminder_1day")],
        [InlineKeyboardButton("🚨 Lembrete no vencimento", callback_data="template_type_reminder_due")],
        [InlineKeyboardButton("❌ Lembrete após vencimento", callback_data="template_type_reminder_overdue")],
        [InlineKeyboardButton("✅ Renovação confirmada", callback_data="template_type_renewal")],
        [InlineKeyboardButton("🔧 Personalizado", callback_data="template_type_custom")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="template_type_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def template_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template type selection"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        callback_data = query.data
        
        if callback_data == "template_type_cancel":
            context.user_data.pop('creating_template_step', None)
            context.user_data.pop('template_data', None)
            await query.edit_message_text("❌ Criação de template cancelada.")
            return
        
        # Extract template type from callback data
        template_type = callback_data.replace("template_type_", "")
        
        # Store template type
        template_data = context.user_data.get('template_data', {})
        template_data['type'] = template_type
        context.user_data['template_data'] = template_data
        context.user_data['creating_template_step'] = 'content'
        
        # Show content input with variables
        await show_template_content_input(query, template_data['name'], template_type)
        
    except Exception as e:
        logger.error(f"Error in template type callback: {e}")
        await query.edit_message_text("❌ Erro ao selecionar tipo do template.")
        context.user_data.pop('creating_template_step', None)
        context.user_data.pop('template_data', None)

async def show_template_content_input(query, template_name: str, template_type: str):
    """Show template content input - Step 3"""
    type_names = {
        'welcome': 'Boas-vindas',
        'reminder_2days': 'Lembrete 2 dias antes',
        'reminder_1day': 'Lembrete 1 dia antes',
        'reminder_due': 'Lembrete no vencimento',
        'reminder_overdue': 'Lembrete após vencimento',
        'renewal': 'Renovação confirmada',
        'custom': 'Personalizado'
    }
    
    text = f"""➕ CRIAR NOVO TEMPLATE - Etapa 3/3

📝 Nome: {template_name}
🏷️ Tipo: {type_names.get(template_type, template_type)}

📄 Digite o conteúdo do template:

💡 **Variáveis disponíveis** (copie e cole):
• `{{nome}}` - Nome do cliente
• `{{plano}}` - Plano do cliente  
• `{{valor}}` - Valor da mensalidade
• `{{vencimento}}` - Data de vencimento
• `{{servidor}}` - Servidor do cliente
• `{{informacoes_extras}}` - Informações extras

❌ Digite 'cancelar' para cancelar a criação."""
    
    await query.edit_message_text(text)

async def create_template_final(update: Update, context: ContextTypes.DEFAULT_TYPE, template_data: dict):
    """Create the final template in database"""
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Create new template
            new_template = MessageTemplate(
                user_id=db_user.id,
                name=template_data['name'],
                template_type=template_data['type'],
                content=template_data['content'],
                is_active=True
            )
            
            session.add(new_template)
            session.commit()
            
            # Clear creation state
            context.user_data.pop('creating_template_step', None)
            context.user_data.pop('template_data', None)
            
            # Restore main keyboard
            reply_markup = get_main_keyboard()
            await update.message.reply_text(f"✅ Template '{template_data['name']}' criado com sucesso!", reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error creating final template: {e}")
        # Clear creation state on error
        context.user_data.pop('creating_template_step', None)
        context.user_data.pop('template_data', None)
        # Restore main keyboard
        reply_markup = get_main_keyboard()
        await update.message.reply_text("❌ Erro ao criar template.", reply_markup=reply_markup)

async def template_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template edit callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # Check if template is a default template (protected)
            if getattr(template, 'is_default', False):
                text = f"""🔒 TEMPLATE PADRÃO PROTEGIDO: {template.name}

⚠️ Este é um template padrão que não pode ser editado para preservar sua integridade.

📋 Para personalizar, use uma das opções:
• 📝 Criar novo template baseado neste
• 📋 Copiar conteúdo para uso manual

🔧 Tipo: {template.template_type}
📄 Conteúdo original:
{template.content}"""
                
                keyboard = [
                    [InlineKeyboardButton("📝 Criar Baseado Neste", callback_data=f"template_copy_{template_id}")],
                    [InlineKeyboardButton("🔙 Voltar aos Templates", callback_data="templates_list")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup)
                return
            
            text = f"""📝 EDITAR TEMPLATE: {template.name}

🔧 Tipo atual: {template.template_type}
📄 Conteúdo atual:
{template.content}

Digite o novo conteúdo para o template ou 'cancelar' para cancelar:"""
            
            await query.edit_message_text(text)
            
            # Store editing state
            context.user_data['editing_template'] = template_id
            
    except Exception as e:
        logger.error(f"Error starting template edit: {e}")
        await query.edit_message_text("❌ Erro ao iniciar edição do template.")

async def template_copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template copy callback - Send template content as text message"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return
            
            # If template is default, create a copy as new custom template
            if getattr(template, 'is_default', False):
                # Create a new template based on the default one
                new_name = f"Cópia de {template.name}"
                new_template = MessageTemplate(
                    user_id=db_user.id,
                    name=new_name,
                    template_type='custom',  # Mark as custom type
                    content=template.content,
                    is_active=True,
                    is_default=False  # Make sure it's not marked as default
                )
                
                session.add(new_template)
                session.commit()
                
                text = f"""✅ TEMPLATE COPIADO COM SUCESSO!

📝 Novo template criado: "{new_name}"
🔧 Tipo: Personalizado
📄 Conteúdo: Baseado no template "{template.name}"

🎯 Agora você pode editar este template personalizado livremente!

💡 Variáveis disponíveis:
• {{client_name}} - Nome do cliente
• {{plan_name}} - Plano do cliente  
• {{plan_price}} - Valor da mensalidade
• {{due_date}} - Data de vencimento
• {{server}} - Servidor do cliente
• {{other_info}} - Informações extras"""
                
                keyboard = [
                    [InlineKeyboardButton("✏️ Editar Agora", callback_data=f"template_edit_{new_template.id}")],
                    [InlineKeyboardButton("📋 Ver Templates", callback_data="templates_list")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                # Send template content as a separate message for easy copying
                copy_message = f"""📋 CONTEÚDO DO TEMPLATE: {template.name}

{template.content}

📝 Você pode copiar o texto acima e editar como quiser!

💡 Variáveis disponíveis:
• {{client_name}} - Nome do cliente
• {{plan_name}} - Plano do cliente  
• {{plan_price}} - Valor da mensalidade
• {{due_date}} - Data de vencimento
• {{server}} - Servidor do cliente
• {{other_info}} - Informações extras"""
                
                # Send as new message to make copying easier
                await query.message.reply_text(copy_message)
                
                # Also update the current message to show success
                await query.edit_message_text(f"✅ Conteúdo do template '{template.name}' copiado para o chat acima!")
            
    except Exception as e:
        logger.error(f"Error copying template: {e}")
        await query.edit_message_text("❌ Erro ao copiar template.")

async def process_template_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process template edit from user input"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        if text.lower() == 'cancelar':
            context.user_data.pop('editing_template', None)
            await update.message.reply_text("❌ Edição cancelada.")
            return
        
        template_id = context.user_data.get('editing_template')
        if not template_id:
            return
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await update.message.reply_text("❌ Template não encontrado.")
                return
            
            # Update template content
            template.content = text
            session.commit()
            
            # Clear editing state
            context.user_data.pop('editing_template', None)
            
            await update.message.reply_text(f"✅ Template '{template.name}' atualizado com sucesso!")
            
    except Exception as e:
        logger.error(f"Error editing template: {e}")
        await update.message.reply_text("❌ Erro ao editar template.")
        # Clear editing state on error
        context.user_data.pop('editing_template', None)

async def subscription_info_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription info from keyboard"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return
            
            # Get subscription info
            trial_days_left = 0
            if db_user.is_trial and db_user.trial_end_date:
                trial_days_left = max(0, (db_user.trial_end_date - datetime.utcnow()).days)
            
            subscription_days_left = 0
            if db_user.next_due_date:
                subscription_days_left = max(0, (db_user.next_due_date - datetime.utcnow()).days)
            
            if db_user.is_trial:
                status_text = f"""
💳 **Informações da Assinatura**

🎁 **Período de Teste Ativo**
📅 Dias restantes: **{trial_days_left}**

💎 **Plano Premium - R$ 20,00/mês**

✅ **Funcionalidades incluídas:**
• Gestão ilimitada de clientes
• Lembretes automáticos via WhatsApp  
• Controle de vencimentos
• Templates personalizáveis
• Suporte prioritário

{"⚠️ **Seu teste expira em breve!**" if trial_days_left <= 2 else ""}

📲 Use o teclado abaixo para navegar
"""
            else:
                status_text = f"""
💳 **Informações da Assinatura**

💎 **Plano Premium Ativo**
💰 Valor: R$ 20,00/mês
📅 Próximo vencimento: {db_user.next_due_date.strftime('%d/%m/%Y') if db_user.next_due_date else 'N/A'}
⏰ Dias restantes: {subscription_days_left}

✅ **Status:** {'Ativa' if db_user.is_active else 'Inativa'}

📲 Use o teclado abaixo para navegar
"""
            
            reply_markup = get_main_keyboard()
            await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing subscription info: {e}")
        await update.message.reply_text("❌ Erro ao carregar informações da assinatura.")

async def add_client_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add client from keyboard"""
    text = """
➕ **Adicionar Cliente**

Vamos cadastrar um novo cliente! 

Por favor, envie o **nome do cliente**:

💡 _Digite /cancel ou "Cancelar" a qualquer momento para voltar ao menu._
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
    return WAITING_CLIENT_NAME

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the Telegram bot"""
    try:
        # Initialize database
        logger.info("Initializing database...")
        db_service.create_tables()
        
        # Start scheduler service
        logger.info("Starting scheduler service...")
        scheduler_service.start()
        
        # Create application
        application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        # Register conversation handlers
        user_registration_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                WAITING_FOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)]
            },
            fallbacks=[CommandHandler("start", start_command)],
            per_message=False
        )
        
        client_addition_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(add_client_callback, pattern="^add_client$"),
                MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), add_client_message)
            ],
            states={
                WAITING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_name)],
                WAITING_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_phone)],
                WAITING_CLIENT_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_package)],
                WAITING_CLIENT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_plan)],
                WAITING_CLIENT_PRICE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_price_selection)],
                WAITING_CLIENT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_price)],
                WAITING_CLIENT_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_server)],
                WAITING_CLIENT_DUE_DATE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_due_date_selection)],
                WAITING_CLIENT_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_due_date)],
                WAITING_CLIENT_OTHER_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_other_info)],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_conversation),
                CommandHandler("start", start_command),
                CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
                MessageHandler(filters.Regex("^(🔙 Cancelar|Cancelar|cancelar|CANCELAR|/cancel|🏠 Menu Principal|🔙 Voltar)$"), cancel_conversation)
            ]
        )
        
        # Edit client conversation handler
        edit_client_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(edit_field_callback, pattern="^edit_field_")
            ],
            states={
                EDIT_WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_name)],
                EDIT_WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_phone)],
                EDIT_WAITING_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_package)],
                EDIT_WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_price)],
                EDIT_WAITING_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_server)],
                EDIT_WAITING_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_due_date)],
                EDIT_WAITING_OTHER_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_other_info)],
            },
            fallbacks=[CallbackQueryHandler(main_menu_callback, pattern="^main_menu$")],
            per_message=False
        )
        
        # Renew client conversation handler
        renew_client_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(renew_custom_callback, pattern="^renew_custom_")
            ],
            states={
                RENEW_WAITING_CUSTOM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_renew_custom_date)],
            },
            fallbacks=[CallbackQueryHandler(main_menu_callback, pattern="^main_menu$")],
            per_message=False
        )
        
        # Schedule configuration conversation handler
        schedule_settings_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(set_morning_time_callback, pattern="^set_morning_time$"),
                CallbackQueryHandler(set_report_time_callback, pattern="^set_report_time$")
            ],
            states={
                SCHEDULE_WAITING_MORNING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_morning_time)],
                SCHEDULE_WAITING_REPORT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_report_time)],
            },
            fallbacks=[CallbackQueryHandler(schedule_settings_callback, pattern="^schedule_settings$")],
            per_message=False
        )
        
        # Register conversation handlers FIRST (highest priority)
        application.add_handler(user_registration_handler)
        application.add_handler(client_addition_handler)
        application.add_handler(edit_client_handler)
        application.add_handler(renew_client_handler)
        application.add_handler(schedule_settings_handler)
        
        # Command handlers
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("ajuda", help_command))
        
        # Keyboard button handlers (specific patterns)
        keyboard_patterns = [
            "^👥 Clientes$",
            "^📊 Dashboard$", 
            "^📱 WhatsApp$",
            "^💳 Assinatura$",
            "^📋 Ver Templates$",
            "^⏰ Horários$",
            "^❓ Ajuda$",
            "^🏠 Menu Principal$",
            "^📋 Ver Clientes$",
            "^🚀 PAGAMENTO ANTECIPADO$"
        ]
        
        for pattern in keyboard_patterns:
            application.add_handler(MessageHandler(filters.Regex(pattern), handle_keyboard_buttons))
        
        # Add a general text handler to catch all text messages (including template creation)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_buttons))
        
        # NOTE: ConversationHandlers now have priority over other text handlers
        
        # Callback query handlers (for backwards compatibility)
        application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
        application.add_handler(CallbackQueryHandler(subscription_info_callback, pattern="^subscription_info$"))
        application.add_handler(CallbackQueryHandler(manage_clients_callback, pattern="^manage_clients$"))
        application.add_handler(CallbackQueryHandler(search_client_callback, pattern="^search_client$"))
        
        # NEW HANDLERS - Add FIRST for priority
        application.add_handler(CallbackQueryHandler(view_sending_queue_callback, pattern="^view_sending_queue$"))
        application.add_handler(CallbackQueryHandler(cancel_specific_sending_callback, pattern="^cancel_specific_sending$"))
        application.add_handler(CallbackQueryHandler(disable_reminders_callback, pattern="^disable_reminders_\\d+$"))
        
        # Settings and schedule settings handlers  
        application.add_handler(CallbackQueryHandler(settings_callback, pattern="^settings$"))
        application.add_handler(CallbackQueryHandler(reset_schedule_callback, pattern="^reset_schedule$"))
        application.add_handler(CallbackQueryHandler(schedule_settings_callback, pattern="^schedule_settings$"))
        application.add_handler(CallbackQueryHandler(toggle_auto_send_on_callback, pattern="^toggle_auto_send_on$"))
        application.add_handler(CallbackQueryHandler(toggle_auto_send_off_callback, pattern="^toggle_auto_send_off$"))
        application.add_handler(CallbackQueryHandler(toggle_client_reminders_callback, pattern="^toggle_reminders_\\d+$"))
        
        # Client management callbacks
        application.add_handler(CallbackQueryHandler(client_details_callback, pattern="^client_\\d+$"))
        application.add_handler(CallbackQueryHandler(back_to_clients_callback, pattern="^back_to_clients$"))
        application.add_handler(CallbackQueryHandler(delete_client_callback, pattern="^delete_\\d+$"))
        application.add_handler(CallbackQueryHandler(archive_client_callback, pattern="^archive_\\d+$"))
        application.add_handler(CallbackQueryHandler(edit_client_callback, pattern="^edit_\\d+$"))
        application.add_handler(CallbackQueryHandler(renew_client_callback, pattern="^renew_\\d+$"))
        application.add_handler(CallbackQueryHandler(renew_auto_callback, pattern="^renew_auto_\\d+$"))
        application.add_handler(CallbackQueryHandler(message_client_callback, pattern="^message_\\d+$"))
        
        # Template management callbacks
        application.add_handler(CallbackQueryHandler(templates_menu_callback, pattern="^templates_menu$"))
        application.add_handler(CallbackQueryHandler(templates_list_callback, pattern="^templates_list$"))
        application.add_handler(CallbackQueryHandler(template_view_callback, pattern="^template_view_\\d+$"))
        application.add_handler(CallbackQueryHandler(toggle_template_callback, pattern="^toggle_template_\\d+$"))
        application.add_handler(CallbackQueryHandler(template_details_callback, pattern="^template_\\d+$"))
        application.add_handler(CallbackQueryHandler(back_to_templates_callback, pattern="^back_to_templates$"))
        application.add_handler(CallbackQueryHandler(template_toggle_callback, pattern="^template_toggle_\\d+$"))
        application.add_handler(CallbackQueryHandler(template_delete_callback, pattern="^template_delete_\\d+$"))
        application.add_handler(CallbackQueryHandler(template_send_callback, pattern="^template_send_\\d+$"))
        application.add_handler(CallbackQueryHandler(send_template_to_client_callback, pattern="^send_template_to_\\d+_\\d+$"))
        application.add_handler(CallbackQueryHandler(template_create_new_callback, pattern="^template_create_new$"))
        application.add_handler(CallbackQueryHandler(template_type_callback, pattern="^template_type_.*$"))
        application.add_handler(CallbackQueryHandler(template_edit_callback, pattern="^template_edit_\\d+$"))
        application.add_handler(CallbackQueryHandler(template_copy_callback, pattern="^template_copy_\\d+$"))
        
        # Template handlers already implemented above - no external imports needed
        
        # Payment system handlers
        from handlers.user_handlers import subscribe_now_callback, check_payment_callback
        application.add_handler(CallbackQueryHandler(subscribe_now_callback, pattern="^subscribe_now$"))
        application.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_payment_.*$"))

        # Other callbacks
        application.add_handler(CallbackQueryHandler(dashboard_callback, pattern="^dashboard$"))
        application.add_handler(CallbackQueryHandler(whatsapp_status_callback, pattern="^whatsapp_status$"))
        application.add_handler(CallbackQueryHandler(whatsapp_disconnect_callback, pattern="^whatsapp_disconnect$"))
        application.add_handler(CallbackQueryHandler(whatsapp_reconnect_callback, pattern="^whatsapp_reconnect$"))
        
        # WhatsApp Pairing Code conversation handler
        pairing_code_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(whatsapp_pairing_code_callback, pattern="^whatsapp_pairing_code$")],
            states={
                "WAITING_PHONE_NUMBER": [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pairing_phone_number),
                ]
            },
            fallbacks=[
                CommandHandler("cancel", cancel_pairing_code),
                MessageHandler(filters.Regex("^(🔙 Cancelar|Cancelar)$"), cancel_pairing_code)
            ],
            per_message=False,  
            per_chat=True,      
            per_user=True,      
            conversation_timeout=600 
        )
        application.add_handler(pairing_code_handler)
        application.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
        
        # Unknown callback handler
        application.add_handler(CallbackQueryHandler(unknown_callback))
        
        # Error handler
        application.add_error_handler(error_handler)
        
        # Start the bot
        logger.info("Starting Telegram bot...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise
    finally:
        # Stop scheduler service
        logger.info("Stopping scheduler service...")
        try:
            scheduler_service.stop()
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

async def set_morning_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle set morning time callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            text = """🌅 **Configurar Horário Matinal**

⏰ Digite o horário para envio dos lembretes matinais.

📝 **Formato:** HH:MM (exemplo: 09:30)
🕘 **Padrão atual:** 09:00

💡 *Este horário será usado para enviar lembretes de:*
• 2 dias antes do vencimento
• 1 dia antes do vencimento  
• No dia do vencimento
• 1 dia após vencimento (em atraso)"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Voltar", callback_data="schedule_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # Return state for conversation handler
            return SCHEDULE_WAITING_MORNING_TIME
            
    except Exception as e:
        logger.error(f"Error setting morning time: {e}")
        await query.edit_message_text("❌ Erro ao configurar horário matinal.")


async def set_report_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle set report time callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            text = """📊 **Configurar Horário do Relatório**

⏰ Digite o horário para receber o relatório diário.

📝 **Formato:** HH:MM (exemplo: 08:30)
🕗 **Padrão atual:** 08:00

💡 *O relatório diário inclui:*
• Clientes em atraso
• Vencimentos de hoje
• Vencimentos de amanhã
• Vencimentos em 2 dias"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Voltar", callback_data="schedule_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # Return state for conversation handler
            return SCHEDULE_WAITING_REPORT_TIME
            
    except Exception as e:
        logger.error(f"Error setting report time: {e}")
        await query.edit_message_text("❌ Erro ao configurar horário do relatório.")

async def reset_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset schedule to defaults callback"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        from datetime import datetime
        from models import UserScheduleSettings
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Reset to default times
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if schedule_settings:
                schedule_settings.morning_reminder_time = '09:00'
                schedule_settings.daily_report_time = '08:00'
                schedule_settings.updated_at = datetime.utcnow()
            else:
                schedule_settings = UserScheduleSettings(
                    user_id=db_user.id,
                    morning_reminder_time='09:00',
                    daily_report_time='08:00'
                )
                session.add(schedule_settings)
            
            session.commit()
            
            text = """✅ **Horários Resetados!**

🔄 **Horários padrão aplicados:**
• 🌅 Lembretes matinais: **09:00**
• 📊 Relatório diário: **08:00**

⚡ As configurações entrarão em vigor no próximo ciclo de agendamento."""
            
            keyboard = [
                [InlineKeyboardButton("⏰ Ver Configurações", callback_data="schedule_settings")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error resetting schedule: {e}")
        await query.edit_message_text("❌ Erro ao resetar configurações de horários.")

async def handle_schedule_morning_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle morning time input"""
    if not update.message or not update.message.text:
        return
        
    time_input = update.message.text.strip()
    
    # Check for cancel
    if time_input in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Configuração cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    return await process_schedule_time_setting(update, context, time_input, "morning")


async def handle_schedule_report_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle report time input"""
    if not update.message or not update.message.text:
        return
        
    time_input = update.message.text.strip()
    
    # Check for cancel
    if time_input in ["🏠 Menu Principal", "Cancelar", "cancelar", "CANCELAR"]:
        await update.message.reply_text("❌ Configuração cancelada.")
        await show_main_menu(update, context)
        return ConversationHandler.END
    
    return await process_schedule_time_setting(update, context, time_input, "report")

async def process_schedule_time_setting(update: Update, context: ContextTypes.DEFAULT_TYPE, time_input: str, time_type: str):
    """Process schedule time setting from user input"""
    if not update.effective_user:
        return ConversationHandler.END
        
    user = update.effective_user
    
    try:
        # Validate time format
        if not validate_time_format(time_input):
            await update.message.reply_text("❌ Formato inválido! Use o formato HH:MM (exemplo: 09:30)")
            # Stay in same state to get new input
            if time_type == "morning":
                return SCHEDULE_WAITING_MORNING_TIME
            elif time_type == "report":
                return SCHEDULE_WAITING_REPORT_TIME
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return ConversationHandler.END
            
            from models import UserScheduleSettings
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if not schedule_settings:
                schedule_settings = UserScheduleSettings(user_id=db_user.id)
                session.add(schedule_settings)
            
            # Update the appropriate time based on time_type
            if time_type == "morning":
                schedule_settings.morning_reminder_time = time_input
                time_type_display = "matinal"
                emoji = "🌅"
            elif time_type == "report":
                schedule_settings.daily_report_time = time_input
                time_type_display = "do relatório"
                emoji = "📊"
            else:
                await update.message.reply_text("❌ Tipo inválido.")
                return ConversationHandler.END
            
            schedule_settings.updated_at = datetime.utcnow()
            session.commit()
            
            text = f"""✅ **Horário {time_type_display.title()} Atualizado!**

{emoji} **Novo horário:** {time_input}

⚡ A configuração entrará em vigor no próximo ciclo de agendamento.

⏰ Use **⏰ Horários** no menu para ver todas as configurações."""
            
            keyboard = [
                [InlineKeyboardButton("⏰ Ver Todas Configurações", callback_data="schedule_settings")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error processing schedule time setting: {e}")
        await update.message.reply_text("❌ Erro ao configurar horário.")
        return ConversationHandler.END

async def process_time_setting(update: Update, context: ContextTypes.DEFAULT_TYPE, time_input: str):
    """Process time setting from user input"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    
    try:
        # Validate time format
        if not validate_time_format(time_input):
            await update.message.reply_text("❌ Formato inválido! Use o formato HH:MM (exemplo: 09:30)")
            return
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await update.message.reply_text("❌ Conta inativa.")
                return
            
            from models import UserScheduleSettings
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if not schedule_settings:
                schedule_settings = UserScheduleSettings(user_id=db_user.id)
                session.add(schedule_settings)
            
            # Update the appropriate time based on user state
            if context.user_data.get('setting_morning_time'):
                schedule_settings.morning_reminder_time = time_input
                time_type = "matinal"
                emoji = "🌅"
                del context.user_data['setting_morning_time']
            elif context.user_data.get('setting_report_time'):
                schedule_settings.daily_report_time = time_input
                time_type = "do relatório"
                emoji = "📊"
                del context.user_data['setting_report_time']
            else:
                await update.message.reply_text("❌ Estado inválido.")
                return
            
            schedule_settings.updated_at = datetime.utcnow()
            session.commit()
            
            text = f"""✅ **Horário {time_type.title()} Atualizado!**

{emoji} **Novo horário:** {time_input}

⚡ A configuração entrará em vigor no próximo ciclo de agendamento.

⏰ Use **⏰ Horários** no menu para ver todas as configurações."""
            
            keyboard = [
                [InlineKeyboardButton("⏰ Ver Todas Configurações", callback_data="schedule_settings")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error processing time setting: {e}")
        await update.message.reply_text("❌ Erro ao configurar horário.")

def validate_time_format(time_str: str) -> bool:
    """Validate time format HH:MM"""
    try:
        if len(time_str) != 5 or time_str[2] != ':':
            return False
        
        hours, minutes = time_str.split(':')
        hours = int(hours)
        minutes = int(minutes)
        
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except:
        return False

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings button callback - redirect to schedule settings"""
    if not update.callback_query:
        return
        
    # Simply redirect to schedule_settings_callback
    await schedule_settings_callback(update, context)

async def schedule_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle schedule settings callback - back to main schedule menu"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Clear any time setting states
    context.user_data.pop('setting_morning_time', None)
    context.user_data.pop('setting_report_time', None)
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get current schedule settings
            from models import UserScheduleSettings
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if not schedule_settings:
                # Create default settings
                schedule_settings = UserScheduleSettings(
                    user_id=db_user.id,
                    morning_reminder_time='09:00',
                    daily_report_time='08:00',
                    auto_send_enabled=True
                )
                session.add(schedule_settings)
                session.commit()
            
            # Check if auto_send_enabled exists (for backward compatibility)
            auto_send_status = getattr(schedule_settings, 'auto_send_enabled', True)
            auto_send_emoji = "✅" if auto_send_status else "❌"
            auto_send_text = "Ativados" if auto_send_status else "Desativados"
            
            text = f"""⏰ **Configurações de Horários**

📅 **Horários Atuais:**
• 🌅 Lembretes matinais: **{schedule_settings.morning_reminder_time}**
• 📊 Relatório diário: **{schedule_settings.daily_report_time}**

🤖 **Envios Automáticos:** {auto_send_emoji} **{auto_send_text}**

⚙️ **O que você deseja fazer?**"""
            
            # Dynamic button text for auto send toggle
            auto_send_button_text = "❌ Desativar Envios" if auto_send_status else "✅ Ativar Envios"
            auto_send_callback = "toggle_auto_send_off" if auto_send_status else "toggle_auto_send_on"
            
            keyboard = [
                [InlineKeyboardButton("🌅 Alterar Horário Matinal", callback_data="set_morning_time")],
                [InlineKeyboardButton("📊 Alterar Horário Relatório", callback_data="set_report_time")],
                [InlineKeyboardButton(auto_send_button_text, callback_data=auto_send_callback)],
                [InlineKeyboardButton("🔄 Resetar para Padrão", callback_data="reset_schedule")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing schedule settings: {e}")
        await query.edit_message_text("❌ Erro ao carregar configurações de horários.")

async def toggle_auto_send_on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto send ON"""
    await toggle_auto_send(update, context, True)

async def toggle_auto_send_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto send OFF"""
    await toggle_auto_send(update, context, False)

async def toggle_auto_send(update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool):
    """Toggle automatic sending on or off"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get or create schedule settings
            from models import UserScheduleSettings
            schedule_settings = session.query(UserScheduleSettings).filter_by(
                user_id=db_user.id
            ).first()
            
            if not schedule_settings:
                schedule_settings = UserScheduleSettings(
                    user_id=db_user.id,
                    morning_reminder_time='09:00',
                    daily_report_time='08:00',
                    auto_send_enabled=enable
                )
                session.add(schedule_settings)
            else:
                schedule_settings.auto_send_enabled = enable
                schedule_settings.updated_at = datetime.utcnow()
            
            session.commit()
            
            status_text = "ativados" if enable else "desativados"
            emoji = "✅" if enable else "❌"
            
            text = f"""{emoji} **Envios Automáticos {status_text.title()}!**

🤖 Os lembretes e relatórios automáticos foram **{status_text}**.

{f"⚡ A partir de agora, o sistema enviará automaticamente:" if enable else "🔇 O sistema não enviará mais lembretes automaticamente até você reativar."}

{f'''📱 **Horários configurados:**
• 🌅 Lembretes matinais: {schedule_settings.morning_reminder_time}
• 📊 Relatório diário: {schedule_settings.daily_report_time}''' if enable else ""}

⏰ Use **⏰ Horários** no menu para alterar configurações."""
            
            keyboard = [
                [InlineKeyboardButton("⏰ Ver Todas Configurações", callback_data="schedule_settings")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error toggling auto send: {e}")
        await query.edit_message_text("❌ Erro ao alterar configuração de envios automáticos.")

async def toggle_client_reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto reminders for specific client"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get client
            client = session.query(Client).filter_by(id=client_id, user_id=db_user.id).first()
            
            if not client:
                await query.edit_message_text("❌ Cliente não encontrado.")
                return
            
            # Toggle auto reminders
            current_status = getattr(client, 'auto_reminders_enabled', True)
            client.auto_reminders_enabled = not current_status
            client.updated_at = datetime.utcnow()
            
            session.commit()
            
            status_text = "ativados" if client.auto_reminders_enabled else "desativados"
            emoji = "✅" if client.auto_reminders_enabled else "❌"
            
            text = f"""{emoji} **Lembretes {status_text.title()}!**

🤖 Os lembretes automáticos para **{client.name}** foram **{status_text}**.

{f"⚡ Este cliente receberá lembretes automáticos nos horários configurados." if client.auto_reminders_enabled else "🔇 Este cliente não receberá mais lembretes automáticos."}

📋 Use **👥 Clientes** para ver outros clientes."""
            
            keyboard = [
                [InlineKeyboardButton("👁️ Ver Detalhes", callback_data=f"client_{client.id}")],
                [InlineKeyboardButton("👥 Lista de Clientes", callback_data="back_to_clients")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error toggling client reminders: {e}")
        await query.edit_message_text("❌ Erro ao alterar configuração de lembretes do cliente.")

async def view_sending_queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View clients in sending queue"""
    query = update.callback_query
    await query.answer()
    
    try:
        user = update.effective_user
        if not user:
            return
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            from datetime import date, timedelta
            today = date.today()
            
            # Buscar clientes que vão receber lembretes nos próximos dias
            clients_2_days = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active',
                auto_reminders_enabled=True,
                due_date=today + timedelta(days=2)
            ).all()
            
            clients_1_day = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active',
                auto_reminders_enabled=True,
                due_date=today + timedelta(days=1)
            ).all()
            
            clients_today = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active',
                auto_reminders_enabled=True,
                due_date=today
            ).all()
            
            clients_overdue = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active',
                auto_reminders_enabled=True,
                due_date=today - timedelta(days=1)
            ).all()
            
            text = "📋 **Fila de Envios Automáticos**\n\n"
            
            if clients_2_days:
                text += "📅 **Em 2 dias (Lembrete Antecipado):**\n"
                for client in clients_2_days:
                    text += f"• {client.name} - {client.due_date.strftime('%d/%m/%Y')}\n"
                text += "\n"
            
            if clients_1_day:
                text += "⚠️ **Amanhã (Lembrete Final):**\n"
                for client in clients_1_day:
                    text += f"• {client.name} - {client.due_date.strftime('%d/%m/%Y')}\n"
                text += "\n"
            
            if clients_today:
                text += "🚨 **Hoje (Vencimento):**\n"
                for client in clients_today:
                    text += f"• {client.name} - {client.due_date.strftime('%d/%m/%Y')}\n"
                text += "\n"
            
            if clients_overdue:
                text += "🔴 **Em atraso (Cobrança):**\n"
                for client in clients_overdue:
                    text += f"• {client.name} - {client.due_date.strftime('%d/%m/%Y')}\n"
                text += "\n"
            
            if not any([clients_2_days, clients_1_day, clients_today, clients_overdue]):
                text += "✅ **Nenhum cliente na fila de envios no momento.**\n\n"
                text += "Todos os clientes estão com lembretes desativados ou não têm vencimentos próximos."
            
            text += "\n🔧 **Ações disponíveis:**\n"
            text += "• ❌ Cancelar envio específico\n"
            text += "• ⏰ Alterar horários de envio\n"
            text += "• 👥 Gerenciar clientes individuais"
            
            keyboard = [
                [InlineKeyboardButton("❌ Cancelar Envio Específico", callback_data="cancel_specific_sending")],
                [InlineKeyboardButton("👥 Ver Clientes", callback_data="main_menu")],
                [InlineKeyboardButton("⏰ Voltar aos Horários", callback_data="schedule_settings")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error viewing sending queue: {e}")
        await query.answer("❌ Erro ao carregar fila de envios.", show_alert=True)

async def cancel_specific_sending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel specific client sending"""
    query = update.callback_query
    await query.answer()
    
    try:
        user = update.effective_user
        if not user:
            return
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            # Buscar clientes ativos com lembretes habilitados
            clients = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active',
                auto_reminders_enabled=True
            ).all()
            
            if not clients:
                text = "❌ **Nenhum cliente com lembretes ativos encontrado.**\n\n"
                text += "Para cancelar envios, você precisa ter clientes com:\n"
                text += "• Status: Ativo\n"
                text += "• Lembretes automáticos: Habilitados\n\n"
                text += "Use **👥 Clientes** para gerenciar individualmente."
                
                keyboard = [
                    [InlineKeyboardButton("👥 Ver Clientes", callback_data="main_menu")],
                    [InlineKeyboardButton("⏰ Voltar aos Horários", callback_data="schedule_settings")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            text = "❌ **Cancelar Envio Específico**\n\n"
            text += "Selecione o cliente para **DESATIVAR** os lembretes automáticos:\n\n"
            
            keyboard = []
            for client in clients[:10]:  # Limit to first 10 clients
                from datetime import date
                days_until_due = (client.due_date - date.today()).days
                status_emoji = "🚨" if days_until_due <= 0 else "⚠️" if days_until_due <= 2 else "📅"
                
                button_text = f"{status_emoji} {client.name} ({client.due_date.strftime('%d/%m')})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"disable_reminders_{client.id}")])
            
            keyboard.append([InlineKeyboardButton("📋 Ver Fila de Envios", callback_data="view_sending_queue")])
            keyboard.append([InlineKeyboardButton("⏰ Voltar aos Horários", callback_data="schedule_settings")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing cancel specific sending: {e}")
        await query.answer("❌ Erro ao carregar opções de cancelamento.", show_alert=True)

async def disable_reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disable reminders for specific client"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Extract client ID from callback data
        client_id = int(query.data.split('_')[-1])
        user = update.effective_user
        
        if not user:
            return
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            client = session.query(Client).filter_by(
                id=client_id,
                user_id=db_user.id
            ).first()
            
            if not client:
                await query.answer("❌ Cliente não encontrado.", show_alert=True)
                return
            
            # Disable automatic reminders for this client
            client.auto_reminders_enabled = False
            session.commit()
            
            text = f"✅ **Lembretes cancelados com sucesso!**\n\n"
            text += f"👤 **Cliente:** {client.name}\n"
            text += f"📅 **Vencimento:** {client.due_date.strftime('%d/%m/%Y')}\n"
            text += f"📱 **Telefone:** {client.phone_number}\n\n"
            text += f"❌ **Status dos lembretes:** DESATIVADOS\n\n"
            text += f"🔄 Este cliente não receberá mais lembretes automáticos até você reativar.\n\n"
            text += f"**Para reativar:** Vá em **👥 Clientes** → Selecionar cliente → **🔔 Ativar Lembretes**"
            
            keyboard = [
                [InlineKeyboardButton("❌ Cancelar Outro Cliente", callback_data="cancel_specific_sending")],
                [InlineKeyboardButton("📋 Ver Fila de Envios", callback_data="view_sending_queue")],
                [InlineKeyboardButton("👥 Ver Clientes", callback_data="main_menu")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error disabling reminders: {e}")
        await query.answer("❌ Erro ao cancelar lembretes.", show_alert=True)

if __name__ == '__main__':
    main()