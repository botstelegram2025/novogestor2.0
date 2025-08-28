import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        # Support Railway environment with internal service communication
        import os
        railway_internal_url = os.getenv('RAILWAY_STATIC_URL')
        if railway_internal_url:
            self.baileys_url = f"https://{railway_internal_url}"
        else:
            self.baileys_url = "http://localhost:3001"
        
        self.headers = {
            'Content-Type': 'application/json'
        }
        logger.info(f"WhatsApp Service initialized with URL: {self.baileys_url}")
    
    def send_message(self, phone_number: str, message: str, user_id: int) -> Dict[str, Any]:
        """
        Send WhatsApp message via Baileys with auto-recovery
        """
        try:
            # Format phone number (remove non-digits and ensure country code)
            clean_phone = ''.join(filter(str.isdigit, phone_number))
            if not clean_phone.startswith('55'):
                clean_phone = '55' + clean_phone
            
            # Prepare payload for Baileys
            payload = {
                'number': clean_phone,
                'message': message
            }
            
            # Send to local Baileys server with user isolation
            url = f"{self.baileys_url}/send/{user_id}"
            
            logger.info(f"Sending WhatsApp message to {clean_phone}")
            
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=45  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    logger.info(f"WhatsApp message sent successfully to {clean_phone}")
                    return {
                        'success': True,
                        'message_id': result.get('messageId'),
                        'response': result
                    }
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"Failed to send WhatsApp message: {error_msg}")
                    
                    # Try to restore session if WhatsApp not connected
                    if 'não conectado' in error_msg.lower() or 'not connected' in error_msg.lower():
                        logger.info(f"Attempting to restore WhatsApp session for user {user_id}")
                        restore_result = self.restore_session(user_id)
                        if restore_result.get('success'):
                            logger.info(f"Session restore initiated for user {user_id}")
                        
                    return {
                        'success': False,
                        'error': error_msg,
                        'details': result
                    }
            else:
                logger.error(f"Failed to send WhatsApp message: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except requests.exceptions.Timeout:
            logger.error("WhatsApp API timeout")
            return {
                'success': False,
                'error': 'Timeout',
                'details': 'API request timed out'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"WhatsApp API request error: {e}")
            return {
                'success': False,
                'error': 'Request failed',
                'details': str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error sending WhatsApp message: {e}")
            return {
                'success': False,
                'error': 'Unexpected error',
                'details': str(e)
            }
    
    def restore_session(self, user_id: int) -> Dict[str, Any]:
        """
        Attempt to restore WhatsApp session for user
        """
        try:
            url = f"{self.baileys_url}/restore/{user_id}"
            
            response = requests.post(
                url,
                headers=self.headers,
                timeout=30  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Session restore response for user {user_id}: {result}")
                return result
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error restoring WhatsApp session for user {user_id}: {e}")
            return {
                'success': False,
                'error': 'Restore failed',
                'details': str(e)
            }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of WhatsApp server
        """
        try:
            url = f"{self.baileys_url}/health"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error getting WhatsApp health status: {e}")
            return {
                'success': False,
                'error': 'Health check failed',
                'details': str(e)
            }
    
    def check_instance_status(self, user_id: int) -> Dict[str, Any]:
        """
        Check if WhatsApp instance is connected and ready
        """
        try:
            url = f"{self.baileys_url}/status/{user_id}"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Check if the status indicates a real connection issue
                state = result.get('state', 'unknown')
                connected = result.get('connected', False)
                
                # Log connection status for debugging
                if connected:
                    logger.info(f"WhatsApp status for user {user_id}: connected={connected}, state={state}")
                else:
                    logger.warning(f"WhatsApp status for user {user_id}: connected={connected}, state={state}")
                
                return {
                    'success': True,
                    'connected': connected,
                    'state': state,
                    'qrCode': result.get('qrCode'),  # ✅ Match the key name exactly
                    'response': result
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except requests.exceptions.ConnectionError:
            logger.error("Baileys server not running")
            return {
                'success': False,
                'error': 'Baileys server not running',
                'details': 'Please start the Baileys server on port 3001'
            }
        except Exception as e:
            logger.error(f"Error checking WhatsApp instance status: {e}")
            return {
                'success': False,
                'error': 'Status check failed',
                'details': str(e)
            }
    
    def request_pairing_code(self, user_id: int, phone_number: str) -> Dict[str, Any]:
        """
        Request pairing code for WhatsApp connection
        """
        try:
            url = f"{self.baileys_url}/pairing-code/{user_id}"
            
            payload = {
                'phoneNumber': phone_number
            }
            
            logger.info(f"Requesting pairing code for user {user_id} with phone {phone_number}")
            
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=45  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    logger.info(f"Pairing code generated successfully for user {user_id}")
                    return {
                        'success': True,
                        'pairing_code': result.get('pairingCode'),
                        'response': result
                    }
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"Failed to generate pairing code: {error_msg}")
                    return {
                        'success': False,
                        'error': error_msg,
                        'details': result
                    }
            else:
                logger.error(f"Failed to request pairing code: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except requests.exceptions.Timeout:
            logger.error("Timeout requesting pairing code")
            return {
                'success': False,
                'error': 'Timeout requesting pairing code'
            }
        except Exception as e:
            logger.error(f"Error requesting pairing code for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_pairing_code(self, user_id: int) -> Dict[str, Any]:
        """
        Get existing pairing code if available
        """
        try:
            url = f"{self.baileys_url}/pairing-code/{user_id}"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                logger.error(f"Failed to get pairing code: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error getting pairing code for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_qr_code(self, user_id: int) -> Dict[str, Any]:
        """
        Get QR code for WhatsApp connection - Uses status endpoint
        """
        try:
            # Use status endpoint instead of non-existent /qr endpoint
            url = f"{self.baileys_url}/status/{user_id}"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                # Extract QR code from status response
                if result.get('success') and result.get('qrCode'):
                    return {
                        'success': True,
                        'qrCode': result.get('qrCode'),
                        'state': result.get('state'),
                        'connected': result.get('connected')
                    }
                else:
                    return {
                        'success': False,
                        'error': 'QR Code not available in status',
                        'details': result
                    }
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error getting QR code: {e}")
            return {
                'success': False,
                'error': 'QR code fetch failed',
                'details': str(e)
            }
    
    def disconnect_whatsapp(self, user_id: int) -> Dict[str, Any]:
        """
        Disconnect WhatsApp
        """
        try:
            url = f"{self.baileys_url}/disconnect/{user_id}"
            
            response = requests.post(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error disconnecting WhatsApp: {e}")
            return {
                'success': False,
                'error': 'Disconnect failed',
                'details': str(e)
            }
    
    def reconnect_whatsapp(self, user_id: int) -> Dict[str, Any]:
        """
        Reconnect WhatsApp
        """
        try:
            url = f"{self.baileys_url}/reconnect/{user_id}"
            
            response = requests.post(
                url,
                headers=self.headers,
                timeout=20  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error reconnecting WhatsApp: {e}")
            return {
                'success': False,
                'error': 'Reconnect failed',
                'details': str(e)
            }
    
    def force_new_qr(self, user_id: int) -> Dict[str, Any]:
        """
        Force generate a new QR code - GUARANTEED to work
        """
        try:
            url = f"{self.baileys_url}/force-qr/{user_id}"
            
            response = requests.post(
                url,
                headers=self.headers,
                timeout=45  # Railway optimized timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                return {
                    'success': False,
                    'error': f"HTTP Error: {response.status_code}",
                    'details': response.text
                }
                
        except Exception as e:
            logger.error(f"Error forcing QR code: {e}")
            return {
                'success': False,
                'error': 'Force QR failed',
                'details': str(e)
            }
    
    def format_message(self, template: str, **kwargs) -> str:
        """
        Format message template with provided variables
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return template
        except Exception as e:
            logger.error(f"Error formatting message template: {e}")
            return template

# Global WhatsApp service instance
whatsapp_service = WhatsAppService()
