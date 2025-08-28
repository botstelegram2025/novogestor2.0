from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
import logging
from datetime import datetime, date, timedelta
from services.database_service import db_service
from services.whatsapp_service import whatsapp_service
from models import User, Client, MessageTemplate
from templates.message_templates import format_client_list, format_welcome_message, format_renewal_message

logger = logging.getLogger(__name__)

# Conversation states
WAITING_CLIENT_NAME = 1
WAITING_CLIENT_PHONE = 2
WAITING_CLIENT_PLAN = 3
WAITING_CLIENT_PRICE = 4
WAITING_CLIENT_DUE_DATE = 5
WAITING_EDIT_FIELD = 6
WAITING_EDIT_VALUE = 7

async def manage_clients_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manage clients callback"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa. Assine o plano para continuar.")
                return
            
            clients = session.query(Client).filter_by(user_id=db_user.id).all()
            client_list = format_client_list(clients)
            
            keyboard = [
                [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                [InlineKeyboardButton("📝 Editar Cliente", callback_data="edit_client")],
                [InlineKeyboardButton("📱 Enviar Mensagem", callback_data="send_message")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                client_list,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error managing clients: {e}")
        await query.edit_message_text("❌ Erro ao carregar clientes.")

async def add_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start add client conversation"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check user status
    with db_service.get_session() as session:
        db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
        
        if not db_user or not db_user.is_active:
            await query.edit_message_text("❌ Conta inativa. Assine o plano para continuar.")
            return ConversationHandler.END
    
    # Store user context
    context.user_data['adding_client'] = True
    context.user_data['client_data'] = {}
    
    await query.edit_message_text(
        "👤 **Adicionar Novo Cliente**\n\nDigite o nome do cliente:"
    )
    
    return WAITING_CLIENT_NAME

async def handle_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client name input"""
    client_name = update.message.text.strip()
    
    if len(client_name) < 2:
        await update.message.reply_text("❌ Nome muito curto. Digite um nome válido:")
        return WAITING_CLIENT_NAME
    
    context.user_data['client_data']['name'] = client_name
    
    await update.message.reply_text(
        f"✅ Nome: {client_name}\n\n📱 Agora digite o número de telefone (com DDD):"
    )
    
    return WAITING_CLIENT_PHONE

async def handle_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client phone input"""
    phone_number = update.message.text.strip()
    
    # Clean and validate phone number
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) < 10 or len(clean_phone) > 11:
        await update.message.reply_text(
            "❌ Número inválido. Digite apenas os números com DDD (ex: 11999999999):"
        )
        return WAITING_CLIENT_PHONE
    
    context.user_data['client_data']['phone_number'] = clean_phone
    
    await update.message.reply_text(
        f"✅ Telefone: {clean_phone}\n\n📦 Digite o nome do plano/serviço:"
    )
    
    return WAITING_CLIENT_PLAN

async def handle_client_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client plan input"""
    plan_name = update.message.text.strip()
    
    context.user_data['client_data']['plan_name'] = plan_name
    
    await update.message.reply_text(
        f"✅ Plano: {plan_name}\n\n💰 Digite o valor do plano (ex: 50.00):"
    )
    
    return WAITING_CLIENT_PRICE

async def handle_client_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client price input"""
    price_text = update.message.text.strip().replace(',', '.')
    
    try:
        price = float(price_text)
        if price < 0:
            raise ValueError("Price cannot be negative")
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Digite um número válido (ex: 50.00):"
        )
        return WAITING_CLIENT_PRICE
    
    context.user_data['client_data']['plan_price'] = price
    
    await update.message.reply_text(
        f"✅ Valor: R$ {price:.2f}\n\n📅 Digite a data de vencimento (DD/MM/AAAA):"
    )
    
    return WAITING_CLIENT_DUE_DATE

async def handle_client_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client due date input and save client"""
    due_date_text = update.message.text.strip()
    
    try:
        due_date = datetime.strptime(due_date_text, '%d/%m/%Y').date()
        if due_date < date.today():
            await update.message.reply_text(
                "⚠️ Data já passou. Digite uma data futura (DD/MM/AAAA):"
            )
            return WAITING_CLIENT_DUE_DATE
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida. Use o formato DD/MM/AAAA (ex: 31/12/2024):"
        )
        return WAITING_CLIENT_DUE_DATE
    
    # Save client to database
    user = update.effective_user
    client_data = context.user_data['client_data']
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await update.message.reply_text("❌ Usuário não encontrado.")
                return ConversationHandler.END
            
            new_client = Client(
                user_id=db_user.id,
                name=client_data['name'],
                phone_number=client_data['phone_number'],
                plan_name=client_data['plan_name'],
                plan_price=client_data['plan_price'],
                due_date=due_date,
                status='active'
            )
            
            session.add(new_client)
            session.commit()
            
            # Send welcome message if enabled
            await send_welcome_message(session, new_client)
            
            success_message = f"""
✅ **Cliente cadastrado com sucesso!**

👤 **{client_data['name']}**
📱 {client_data['phone_number']}
📦 {client_data['plan_name']}
💰 R$ {client_data['plan_price']:.2f}
📅 Vence: {due_date.strftime('%d/%m/%Y')}

📱 Mensagem de boas-vindas enviada via WhatsApp!
"""
            
            keyboard = [
                [InlineKeyboardButton("➕ Adicionar Outro", callback_data="add_client")],
                [InlineKeyboardButton("📋 Ver Clientes", callback_data="manage_clients")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                success_message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            logger.info(f"Client added: {client_data['name']} for user {user.id}")
            
    except Exception as e:
        logger.error(f"Error saving client: {e}")
        await update.message.reply_text("❌ Erro ao cadastrar cliente. Tente novamente.")
    
    # Clean up context
    context.user_data.pop('adding_client', None)
    context.user_data.pop('client_data', None)
    
    return ConversationHandler.END

async def send_welcome_message(session, client: Client):
    """Send welcome message to new client"""
    try:
        # Get welcome template
        template = session.query(MessageTemplate).filter_by(
            template_type='welcome',
            is_active=True
        ).first()
        
        if template:
            message_content = format_welcome_message(
                template.content,
                client_name=client.name,
                plan_name=client.plan_name,
                plan_price=client.plan_price,
                due_date=client.due_date.strftime('%d/%m/%Y')
            )
            
            # Send via WhatsApp
            result = whatsapp_service.send_message(client.phone_number, message_content)
            
            if result['success']:
                logger.info(f"Welcome message sent to {client.name}")
            else:
                logger.error(f"Failed to send welcome message to {client.name}: {result.get('error')}")
    
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

async def edit_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show client list for editing"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            clients = session.query(Client).filter_by(user_id=db_user.id).all()
            
            if not clients:
                await query.edit_message_text(
                    "📋 Nenhum cliente cadastrado.\n\nAdicione um cliente primeiro.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
                        [InlineKeyboardButton("🔙 Voltar", callback_data="manage_clients")]
                    ])
                )
                return
            
            keyboard = []
            for client in clients:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {client.name}",
                        callback_data=f"edit_client_{client.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="manage_clients")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📝 **Selecione o cliente para editar:**",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error showing edit client list: {e}")
        await query.edit_message_text("❌ Erro ao carregar clientes.")

async def send_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show options for sending messages"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user:
                await query.edit_message_text("❌ Usuário não encontrado.")
                return
            
            clients = session.query(Client).filter_by(
                user_id=db_user.id,
                status='active'
            ).all()
            
            if not clients:
                await query.edit_message_text(
                    "📋 Nenhum cliente ativo encontrado.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data="manage_clients")]
                    ])
                )
                return
            
            keyboard = [
                [InlineKeyboardButton("📱 Lembrete Manual", callback_data="send_manual_reminder")],
                [InlineKeyboardButton("🎉 Renovação", callback_data="send_renewal_message")],
                [InlineKeyboardButton("👋 Boas-vindas", callback_data="send_welcome_message")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="manage_clients")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📱 **Enviar Mensagem**\n\nEscolha o tipo de mensagem:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error showing send message options: {e}")
        await query.edit_message_text("❌ Erro ao carregar opções.")

# Conversation handler for adding clients
add_client_handler = ConversationHandler(
    entry_points=[],  # Will be triggered from callback
    states={
        WAITING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_name)],
        WAITING_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_phone)],
        WAITING_CLIENT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_plan)],
        WAITING_CLIENT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_price)],
        WAITING_CLIENT_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_due_date)],
    },
    fallbacks=[]
)
