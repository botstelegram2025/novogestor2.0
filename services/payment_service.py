import mercadopago
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.sdk = mercadopago.SDK(Config.MERCADO_PAGO_ACCESS_TOKEN)
    
    def create_subscription_payment(self, user_telegram_id: str, amount: float = None, method: str = "pix") -> Dict[str, Any]:
        """
        Create a PIX payment for monthly subscription
        """
        try:
            if amount is None:
                amount = Config.MONTHLY_SUBSCRIPTION_PRICE
            
            return self._create_pix_payment(user_telegram_id, amount)
                
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return {
                'success': False,
                'error': 'Payment service error',
                'details': str(e)
            }
    
    def _create_pix_payment(self, user_telegram_id: str, amount: float) -> Dict[str, Any]:
        """Create PIX payment"""
        try:
            # Payment data for PIX
            payment_data = {
                "transaction_amount": amount,
                "description": f"Assinatura Mensal - Bot Telegram - {user_telegram_id}",
                "payment_method_id": "pix",
                "payer": {
                    "email": f"user_{user_telegram_id}@telegram.bot",
                    "identification": {
                        "type": "CPF",
                        "number": "00000000000"  # Default for Telegram users
                    }
                },
                "notification_url": f"https://your-webhook-url.com/webhook/mercadopago",
                "external_reference": f"telegram_bot_{user_telegram_id}_{int(datetime.now().timestamp())}",
                "date_of_expiration": (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S.000-03:00')
            }
            
            # Create payment
            payment_response = self.sdk.payment().create(payment_data)
            payment = payment_response["response"]
            
            if payment_response["status"] == 201:
                logger.info(f"PIX payment created successfully for user {user_telegram_id}")
                
                return {
                    'success': True,
                    'payment_id': payment["id"],
                    'status': payment["status"],
                    'qr_code': payment["point_of_interaction"]["transaction_data"]["qr_code"],
                    'qr_code_base64': payment["point_of_interaction"]["transaction_data"]["qr_code_base64"],
                    'amount': payment["transaction_amount"],
                    'expires_at': payment["date_of_expiration"],
                    'payment_data': payment
                }
            else:
                logger.error(f"Failed to create PIX payment: {payment_response}")
                return {
                    'success': False,
                    'error': 'Payment creation failed',
                    'details': payment_response
                }
                
        except Exception as e:
            logger.error(f"Error creating PIX payment: {e}")
            return {
                'success': False,
                'error': 'Payment service error',
                'details': str(e)
            }
    
    
    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Check payment status by ID
        """
        try:
            payment_response = self.sdk.payment().get(payment_id)
            payment = payment_response["response"]
            
            if payment_response["status"] == 200:
                return {
                    'success': True,
                    'payment_id': payment["id"],
                    'status': payment["status"],
                    'status_detail': payment["status_detail"],
                    'amount': payment["transaction_amount"],
                    'date_approved': payment.get("date_approved"),
                    'payment_data': payment
                }
            else:
                logger.error(f"Failed to check payment status: {payment_response}")
                return {
                    'success': False,
                    'error': 'Payment status check failed',
                    'details': payment_response
                }
                
        except Exception as e:
            logger.error(f"Error checking payment status: {e}")
            return {
                'success': False,
                'error': 'Payment service error',
                'details': str(e)
            }
    
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process Mercado Pago webhook notification
        """
        try:
            if webhook_data.get("type") == "payment":
                payment_id = webhook_data.get("data", {}).get("id")
                
                if payment_id:
                    # Check payment status
                    payment_status = self.check_payment_status(str(payment_id))
                    
                    if payment_status['success']:
                        return {
                            'success': True,
                            'payment_id': payment_id,
                            'status': payment_status['status'],
                            'action_required': payment_status['status'] == 'approved'
                        }
            
            return {
                'success': False,
                'error': 'Invalid webhook data',
                'details': webhook_data
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return {
                'success': False,
                'error': 'Webhook processing error',
                'details': str(e)
            }

# Global payment service instance
payment_service = PaymentService()
