import logging
from typing import Optional, List, Dict, Any
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.constants import ParseMode
from services.database_service import db_service
from models import User
from config import Config

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    async def send_notification(self, user_telegram_id: str, message: str, 
                              reply_markup: InlineKeyboardMarkup = None,
                              parse_mode: str = ParseMode.MARKDOWN) -> bool:
        """
        Send notification message to a specific user
        """
        try:
            await self.bot.send_message(
                chat_id=user_telegram_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.info(f"Notification sent to user {user_telegram_id}")
            return True
            
        except Forbidden:
            logger.warning(f"Bot blocked by user {user_telegram_id}")
            # Mark user as inactive if bot is blocked
            await self._handle_blocked_user(user_telegram_id)
            return False
            
        except BadRequest as e:
            logger.error(f"Bad request sending notification to {user_telegram_id}: {e}")
            return False
            
        except TelegramError as e:
            logger.error(f"Telegram error sending notification to {user_telegram_id}: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error sending notification to {user_telegram_id}: {e}")
            return False
    
    async def send_payment_confirmation(self, user_telegram_id: str, 
                                      subscription_expires_at: str) -> bool:
        """
        Send payment confirmation notification
        """
        message = f"""
🎉 **Pagamento Confirmado!**

✅ Sua assinatura foi renovada com sucesso!
📅 Válida até: {subscription_expires_at}

Agora você pode continuar usando todas as funcionalidades:
👥 Gestão ilimitada de clientes
📱 Lembretes automáticos via WhatsApp
💰 Controle de vencimentos

Obrigado pela confiança! 🚀
"""
        
        keyboard = [
            [InlineKeyboardButton("👥 Gerenciar Clientes", callback_data="manage_clients")],
            [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return await self.send_notification(user_telegram_id, message, reply_markup)
    
    async def send_trial_expiry_warning(self, user_telegram_id: str, days_left: int) -> bool:
        """
        Send trial expiry warning notification
        """
        if days_left <= 0:
            message = """
⚠️ **Período de Teste Expirado**

Seu período de teste de 7 dias expirou.

Para continuar usando o bot, assine o plano mensal por apenas R$ 20,00.

💎 **Benefícios do Plano Premium:**
👥 Gestão ilimitada de clientes
📱 Lembretes automáticos via WhatsApp
💰 Controle de vencimentos
📊 Relatórios detalhados
"""
        else:
            message = f"""
⏰ **Teste Expirando**

Seu período de teste expira em {days_left} dia{'s' if days_left > 1 else ''}!

Assine agora o plano mensal por apenas R$ 20,00 e continue aproveitando:
👥 Gestão ilimitada de clientes
📱 Lembretes automáticos via WhatsApp
💰 Controle de vencimentos
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Assinar Agora", callback_data="subscribe_now")],
            [InlineKeyboardButton("📋 Ver Clientes", callback_data="manage_clients")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return await self.send_notification(user_telegram_id, message, reply_markup)
    
    async def send_subscription_expiry_warning(self, user_telegram_id: str, days_left: int) -> bool:
        """
        Send subscription expiry warning notification
        """
        if days_left <= 0:
            message = """
⚠️ **Assinatura Vencida**

Sua assinatura venceu. Renove agora para continuar usando o bot.

💰 **Renovação:** R$ 20,00/mês
"""
        elif days_left <= 3:
            message = f"""
⏰ **Assinatura Vencendo**

Sua assinatura vence em {days_left} dia{'s' if days_left > 1 else ''}!

Renove agora para não perder o acesso:
💰 **Valor:** R$ 20,00/mês
"""
        else:
            return True  # Don't send warning yet
        
        keyboard = [
            [InlineKeyboardButton("💳 Renovar Agora", callback_data="subscribe_now")],
            [InlineKeyboardButton("📊 Ver Status", callback_data="subscription_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return await self.send_notification(user_telegram_id, message, reply_markup)
    
    async def send_whatsapp_error_notification(self, user_telegram_id: str, 
                                             client_name: str, error_message: str) -> bool:
        """
        Send WhatsApp delivery error notification
        """
        message = f"""
❌ **Erro no Envio WhatsApp**

Não foi possível enviar mensagem para:
👤 **Cliente:** {client_name}

📝 **Erro:** {error_message}

Verifique:
• Número de telefone do cliente
• Status da conexão WhatsApp
• Configurações da API

Use /ajuda se precisar de suporte.
"""
        
        keyboard = [
            [InlineKeyboardButton("📱 Verificar WhatsApp", callback_data="whatsapp_status")],
            [InlineKeyboardButton("👥 Ver Clientes", callback_data="manage_clients")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return await self.send_notification(user_telegram_id, message, reply_markup)
    
    async def broadcast_system_notification(self, message: str, 
                                          active_users_only: bool = True) -> Dict[str, int]:
        """
        Broadcast system notification to all users
        """
        results = {
            'sent': 0,
            'failed': 0,
            'blocked': 0
        }
        
        try:
            with db_service.get_session() as session:
                query = session.query(User)
                if active_users_only:
                    query = query.filter(User.is_active == True)
                
                users = query.all()
                
                for user in users:
                    success = await self.send_notification(user.telegram_id, message)
                    if success:
                        results['sent'] += 1
                    else:
                        results['failed'] += 1
                
                logger.info(f"Broadcast completed: {results}")
                return results
                
        except Exception as e:
            logger.error(f"Error broadcasting system notification: {e}")
            return results
    
    async def send_welcome_to_premium(self, user_telegram_id: str) -> bool:
        """
        Send welcome message when user upgrades to premium
        """
        message = """
🎉 **Bem-vindo ao Premium!**

Parabéns! Agora você tem acesso completo a todas as funcionalidades:

✅ **Incluído no seu plano:**
👥 Gestão ilimitada de clientes
📱 Lembretes automáticos via WhatsApp
💰 Controle de vencimentos
📊 Relatórios detalhados
🔔 Notificações em tempo real
🛠️ Suporte prioritário

🚀 **Começe agora:**
• Cadastre seus clientes
• Configure os lembretes automáticos
• Monitore vencimentos

Obrigado por confiar em nosso serviço! 💎
"""
        
        keyboard = [
            [InlineKeyboardButton("➕ Adicionar Cliente", callback_data="add_client")],
            [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return await self.send_notification(user_telegram_id, message, reply_markup)
    
    async def send_maintenance_notification(self, user_telegram_id: str, 
                                          maintenance_message: str) -> bool:
        """
        Send maintenance notification
        """
        message = f"""
🔧 **Manutenção Programada**

{maintenance_message}

Pedimos desculpas pelo inconveniente. Voltaremos o mais breve possível!

Para dúvidas, entre em contato conosco.
"""
        
        return await self.send_notification(user_telegram_id, message)
    
    async def _handle_blocked_user(self, user_telegram_id: str):
        """
        Handle user that has blocked the bot
        """
        try:
            with db_service.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_telegram_id).first()
                if user:
                    # Don't deactivate immediately, just log for now
                    # user.is_active = False
                    # session.commit()
                    logger.info(f"User {user_telegram_id} has blocked the bot")
                    
        except Exception as e:
            logger.error(f"Error handling blocked user {user_telegram_id}: {e}")
    
    async def get_bot_info(self) -> Dict[str, Any]:
        """
        Get bot information
        """
        try:
            bot_info = await self.bot.get_me()
            return {
                'success': True,
                'id': bot_info.id,
                'username': bot_info.username,
                'first_name': bot_info.first_name,
                'can_join_groups': bot_info.can_join_groups,
                'can_read_all_group_messages': bot_info.can_read_all_group_messages,
                'supports_inline_queries': bot_info.supports_inline_queries
            }
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def check_user_accessible(self, user_telegram_id: str) -> bool:
        """
        Check if user is accessible (hasn't blocked the bot)
        """
        try:
            await self.bot.send_chat_action(chat_id=user_telegram_id, action="typing")
            return True
        except Forbidden:
            return False
        except Exception as e:
            logger.error(f"Error checking user accessibility: {e}")
            return False
    
    async def send_bulk_notifications(self, user_telegram_ids: List[str], 
                                    message: str, 
                                    reply_markup: InlineKeyboardMarkup = None) -> Dict[str, int]:
        """
        Send notifications to multiple users
        """
        results = {
            'sent': 0,
            'failed': 0,
            'blocked': 0
        }
        
        for user_id in user_telegram_ids:
            success = await self.send_notification(user_id, message, reply_markup)
            if success:
                results['sent'] += 1
            else:
                results['failed'] += 1
        
        return results
    
    def format_user_mention(self, user) -> str:
        """
        Format user mention for messages
        """
        if user.username:
            return f"@{user.username}"
        elif user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        else:
            return f"Usuário {user.telegram_id}"

# Global telegram service instance
telegram_service = TelegramService()
