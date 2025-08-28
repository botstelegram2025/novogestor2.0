from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
import logging
from datetime import datetime, timedelta
from services.database_service import db_service
from services.payment_service import payment_service
from models import User, Subscription
from templates.message_templates import format_subscription_info, format_payment_instructions

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_PHONE = 1

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    try:
        with db_service.get_session() as session:
            # Check if user already exists
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if db_user:
                # Existing user
                if db_user.is_active:
                    subscription_info = format_subscription_info(db_user)
                    
                    keyboard = [
                        [InlineKeyboardButton("👥 Gerenciar Clientes", callback_data="manage_clients")],
                        [InlineKeyboardButton("💳 Assinatura", callback_data="subscription_info")],
                        [InlineKeyboardButton("📊 Relatórios", callback_data="reports")],
                        [InlineKeyboardButton("❓ Ajuda", callback_data="help")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        f"👋 Olá {user.first_name}! Bem-vindo de volta!\n\n{subscription_info}",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    # User exists but inactive (trial expired)
                    await show_reactivation_options(update, context)
            else:
                # New user - start registration
                await start_registration(update, context)
                
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text(
            "❌ Ocorreu um erro. Tente novamente mais tarde."
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
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    return WAITING_FOR_PHONE

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input during registration"""
    user = update.effective_user
    phone_number = update.message.text.strip()
    
    # Basic phone validation
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    if len(clean_phone) < 10 or len(clean_phone) > 11:
        await update.message.reply_text(
            "❌ Número inválido. Digite apenas os números com DDD (ex: 11999999999):"
        )
        return WAITING_FOR_PHONE
    
    try:
        with db_service.get_session() as session:
            # Create new user
            new_user = User(
                telegram_id=str(user.id),
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                phone_number=clean_phone,
                trial_start_date=datetime.utcnow(),
                trial_end_date=datetime.utcnow() + timedelta(days=7),
                is_trial=True,
                is_active=True
            )
            
            session.add(new_user)
            session.commit()
            
            success_message = f"""
✅ **Cadastro realizado com sucesso!**

🆓 Seu período de teste de 7 dias já começou!
📅 Válido até: {new_user.trial_end_date.strftime('%d/%m/%Y às %H:%M')}

🚀 **Próximos passos:**
1. Cadastre seus primeiros clientes
2. Configure os lembretes automáticos
3. Teste todas as funcionalidades

Use os botões abaixo para começar:
"""
            
            keyboard = [
                [InlineKeyboardButton("👥 Cadastrar Cliente", callback_data="add_client")],
                [InlineKeyboardButton("📋 Ver Clientes", callback_data="list_clients")],
                [InlineKeyboardButton("⚙️ Configurações", callback_data="settings")],
                [InlineKeyboardButton("❓ Ajuda", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                success_message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            logger.info(f"New user registered: {user.id} - {user.first_name}")
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        await update.message.reply_text(
            "❌ Erro ao realizar cadastro. Tente novamente mais tarde."
        )
        return ConversationHandler.END

async def show_reactivation_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show options for reactivating expired account"""
    message = """
⚠️ **Sua conta está inativa**

Seu período de teste expirou. Para continuar usando o bot, você precisa assinar o plano mensal.

💰 **Assinatura:** R$ 20,00/mês
✅ **Inclui:** Gestão ilimitada de clientes, lembretes automáticos, suporte

Deseja reativar sua conta?
"""
    
    keyboard = [
        [InlineKeyboardButton("💳 Assinar Agora", callback_data="subscribe_now")],
        [InlineKeyboardButton("❓ Mais Informações", callback_data="subscription_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def subscription_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription info callback"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if db_user:
                subscription_info = format_subscription_info(db_user)
                
                keyboard = []
                if db_user.is_trial and db_user.is_active:
                    keyboard.append([InlineKeyboardButton("💳 Assinar Agora (PIX)", callback_data="subscribe_now")])
                elif not db_user.is_active:
                    keyboard.append([InlineKeyboardButton("💳 Reativar Conta (PIX)", callback_data="subscribe_now")])
                
                keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    subscription_info,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Usuário não encontrado.")
                
    except Exception as e:
        logger.error(f"Error showing subscription info: {e}")
        await query.edit_message_text("❌ Erro ao carregar informações.")

async def subscribe_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription payment callback - create PIX payment directly"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Create PIX payment directly
        payment_result = payment_service.create_subscription_payment(str(user.id), method="pix")
        
        if payment_result['success']:
            # Save subscription record
            with db_service.get_session() as session:
                db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
                
                if db_user:
                    subscription = Subscription(
                        user_id=db_user.id,
                        payment_id=str(payment_result['payment_id']),
                        amount=payment_result['amount'],
                        status='pending',
                        payment_method='pix',
                        pix_qr_code=payment_result['qr_code'],
                        pix_qr_code_base64=payment_result['qr_code_base64']
                    )
                    
                    session.add(subscription)
                    session.commit()
                    
                    # Format expiration date
                    expires_at = datetime.fromisoformat(payment_result['expires_at'].replace('Z', '+00:00'))
                    expires_formatted = expires_at.strftime('%d/%m/%Y às %H:%M')
                    
                    # Send payment instructions
                    payment_message = format_payment_instructions(
                        payment_result['qr_code'],
                        payment_result['amount'],
                        expires_formatted
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("✅ Verificar Pagamento", callback_data=f"check_payment_{payment_result['payment_id']}")],
                        [InlineKeyboardButton("🔄 Gerar Novo QR", callback_data="subscribe_now")],
                        [InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        payment_message,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"PIX payment created for user {user.id}: {payment_result['payment_id']}")
                else:
                    await query.edit_message_text("❌ Usuário não encontrado.")
        else:
            await query.edit_message_text(
                f"❌ Erro ao gerar PIX: {payment_result.get('error', 'Erro desconhecido')}"
            )
            
    except Exception as e:
        logger.error(f"Error creating PIX payment: {e}")
        await query.edit_message_text("❌ Erro interno. Tente novamente.")



async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check payment status and activate account if paid"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Extract payment ID from callback data
    callback_data = query.data
    payment_id = callback_data.split("_")[-1]
    
    try:
        # Check payment status
        payment_status = payment_service.check_payment_status(payment_id)
        
        if payment_status['success']:
            status = payment_status['status']
            
            if status == 'approved':
                # Payment approved - activate account
                await activate_user_account(user.id, payment_id)
                
                message = f"""
✅ **Pagamento Confirmado!**

Sua conta foi ativada com sucesso!

🎉 **Bem-vindo de volta!**
• Todos os recursos liberados
• Assinatura válida por 30 dias
• Renovação automática

💰 **Valor pago:** R$ {payment_status['amount']:.2f}
📅 **Data da aprovação:** {payment_status.get('date_approved', 'Agora')}

Clique em "🏠 Menu Principal" para começar!
"""
                
                keyboard = [
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                logger.info(f"Payment approved and account activated for user {user.id}")
                
            elif status == 'pending':
                message = f"""
⏳ **Pagamento Pendente**

Seu pagamento ainda está sendo processado.

💳 **Status:** {payment_status.get('status_detail', 'Em análise')}
⏰ **Aguarde:** A confirmação pode levar alguns minutos

🔄 Clique em "Verificar Novamente" em alguns minutos.
"""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Verificar Novamente", callback_data=f"check_payment_{payment_id}")],
                    [InlineKeyboardButton("🔙 Voltar", callback_data="subscribe_now")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
            elif status == 'rejected':
                message = f"""
❌ **Pagamento Rejeitado**

Infelizmente seu pagamento foi rejeitado.

🔍 **Motivo:** {payment_status.get('status_detail', 'Não especificado')}
💡 **Sugestão:** Tente novamente ou use outro método de pagamento

🔄 Clique em "Nova Tentativa" para tentar novamente.
"""
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Nova Tentativa", callback_data="subscribe_now")],
                    [InlineKeyboardButton("💬 Suporte", callback_data="help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
            else:
                await query.edit_message_text(
                    f"📊 Status do pagamento: {status}\n\nTente verificar novamente em alguns minutos."
                )
        else:
            await query.edit_message_text(
                f"❌ Erro ao verificar pagamento: {payment_status.get('error', 'Erro desconhecido')}"
            )
            
    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        await query.edit_message_text("❌ Erro ao verificar pagamento. Tente novamente.")

async def activate_user_account(telegram_id: int, payment_id: str):
    """Activate user account after successful payment"""
    try:
        with db_service.get_session() as session:
            # Find user
            user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
            
            if user:
                # Activate user
                user.is_active = True
                user.is_trial = False
                
                # Set next due date (30 days from now)
                from datetime import datetime, timedelta
                user.next_due_date = datetime.utcnow() + timedelta(days=30)
                
                # Update subscription record
                subscription = session.query(Subscription).filter_by(payment_id=payment_id).first()
                if subscription:
                    subscription.status = 'approved'
                    subscription.approved_at = datetime.utcnow()
                
                session.commit()
                
                logger.info(f"Account activated for user {telegram_id}, payment {payment_id}")
                return True
            else:
                logger.error(f"User not found for telegram_id {telegram_id}")
                return False
                
    except Exception as e:
        logger.error(f"Error activating user account: {e}")
        return False

async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment status check callback"""
    query = update.callback_query
    await query.answer()
    
    # Extract payment ID from callback data
    payment_id = query.data.split('_')[-1]
    
    try:
        payment_status = payment_service.check_payment_status(payment_id)
        
        if payment_status['success']:
            if payment_status['status'] == 'approved':
                # Payment approved - update user
                user = query.from_user
                
                with db_service.get_session() as session:
                    db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
                    subscription = session.query(Subscription).filter_by(payment_id=payment_id).first()
                    
                    if db_user and subscription:
                        # Update subscription
                        subscription.status = 'approved'
                        subscription.paid_at = datetime.utcnow()
                        subscription.expires_at = datetime.utcnow() + timedelta(days=30)
                        
                        # Update user
                        db_user.is_trial = False
                        db_user.is_active = True
                        db_user.last_payment_date = datetime.utcnow()
                        db_user.next_due_date = subscription.expires_at
                        
                        session.commit()
                        
                        success_message = f"""
🎉 **Pagamento Confirmado!**

✅ Sua assinatura foi ativada com sucesso!
📅 Válida até: {subscription.expires_at.strftime('%d/%m/%Y')}

Agora você pode usar todas as funcionalidades:
👥 Gestão ilimitada de clientes
📱 Lembretes automáticos via WhatsApp
💰 Controle de vencimentos
📊 Relatórios detalhados

Bem-vindo ao plano premium! 🚀
"""
                        
                        keyboard = [
                            [InlineKeyboardButton("👥 Gerenciar Clientes", callback_data="manage_clients")],
                            [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            success_message,
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                        
                        logger.info(f"Payment approved for user {user.id}")
                    else:
                        await query.edit_message_text("❌ Erro ao processar pagamento.")
            else:
                await query.edit_message_text(
                    f"⏳ Pagamento ainda pendente.\n\nStatus: {payment_status['status']}\n\nTente novamente em alguns minutos.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Verificar Novamente", callback_data=f"check_payment_{payment_id}")],
                        [InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")]
                    ])
                )
        else:
            await query.edit_message_text(
                "❌ Erro ao verificar status do pagamento. Tente novamente."
            )
            
    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        await query.edit_message_text("❌ Erro ao verificar pagamento.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
❓ **Ajuda - Bot de Gestão de Clientes**

**Comandos principais:**
/start - Iniciar o bot
/clientes - Gerenciar clientes
/assinatura - Informações da assinatura
/ajuda - Esta mensagem de ajuda

**Funcionalidades:**
👥 **Gestão de Clientes**: Cadastre e gerencie seus clientes
📱 **Lembretes WhatsApp**: Envio automático de lembretes de vencimento
💰 **Controle Financeiro**: Acompanhe vencimentos e pagamentos
📊 **Relatórios**: Visualize estatísticas dos seus clientes

**Lembretes Automáticos:**
• 2 dias antes do vencimento
• 1 dia antes do vencimento
• No dia do vencimento
• 1 dia após o vencimento

**Suporte:**
Para dúvidas ou problemas, entre em contato conosco.

**Assinatura:**
🆓 Teste grátis por 7 dias
💰 R$ 20,00/mês após o período de teste
"""
    
    keyboard = [
        [InlineKeyboardButton("👥 Clientes", callback_data="manage_clients")],
        [InlineKeyboardButton("💳 Assinatura", callback_data="subscription_info")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        query = update.callback_query
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

# Conversation handler for user registration
user_registration_handler = ConversationHandler(
    entry_points=[],  # Will be triggered from start_command
    states={
        WAITING_FOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)]
    },
    fallbacks=[]
)
