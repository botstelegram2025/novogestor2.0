import schedule
import time
import threading
import logging
from datetime import datetime, timedelta, date
import asyncio

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.loop = None

    def start(self):
        """Start the scheduler service"""
        if self.is_running:
            logger.warning("Scheduler service is already running")
            return

        self.is_running = True
        
        # Schedule jobs for reminder system - check user-specific times every minute
        schedule.every().minute.do(self._check_reminder_times)
        schedule.every().hour.do(self._check_due_dates)
        
        # Schedule payment verification every 2 minutes
        schedule.every(2).minutes.do(self._check_pending_payments)
        
        # Start the scheduler thread
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        
        logger.info("Scheduler service started")

    def stop(self):
        """Stop the scheduler service"""
        self.is_running = False
        schedule.clear()
        if self.thread:
            self.thread.join()
        logger.info("Scheduler service stopped")

    def _run_scheduler(self):
        """Run the scheduler in a separate thread"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler: {e}")

    def _check_reminder_times(self):
        """Check if it's time for any user's scheduled reminders or reports - improved to handle missed executions"""
        try:
            from services.database_service import DatabaseService
            from models import User, UserScheduleSettings, Client, MessageTemplate, MessageLog
            from services.whatsapp_service import whatsapp_service
            from services.telegram_service import telegram_service
            from datetime import date, time
            
            db_service = DatabaseService()
            
            # Use Brazil timezone (America/Sao_Paulo)
            import pytz
            brazil_tz = pytz.timezone('America/Sao_Paulo')
            current_datetime = datetime.now(brazil_tz)
            current_time_str = current_datetime.strftime("%H:%M")
            current_date = current_datetime.date()
            current_time = current_datetime.time()
            
            logger.info(f"Checking reminder times at {current_time_str}")
            
            with db_service.get_session() as session:
                # Get all active users with their schedule settings
                users_settings = session.query(User, UserScheduleSettings).join(
                    UserScheduleSettings, User.id == UserScheduleSettings.user_id, isouter=True
                ).filter(User.is_active == True).all()
                
                logger.info(f"Found {len(users_settings)} users to check")
                
                for user, settings in users_settings:
                    # Check for trial expiration first
                    self._check_trial_expiration(user, current_date)
                    
                    if not settings:
                        # Create default settings if none exist
                        logger.info(f"Creating default settings for user {user.id}")
                        settings = UserScheduleSettings(
                            user_id=user.id,
                            morning_reminder_time='09:00',
                            daily_report_time='08:00',
                            auto_send_enabled=True
                        )
                        session.add(settings)
                        session.commit()
                    
                    # Check if automated sending is enabled for this user
                    if hasattr(settings, 'auto_send_enabled') and not settings.auto_send_enabled:
                        logger.info(f"Auto send disabled for user {user.id}, skipping")
                        continue
                    
                    logger.info(f"Checking times for user {user.id}: morning={settings.morning_reminder_time}, report={settings.daily_report_time}")
                    
                    # Parse daily reminder time
                    try:
                        daily_time = datetime.strptime(settings.morning_reminder_time, "%H:%M").time()
                    except ValueError as e:
                        logger.error(f"Invalid time format for user {user.id}: {e}")
                        continue
                    
                    # Check daily reminders - execute if time passed and not run today
                    last_run = getattr(settings, 'last_morning_run', None)
                    if (current_time >= daily_time and 
                        (last_run != current_date or last_run is None)):
                        logger.info(f"Processing daily reminders for user {user.id} (time passed: {current_time_str} >= {settings.morning_reminder_time})")
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                self._process_daily_reminders_for_user(user.id), 
                                self._get_event_loop()
                            )
                            future.result(timeout=30)
                            
                            # Update last run date
                            from models import UserScheduleSettings
                            user_settings = session.query(UserScheduleSettings).filter_by(user_id=user.id).first()
                            if user_settings:
                                user_settings.last_morning_run = current_date
                                session.commit()
                            logger.info(f"Daily reminders completed for user {user.id}")
                        except Exception as e:
                            logger.error(f"Error processing daily reminders for user {user.id}: {e}")
                    
                    # Check daily report - execute if time passed and not run today  
                    try:
                        report_time = datetime.strptime(settings.daily_report_time, "%H:%M").time()
                        last_report_run = getattr(settings, 'last_report_run', None)
                        if (current_time >= report_time and 
                            (last_report_run != current_date or last_report_run is None)):
                            logger.info(f"Processing daily report for user {user.id} (time passed: {current_time_str} >= {settings.daily_report_time})")
                            try:
                                future = asyncio.run_coroutine_threadsafe(
                                    self._process_user_notifications_for_user(user.id), 
                                    self._get_event_loop()
                                )
                                future.result(timeout=30)
                                
                                # Update last report run date
                                from models import UserScheduleSettings
                                user_settings = session.query(UserScheduleSettings).filter_by(user_id=user.id).first()
                                if user_settings:
                                    user_settings.last_report_run = current_date
                                    session.commit()
                                logger.info(f"Daily report completed for user {user.id}")
                            except Exception as e:
                                logger.error(f"Error processing daily report for user {user.id}: {e}")
                    except ValueError:
                        logger.error(f"Invalid report time format for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error checking reminder times: {e}")

    def _get_event_loop(self):
        """Get or create event loop for async operations"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _send_user_reminders(self, user_id, time_period):
        """Send reminders for a specific user"""
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Run the reminder sending
            if time_period == 'morning':
                self.loop.run_until_complete(self._process_reminders_for_user(user_id))
            else:  # evening
                self.loop.run_until_complete(self._process_evening_reminders_for_user(user_id))
            
        except Exception as e:
            logger.error(f"Error sending {time_period} reminders for user {user_id}: {e}")
        finally:
            if self.loop:
                self.loop.close()

    def _send_user_notifications_for_user(self, user_id):
        """Send daily notifications to specific user about their clients' due dates"""
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Run the user notification sending
            self.loop.run_until_complete(self._process_user_notifications_for_user(user_id))
            
        except Exception as e:
            logger.error(f"Error sending daily notifications to user {user_id}: {e}")
        finally:
            if self.loop:
                self.loop.close()

    def _check_pending_payments(self):
        """Check pending payments and process approved ones automatically"""
        logger.info("🔍 Checking pending payments for automatic processing")
        
        try:
            from services.database_service import DatabaseService
            from services.payment_service import payment_service
            from services.telegram_service import telegram_service
            from models import User, Subscription
            from datetime import datetime, timedelta
            
            db_service = DatabaseService()
            
            with db_service.get_session() as session:
                # Get pending payments from last 24 hours
                yesterday = datetime.utcnow() - timedelta(hours=24)
                pending_subscriptions = session.query(Subscription).filter(
                    Subscription.status == 'pending',
                    Subscription.created_at >= yesterday
                ).all()
                
                logger.info(f"📋 Found {len(pending_subscriptions)} pending payments to check")
                
                approved_count = 0
                pending_count = 0
                
                for subscription in pending_subscriptions:
                    logger.info(f"🔍 Checking payment {subscription.payment_id} for user {subscription.user_id}")
                    
                    # Check payment status with Mercado Pago
                    payment_status = payment_service.check_payment_status(subscription.payment_id)
                    
                    if payment_status['success']:
                        current_status = payment_status['status']
                        status_detail = payment_status.get('status_detail', 'N/A')
                        logger.info(f"📊 Payment {subscription.payment_id} status: {current_status} ({status_detail})")
                        
                        if current_status == 'approved':
                            approved_count += 1
                            logger.info(f"✅ Payment {subscription.payment_id} APPROVED! Processing automatically...")
                            
                            # Update subscription
                            old_status = subscription.status
                            subscription.status = 'approved'
                            subscription.paid_at = datetime.utcnow()
                            subscription.expires_at = datetime.utcnow() + timedelta(days=30)
                            
                            # Update user
                            user = session.query(User).get(subscription.user_id)
                            if user:
                                user.is_trial = False
                                user.is_active = True
                                user.last_payment_date = datetime.utcnow()
                                user.next_due_date = subscription.expires_at
                                
                                # Send automatic approval notification via Telegram
                                try:
                                    notification_message = f"""
✅ **PAGAMENTO APROVADO AUTOMATICAMENTE!**

💰 **Valor:** R$ {subscription.amount:.2f}
📅 **Aprovado em:** {datetime.now().strftime('%d/%m/%Y às %H:%M')}

🎉 **Sua conta foi ativada!**
• Plano Premium ativo por 30 dias
• Todos os recursos liberados
• Próximo vencimento: {subscription.expires_at.strftime('%d/%m/%Y')}

🚀 Use o comando /start para acessar todas as funcionalidades!
"""
                                    
                                    # Send notification via telegram
                                    future = asyncio.run_coroutine_threadsafe(
                                        telegram_service.send_message(
                                            user.telegram_id, 
                                            notification_message
                                        ),
                                        self._get_event_loop()
                                    )
                                    future.result(timeout=10)
                                    
                                    logger.info(f"📲 Automatic approval notification sent to user {user.telegram_id}")
                                    
                                except Exception as e:
                                    logger.error(f"❌ Error sending approval notification: {e}")
                                
                                logger.info(f"✅ User {user.telegram_id} account AUTOMATICALLY ACTIVATED!")
                            
                            session.commit()
                            logger.info(f"💾 Payment {subscription.payment_id} updated: {old_status} → approved")
                            
                        elif current_status == 'pending':
                            pending_count += 1
                            if status_detail == 'pending_waiting_transfer':
                                logger.info(f"⏳ Payment {subscription.payment_id} - User hasn't scanned PIX code yet")
                            else:
                                logger.info(f"⏳ Payment {subscription.payment_id} - Still processing: {status_detail}")
                                
                        elif current_status in ['rejected', 'cancelled']:
                            logger.info(f"❌ Payment {subscription.payment_id} {current_status} - updating status")
                            subscription.status = current_status
                            session.commit()
                            
                    else:
                        logger.warning(f"⚠️ Failed to check payment {subscription.payment_id}: {payment_status.get('error')}")
                
                # Summary log
                if len(pending_subscriptions) > 0:
                    logger.info(f"📊 Payment check summary: {approved_count} approved, {pending_count} still pending, {len(pending_subscriptions) - approved_count - pending_count} other status")
                
                # Clean up very old pending payments (over 24 hours)
                old_pending = session.query(Subscription).filter(
                    Subscription.status == 'pending',
                    Subscription.created_at < yesterday
                ).all()
                
                for old_sub in old_pending:
                    old_sub.status = 'expired'
                    logger.info(f"⏰ Expired old pending payment {old_sub.payment_id}")
                
                if old_pending:
                    session.commit()
                    logger.info(f"🧹 Cleaned up {len(old_pending)} expired payments")
                
        except Exception as e:
            logger.error(f"❌ Error checking pending payments: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _check_due_dates(self):
        """Check for overdue clients and update status"""
        logger.info("Running due date check")
        
        try:
            from services.database_service import DatabaseService
            
            db_service = DatabaseService()
            
            with db_service.get_session() as session:
                from models import Client
                
                today = date.today()
                
                # Find overdue clients
                overdue_clients = session.query(Client).filter(
                    Client.due_date < today,
                    Client.status == 'active'
                ).all()
                
                # Update status to inactive
                for client in overdue_clients:
                    client.status = 'inactive'
                    logger.info(f"Marked client {client.name} as inactive (overdue)")
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error checking due dates: {e}")

    def _send_user_notifications(self):
        """Send daily notifications to users about their clients' due dates"""
        logger.info("Running daily user notifications")
        
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Run the user notifications
            self.loop.run_until_complete(self._process_user_notifications())
            
        except Exception as e:
            logger.error(f"Error sending user notifications: {e}")
        finally:
            if self.loop:
                self.loop.close()

    async def _process_user_notifications(self):
        """Process and send daily notifications to users via Telegram"""
        from services.database_service import DatabaseService
        from services.telegram_service import telegram_service
        from models import Client, User
        
        db_service = DatabaseService()
        
        today = date.today()
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = today + timedelta(days=2)
        
        try:
            with db_service.get_session() as session:
                # Get all active users
                users = session.query(User).filter_by(is_active=True).all()
                
                for user in users:
                    # Get clients by due date categories
                    overdue_clients = session.query(Client).filter_by(
                        user_id=user.id,
                        status='active'
                    ).filter(Client.due_date < today).all()
                    
                    due_today = session.query(Client).filter_by(
                        user_id=user.id,
                        due_date=today,
                        status='active'
                    ).all()
                    
                    due_tomorrow = session.query(Client).filter_by(
                        user_id=user.id,
                        due_date=tomorrow,
                        status='active'
                    ).all()
                    
                    due_day_after = session.query(Client).filter_by(
                        user_id=user.id,
                        due_date=day_after_tomorrow,
                        status='active'
                    ).all()
                    
                    # Only send notification if there are clients to report
                    if overdue_clients or due_today or due_tomorrow or due_day_after:
                        notification_text = self._build_notification_message(
                            overdue_clients, due_today, due_tomorrow, due_day_after
                        )
                        
                        # Send notification to user
                        success = await telegram_service.send_notification(
                            user.telegram_id, notification_text
                        )
                        
                        if success:
                            logger.info(f"Sent daily notification to user {user.telegram_id}")
                        else:
                            logger.error(f"Failed to send notification to user {user.telegram_id}")
                
        except Exception as e:
            logger.error(f"Error processing user notifications: {e}")

    def _build_notification_message(self, overdue_clients, due_today, due_tomorrow, due_day_after):
        """Build the notification message for user"""
        message = "📅 **Relatório Diário de Vencimentos**\n\n"
        
        # Overdue clients
        if overdue_clients:
            message += f"🔴 **{len(overdue_clients)} cliente(s) em atraso:**\n"
            for client in overdue_clients[:5]:  # Show max 5
                days_overdue = (date.today() - client.due_date).days
                message += f"• {client.name} - {days_overdue} dia(s) de atraso\n"
            if len(overdue_clients) > 5:
                message += f"• ... e mais {len(overdue_clients) - 5} cliente(s)\n"
            message += "\n"
        
        # Due today
        if due_today:
            message += f"🟡 **{len(due_today)} cliente(s) vencem hoje:**\n"
            for client in due_today[:5]:  # Show max 5
                message += f"• {client.name} - R$ {client.plan_price:.2f}\n"
            if len(due_today) > 5:
                message += f"• ... e mais {len(due_today) - 5} cliente(s)\n"
            message += "\n"
        
        # Due tomorrow
        if due_tomorrow:
            message += f"🟠 **{len(due_tomorrow)} cliente(s) vencem amanhã:**\n"
            for client in due_tomorrow[:5]:  # Show max 5
                message += f"• {client.name} - R$ {client.plan_price:.2f}\n"
            if len(due_tomorrow) > 5:
                message += f"• ... e mais {len(due_tomorrow) - 5} cliente(s)\n"
            message += "\n"
        
        # Due day after tomorrow
        if due_day_after:
            message += f"🔵 **{len(due_day_after)} cliente(s) vencem em 2 dias:**\n"
            for client in due_day_after[:5]:  # Show max 5
                message += f"• {client.name} - R$ {client.plan_price:.2f}\n"
            if len(due_day_after) > 5:
                message += f"• ... e mais {len(due_day_after) - 5} cliente(s)\n"
            message += "\n"
        
        message += "📱 Use o menu **👥 Clientes** para gerenciar seus clientes."
        
        return message

    async def _process_reminders(self):
        """Process and send reminder messages"""
        from services.database_service import DatabaseService
        from services.whatsapp_service import WhatsAppService
        from models import Client, User, MessageTemplate, MessageLog
        
        db_service = DatabaseService()
        whatsapp_service = WhatsAppService()
        
        today = date.today()
        
        # Calculate reminder dates
        reminder_2_days = today + timedelta(days=2)
        reminder_1_day = today + timedelta(days=1)
        
        try:
            with db_service.get_session() as session:
                # Get all active users
                users = session.query(User).filter_by(is_active=True).all()
                
                for user in users:
                    # Process each type of reminder
                    await self._send_reminder_type(session, user, today, 'reminder_due_date', whatsapp_service)
                    await self._send_reminder_type(session, user, reminder_1_day, 'reminder_1_day', whatsapp_service)
                    await self._send_reminder_type(session, user, reminder_2_days, 'reminder_2_days', whatsapp_service)
                    
                    # Send overdue reminders (1 day after due date)
                    overdue_date = today - timedelta(days=1)
                    await self._send_reminder_type(session, user, overdue_date, 'reminder_overdue', whatsapp_service)
                
        except Exception as e:
            logger.error(f"Error processing reminders: {e}")

    async def _process_evening_reminders(self):
        """Process evening reminders for next day due dates"""
        from services.database_service import DatabaseService
        from services.whatsapp_service import WhatsAppService
        from models import Client, User, MessageTemplate, MessageLog
        
        db_service = DatabaseService()
        whatsapp_service = WhatsAppService()
        
        tomorrow = date.today() + timedelta(days=1)
        
        try:
            with db_service.get_session() as session:
                users = session.query(User).filter_by(is_active=True).all()
                
                for user in users:
                    await self._send_reminder_type(session, user, tomorrow, 'reminder_1_day', whatsapp_service)
                
        except Exception as e:
            logger.error(f"Error processing evening reminders: {e}")

    async def _send_reminder_type(self, session, user, target_date, reminder_type, whatsapp_service):
        """Send specific type of reminder"""
        from models import Client, MessageTemplate, MessageLog
        
        try:
            # Get template for this reminder type
            template = session.query(MessageTemplate).filter_by(
                user_id=user.id,
                template_type=reminder_type,
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"No template found for {reminder_type} for user {user.id}")
                return
            
            # Get clients with due date matching target date and auto reminders enabled
            clients = session.query(Client).filter_by(
                user_id=user.id,
                due_date=target_date,
                status='active',
                auto_reminders_enabled=True
            ).all()
            
            for client in clients:
                # Check if message was already sent today for this reminder type
                existing_log = session.query(MessageLog).filter_by(
                    user_id=user.id,
                    client_id=client.id,
                    template_id=template.id
                ).filter(
                    MessageLog.sent_at >= datetime.combine(date.today(), datetime.min.time())
                ).first()
                
                if existing_log:
                    logger.info(f"Message already sent today for client {client.name}, type {reminder_type}")
                    continue
                
                # Replace variables in template
                message_content = self._replace_template_variables(template.content, client)
                
                # Send message
                result = whatsapp_service.send_message(client.phone_number, message_content, user.id)
                
                if result.get('success'):
                    # Log the message
                    message_log = MessageLog(
                        user_id=user.id,
                        client_id=client.id,
                        template_id=template.id,
                        message_content=message_content,
                        sent_at=datetime.now(),
                        status='sent'
                    )
                    session.add(message_log)
                    logger.info(f"Sent {reminder_type} reminder to {client.name}")
                else:
                    # Log failed message
                    message_log = MessageLog(
                        user_id=user.id,
                        client_id=client.id,
                        template_id=template.id,
                        message_content=message_content,
                        sent_at=datetime.now(),
                        status='failed'
                    )
                    session.add(message_log)
                    logger.error(f"Failed to send {reminder_type} reminder to {client.name}")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error sending {reminder_type} reminders: {e}")

    def _replace_template_variables(self, template_content, client):
        """Replace template variables with client data"""
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

    async def _send_reminders_by_type(self, session, user, clients, reminder_type, whatsapp_service):
        """Send reminders to specific clients by type"""
        from models import MessageTemplate, MessageLog
        
        try:
            # Get template for this reminder type
            template = session.query(MessageTemplate).filter_by(
                user_id=user.id,
                template_type=reminder_type,
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"No template found for {reminder_type} for user {user.id}")
                return
            
            for client in clients:
                # Check if message was already sent today for this reminder type
                existing_log = session.query(MessageLog).filter_by(
                    user_id=user.id,
                    client_id=client.id,
                    template_type=reminder_type
                ).filter(
                    MessageLog.sent_at >= datetime.combine(date.today(), datetime.min.time())
                ).first()
                
                if existing_log:
                    logger.info(f"Message already sent today for client {client.name}, type {reminder_type}")
                    continue
                
                # Replace variables in template
                message_content = self._replace_template_variables(template.content, client)
                
                # Send message
                result = whatsapp_service.send_message(client.phone_number, message_content, user.id)
                
                if result.get('success'):
                    # Log the message
                    message_log = MessageLog(
                        user_id=user.id,
                        client_id=client.id,
                        template_type=reminder_type,
                        recipient_phone=client.phone_number,
                        message_content=message_content,
                        sent_at=datetime.now(),
                        status='sent'
                    )
                    session.add(message_log)
                    logger.info(f"Sent {reminder_type} reminder to {client.name} ({client.phone_number})")
                else:
                    # Log failed message
                    error_msg = result.get('error', 'WhatsApp send failed')
                    message_log = MessageLog(
                        user_id=user.id,
                        client_id=client.id,
                        template_type=reminder_type,
                        recipient_phone=client.phone_number,
                        message_content=message_content,
                        sent_at=datetime.now(),
                        status='failed',
                        error_message=error_msg
                    )
                    session.add(message_log)
                    logger.error(f"Failed to send {reminder_type} reminder to {client.name}: {error_msg}")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error sending {reminder_type} reminders: {e}")

    async def _process_daily_reminders_for_user(self, user_id):
        """Process daily reminders for a specific user - sends reminders for all client statuses"""
        try:
            from services.database_service import DatabaseService
            from services.whatsapp_service import whatsapp_service
            from models import User, Client, MessageTemplate, MessageLog
            from datetime import date, timedelta
            
            db_service = DatabaseService()
            
            with db_service.get_session() as session:
                user = session.query(User).filter_by(id=user_id, is_active=True).first()
                
                if not user:
                    logger.warning(f"User {user_id} not found or inactive")
                    return
                
                today = date.today()
                logger.info(f"Processing daily reminders for user {user_id} on {today}")
                
                # Get clients due in 2 days
                clients_2_days = session.query(Client).filter_by(
                    user_id=user.id,
                    due_date=today + timedelta(days=2),
                    status='active',
                    auto_reminders_enabled=True
                ).all()
                
                # Get clients due tomorrow
                clients_1_day = session.query(Client).filter_by(
                    user_id=user.id,
                    due_date=today + timedelta(days=1),
                    status='active',
                    auto_reminders_enabled=True
                ).all()
                
                # Get clients due today
                clients_due_today = session.query(Client).filter_by(
                    user_id=user.id,
                    due_date=today,
                    status='active',
                    auto_reminders_enabled=True
                ).all()
                
                # Get clients overdue (1 day)
                clients_overdue = session.query(Client).filter_by(
                    user_id=user.id,
                    status='active',
                    auto_reminders_enabled=True
                ).filter(Client.due_date == today - timedelta(days=1)).all()
                
                logger.info(f"Found clients for user {user_id}: 2days={len(clients_2_days)}, 1day={len(clients_1_day)}, today={len(clients_due_today)}, overdue={len(clients_overdue)}")
                
                # Send reminder messages for each category
                if clients_2_days:
                    await self._send_reminders_by_type(session, user, clients_2_days, 'reminder_2_days', whatsapp_service)
                
                if clients_1_day:
                    await self._send_reminders_by_type(session, user, clients_1_day, 'reminder_1_day', whatsapp_service)
                
                if clients_due_today:
                    await self._send_reminders_by_type(session, user, clients_due_today, 'reminder_due_date', whatsapp_service)
                
                if clients_overdue:
                    await self._send_reminders_by_type(session, user, clients_overdue, 'reminder_overdue', whatsapp_service)
                
        except Exception as e:
            logger.error(f"Error processing daily reminders for user {user_id}: {e}")


    async def _process_user_notifications_for_user(self, user_id):
        """Process daily user notifications for specific user"""
        try:
            from services.database_service import DatabaseService
            from services.telegram_service import telegram_service
            from models import User, Client
            
            db_service = DatabaseService()
            
            with db_service.get_session() as session:
                user = session.query(User).filter_by(id=user_id, is_active=True).first()
                
                if not user:
                    return
                
                # Get all clients for this user
                clients = session.query(Client).filter_by(user_id=user.id).all()
                
                if not clients:
                    return
                
                today = date.today()
                tomorrow = today + timedelta(days=1)
                day_after = today + timedelta(days=2)
                
                # Categorize clients
                overdue = [c for c in clients if c.due_date < today and c.status == 'active']
                due_today = [c for c in clients if c.due_date == today and c.status == 'active']
                due_tomorrow = [c for c in clients if c.due_date == tomorrow and c.status == 'active']
                due_in_2_days = [c for c in clients if c.due_date == day_after and c.status == 'active']
                
                # Only send notification if there are relevant clients
                if overdue or due_today or due_tomorrow or due_in_2_days:
                    notification_text = self._build_notification_message(
                        overdue, due_today, due_tomorrow, due_in_2_days
                    )
                    
                    await telegram_service.send_notification(user.telegram_id, notification_text)
                    logger.info(f"Sent daily notification to user {user.telegram_id}")
        
        except Exception as e:
            logger.error(f"Error processing daily notifications for user {user_id}: {e}")

    def _check_trial_expiration(self, user, current_date):
        """Check if user's trial period has expired and send payment notification"""
        try:
            if not user.is_trial:
                return  # User is not on trial
                
            from datetime import timedelta
            trial_end_date = user.created_at.date() + timedelta(days=7)
            days_until_expiry = (trial_end_date - current_date).days
            
            # Check if trial expires today or has expired
            if days_until_expiry <= 0 and user.is_active:
                logger.info(f"Trial expired for user {user.id}, sending payment notification")
                
                # Deactivate user
                from services.database_service import DatabaseService
                db_service = DatabaseService()
                
                with db_service.get_session() as session:
                    # Update user status
                    db_user = session.query(User).filter_by(id=user.id).first()
                    if db_user:
                        db_user.is_active = False
                        session.commit()
                        
                        # Send payment notification
                        future = asyncio.run_coroutine_threadsafe(
                            self._send_payment_notification(user.telegram_id),
                            self._get_event_loop()
                        )
                        try:
                            future.result(timeout=15)
                        except Exception as e:
                            logger.error(f"Error sending payment notification: {e}")
                        
            elif days_until_expiry == 1:
                # Send reminder 1 day before expiry
                logger.info(f"Sending trial expiry reminder for user {user.id} (1 day left)")
                future = asyncio.run_coroutine_threadsafe(
                    self._send_trial_reminder(user.telegram_id, days_until_expiry),
                    self._get_event_loop()
                )
                try:
                    future.result(timeout=15)
                except Exception as e:
                    logger.error(f"Error sending trial reminder: {e}")
                
        except Exception as e:
            logger.error(f"Error checking trial expiration for user {user.id}: {e}")

    async def _send_payment_notification(self, telegram_id):
        """Send payment notification when trial expires"""
        try:
            from services.telegram_service import telegram_service
            
            message = """
⚠️ **Seu período de teste expirou!**

Seu teste gratuito de 7 dias chegou ao fim. Para continuar usando todas as funcionalidades do bot, você precisa ativar a assinatura mensal.

💰 **Assinatura:** R$ 20,00/mês
✅ **Inclui:**
• Gestão ilimitada de clientes
• Lembretes automáticos via WhatsApp  
• Controle de vencimentos
• Relatórios detalhados
• Suporte prioritário

🔗 Use o comando /start para assinar e reativar sua conta!
"""
            
            await telegram_service.send_notification(telegram_id, message)
            logger.info(f"Payment notification sent to user {telegram_id}")
            
        except Exception as e:
            logger.error(f"Error sending payment notification: {e}")

    async def _send_trial_reminder(self, telegram_id, days_left):
        """Send trial expiry reminder"""
        try:
            from services.telegram_service import telegram_service
            
            message = f"""
⏰ **Lembrete: Seu teste expira em {days_left} dia(s)!**

Seu período gratuito está chegando ao fim. Não perca o acesso às suas funcionalidades!

💰 **Assinatura:** R$ 20,00/mês
🎯 **Mantenha:**
• Todos os seus clientes cadastrados
• Lembretes automáticos configurados
• Histórico de mensagens

Para assinar e garantir a continuidade, use o comando /start quando seu teste expirar.
"""
            
            await telegram_service.send_notification(telegram_id, message)
            logger.info(f"Trial reminder sent to user {telegram_id}")
            
        except Exception as e:
            logger.error(f"Error sending trial reminder: {e}")

# Global scheduler service instance
scheduler_service = SchedulerService()