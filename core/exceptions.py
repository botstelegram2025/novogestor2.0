"""
Professional Exception Handling System
Defines custom exceptions with error codes and contexts
"""
from typing import Dict, Any, Optional
from enum import Enum

class ErrorCode(Enum):
    """Standard error codes for the application"""
    
    # General errors (1000-1999)
    UNKNOWN_ERROR = 1000
    VALIDATION_ERROR = 1001
    CONFIGURATION_ERROR = 1002
    AUTHENTICATION_ERROR = 1003
    AUTHORIZATION_ERROR = 1004
    RATE_LIMIT_EXCEEDED = 1005
    
    # Database errors (2000-2999)
    DATABASE_CONNECTION_ERROR = 2000
    DATABASE_QUERY_ERROR = 2001
    DATABASE_CONSTRAINT_ERROR = 2002
    DATABASE_TIMEOUT_ERROR = 2003
    
    # Telegram errors (3000-3999)
    TELEGRAM_API_ERROR = 3000
    TELEGRAM_WEBHOOK_ERROR = 3001
    TELEGRAM_MESSAGE_ERROR = 3002
    TELEGRAM_RATE_LIMIT = 3003
    
    # WhatsApp errors (4000-4999)
    WHATSAPP_CONNECTION_ERROR = 4000
    WHATSAPP_SEND_ERROR = 4001
    WHATSAPP_QR_ERROR = 4002
    WHATSAPP_SESSION_ERROR = 4003
    
    # Payment errors (5000-5999)
    PAYMENT_PROVIDER_ERROR = 5000
    PAYMENT_VALIDATION_ERROR = 5001
    PAYMENT_WEBHOOK_ERROR = 5002
    SUBSCRIPTION_ERROR = 5003
    
    # Business logic errors (6000-6999)
    USER_NOT_FOUND = 6000
    USER_INACTIVE = 6001
    CLIENT_NOT_FOUND = 6002
    SUBSCRIPTION_EXPIRED = 6003
    TEMPLATE_NOT_FOUND = 6004
    SCHEDULE_CONFLICT = 6005
    
    # External service errors (7000-7999)
    EXTERNAL_SERVICE_ERROR = 7000
    EXTERNAL_SERVICE_TIMEOUT = 7001
    EXTERNAL_SERVICE_UNAVAILABLE = 7002

class BaseAppException(Exception):
    """Base exception class for the application"""
    
    def __init__(self, 
                 message: str,
                 error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
                 context: Optional[Dict[str, Any]] = None,
                 cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.cause = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses"""
        return {
            'error_code': self.error_code.value,
            'error_name': self.error_code.name,
            'message': self.message,
            'context': self.context,
            'cause': str(self.cause) if self.cause else None
        }
    
    def __str__(self) -> str:
        return f"[{self.error_code.name}] {self.message}"

class ValidationError(BaseAppException):
    """Raised when input validation fails"""
    
    def __init__(self, message: str, field: str = None, value: Any = None):
        context = {}
        if field:
            context['field'] = field
        if value is not None:
            context['invalid_value'] = str(value)
        
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            context=context
        )

class DatabaseError(BaseAppException):
    """Database-related errors"""
    
    def __init__(self, message: str, operation: str = None, table: str = None):
        context = {}
        if operation:
            context['operation'] = operation
        if table:
            context['table'] = table
        
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_QUERY_ERROR,
            context=context
        )

class TelegramError(BaseAppException):
    """Telegram API related errors"""
    
    def __init__(self, message: str, api_method: str = None, response_code: int = None):
        context = {}
        if api_method:
            context['api_method'] = api_method
        if response_code:
            context['response_code'] = response_code
        
        super().__init__(
            message=message,
            error_code=ErrorCode.TELEGRAM_API_ERROR,
            context=context
        )

class WhatsAppError(BaseAppException):
    """WhatsApp service related errors"""
    
    def __init__(self, message: str, user_id: str = None, operation: str = None):
        context = {}
        if user_id:
            context['user_id'] = user_id
        if operation:
            context['operation'] = operation
        
        super().__init__(
            message=message,
            error_code=ErrorCode.WHATSAPP_CONNECTION_ERROR,
            context=context
        )

class PaymentError(BaseAppException):
    """Payment processing related errors"""
    
    def __init__(self, message: str, payment_id: str = None, provider: str = None):
        context = {}
        if payment_id:
            context['payment_id'] = payment_id
        if provider:
            context['provider'] = provider
        
        super().__init__(
            message=message,
            error_code=ErrorCode.PAYMENT_PROVIDER_ERROR,
            context=context
        )

class BusinessLogicError(BaseAppException):
    """Business logic related errors"""
    
    def __init__(self, message: str, entity_type: str = None, entity_id: str = None):
        context = {}
        if entity_type:
            context['entity_type'] = entity_type
        if entity_id:
            context['entity_id'] = entity_id
        
        super().__init__(
            message=message,
            error_code=ErrorCode.USER_NOT_FOUND,
            context=context
        )

class ExternalServiceError(BaseAppException):
    """External service related errors"""
    
    def __init__(self, message: str, service: str = None, endpoint: str = None):
        context = {}
        if service:
            context['service'] = service
        if endpoint:
            context['endpoint'] = endpoint
        
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            context=context
        )

class RateLimitError(BaseAppException):
    """Rate limiting related errors"""
    
    def __init__(self, message: str, limit: int = None, window: int = None):
        context = {}
        if limit:
            context['limit'] = limit
        if window:
            context['window'] = window
        
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            context=context
        )