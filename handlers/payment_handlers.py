from telegram import Update
from telegram.ext import ContextTypes
import logging
from datetime import datetime, timedelta
from services.database_service import db_service
from services.payment_service import payment_service
from models import User, Subscription

logger = logging.getLogger(__name__)

async def handle_payment_webhook(webhook_data: dict) -> bool:
    """
    Handle Mercado Pago webhook notifications
    This function should be called by a webhook endpoint
    """
    try:
        logger.info(f"Processing payment webhook: {webhook_data}")
        
        if webhook_data.get("type") != "payment":
            logger.info(f"Ignoring non-payment webhook: {webhook_data.get('type')}")
            return True
        
        payment_id = webhook_data.get("data", {}).get("id")
        if not payment_id:
            logger.error("No payment ID in webhook data")
            return False
        
        # Check payment status
        payment_status = payment_service.check_payment_status(str(payment_id))
        
        if not payment_status['success']:
            logger.error(f"Failed to check payment status: {payment_status}")
            return False
        
        # Update subscription in database
        with db_service.get_session() as session:
            subscription = session.query(Subscription).filter_by(
                payment_id=str(payment_id)
            ).first()
            
            if not subscription:
                logger.error(f"Subscription not found for payment ID: {payment_id}")
                return False
            
            old_status = subscription.status
            subscription.status = payment_status['status']
            
            if payment_status['status'] == 'approved':
                subscription.paid_at = datetime.utcnow()
                subscription.expires_at = datetime.utcnow() + timedelta(days=30)
                
                # Update user subscription
                user = session.query(User).get(subscription.user_id)
                if user:
                    user.is_trial = False
                    user.is_active = True
                    user.last_payment_date = datetime.utcnow()
                    user.next_due_date = subscription.expires_at
                    
                    logger.info(f"Payment approved for user {user.telegram_id}")
                    
                    # Here you could send a confirmation message to the user
                    # This would require having the bot instance available
                    
            elif payment_status['status'] in ['rejected', 'cancelled']:
                logger.info(f"Payment {payment_status['status']} for subscription {subscription.id}")
            
            session.commit()
            
            logger.info(f"Updated subscription {subscription.id}: {old_status} -> {subscription.status}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error processing payment webhook: {e}")
        return False

async def check_subscription_status(user_id: str) -> dict:
    """
    Check current subscription status for a user
    """
    try:
        with db_service.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            
            if not user:
                return {
                    'success': False,
                    'error': 'User not found'
                }
            
            # Check if user is in trial
            if user.is_trial:
                trial_days_left = (user.trial_end_date - datetime.utcnow()).days
                return {
                    'success': True,
                    'status': 'trial',
                    'is_active': user.is_active,
                    'days_left': max(0, trial_days_left),
                    'expires_at': user.trial_end_date
                }
            
            # Check subscription status
            if user.next_due_date:
                days_until_due = (user.next_due_date - datetime.utcnow()).days
                return {
                    'success': True,
                    'status': 'subscribed',
                    'is_active': user.is_active,
                    'days_left': max(0, days_until_due),
                    'expires_at': user.next_due_date,
                    'last_payment': user.last_payment_date
                }
            
            return {
                'success': True,
                'status': 'expired',
                'is_active': user.is_active,
                'days_left': 0
            }
            
    except Exception as e:
        logger.error(f"Error checking subscription status: {e}")
        return {
            'success': False,
            'error': str(e)
        }

async def get_pending_payments(user_id: str) -> list:
    """
    Get pending payments for a user
    """
    try:
        with db_service.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            
            if not user:
                return []
            
            pending_subscriptions = session.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == 'pending',
                Subscription.created_at > datetime.utcnow() - timedelta(hours=24)
            ).all()
            
            payments = []
            for sub in pending_subscriptions:
                if sub.payment_id:
                    # Check current status
                    payment_status = payment_service.check_payment_status(sub.payment_id)
                    
                    payments.append({
                        'subscription_id': sub.id,
                        'payment_id': sub.payment_id,
                        'amount': sub.amount,
                        'status': payment_status.get('status', 'pending'),
                        'created_at': sub.created_at,
                        'qr_code': sub.pix_qr_code
                    })
            
            return payments
            
    except Exception as e:
        logger.error(f"Error getting pending payments: {e}")
        return []

async def cancel_expired_payments():
    """
    Cancel payments that have expired (older than 24 hours and still pending)
    """
    try:
        with db_service.get_session() as session:
            expired_subscriptions = session.query(Subscription).filter(
                Subscription.status == 'pending',
                Subscription.created_at < datetime.utcnow() - timedelta(hours=24)
            ).all()
            
            for subscription in expired_subscriptions:
                subscription.status = 'expired'
                logger.info(f"Expired subscription {subscription.id}")
            
            if expired_subscriptions:
                session.commit()
                logger.info(f"Cancelled {len(expired_subscriptions)} expired payments")
                
    except Exception as e:
        logger.error(f"Error cancelling expired payments: {e}")

async def generate_payment_report(user_id: str) -> dict:
    """
    Generate payment report for a user
    """
    try:
        with db_service.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            
            if not user:
                return {'success': False, 'error': 'User not found'}
            
            subscriptions = session.query(Subscription).filter_by(
                user_id=user.id
            ).order_by(Subscription.created_at.desc()).all()
            
            report = {
                'success': True,
                'user_info': {
                    'telegram_id': user.telegram_id,
                    'is_trial': user.is_trial,
                    'is_active': user.is_active,
                    'trial_end_date': user.trial_end_date,
                    'last_payment_date': user.last_payment_date,
                    'next_due_date': user.next_due_date
                },
                'payments': [],
                'statistics': {
                    'total_payments': 0,
                    'approved_payments': 0,
                    'total_amount_paid': 0.0,
                    'pending_payments': 0
                }
            }
            
            for sub in subscriptions:
                payment_info = {
                    'id': sub.id,
                    'payment_id': sub.payment_id,
                    'amount': sub.amount,
                    'status': sub.status,
                    'created_at': sub.created_at,
                    'paid_at': sub.paid_at,
                    'expires_at': sub.expires_at
                }
                report['payments'].append(payment_info)
                
                # Update statistics
                report['statistics']['total_payments'] += 1
                if sub.status == 'approved':
                    report['statistics']['approved_payments'] += 1
                    report['statistics']['total_amount_paid'] += sub.amount
                elif sub.status == 'pending':
                    report['statistics']['pending_payments'] += 1
            
            return report
            
    except Exception as e:
        logger.error(f"Error generating payment report: {e}")
        return {'success': False, 'error': str(e)}
