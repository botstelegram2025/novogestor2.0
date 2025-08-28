import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
import pytz
from config import Config

logger = logging.getLogger(__name__)

def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Validate and format phone number
    Returns: (is_valid, formatted_phone)
    """
    try:
        # Remove all non-digit characters
        clean_phone = re.sub(r'\D', '', phone)
        
        # Check length (10-11 digits for Brazil)
        if len(clean_phone) < 10 or len(clean_phone) > 11:
            return False, "Número deve ter 10 ou 11 dígitos"
        
        # Add country code if not present
        if not clean_phone.startswith('55'):
            clean_phone = '55' + clean_phone
        
        return True, clean_phone
        
    except Exception as e:
        logger.error(f"Error validating phone number: {e}")
        return False, "Erro na validação do número"

def validate_email(email: str) -> bool:
    """
    Validate email format
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def format_currency(amount: float) -> str:
    """
    Format amount as Brazilian currency
    """
    try:
        return f"R$ {amount:.2f}".replace('.', ',')
    except (ValueError, TypeError):
        return "R$ 0,00"

def parse_currency(currency_str: str) -> Optional[float]:
    """
    Parse currency string to float
    """
    try:
        # Remove currency symbols and normalize
        clean_str = re.sub(r'[R$\s]', '', currency_str)
        clean_str = clean_str.replace(',', '.')
        return float(clean_str)
    except (ValueError, TypeError):
        return None

def validate_date(date_str: str, date_format: str = '%d/%m/%Y') -> tuple[bool, Optional[date]]:
    """
    Validate and parse date string
    Returns: (is_valid, parsed_date)
    """
    try:
        parsed_date = datetime.strptime(date_str, date_format).date()
        return True, parsed_date
    except ValueError:
        return False, None

def format_date(date_obj: date, format_str: str = '%d/%m/%Y') -> str:
    """
    Format date object to string
    """
    try:
        return date_obj.strftime(format_str)
    except (AttributeError, ValueError):
        return ""

def get_timezone():
    """
    Get configured timezone
    """
    return pytz.timezone(Config.TIMEZONE)

def get_local_time() -> datetime:
    """
    Get current time in configured timezone
    """
    tz = get_timezone()
    return datetime.now(tz)

def days_until_date(target_date: date) -> int:
    """
    Calculate days until target date
    """
    today = date.today()
    return (target_date - today).days

def is_date_in_range(check_date: date, start_date: date, end_date: date) -> bool:
    """
    Check if date is within range (inclusive)
    """
    return start_date <= check_date <= end_date

def generate_unique_reference(prefix: str = "REF") -> str:
    """
    Generate unique reference string
    """
    timestamp = int(datetime.now().timestamp())
    return f"{prefix}_{timestamp}"

def sanitize_text(text: str, max_length: int = 255) -> str:
    """
    Sanitize text input
    """
    if not text:
        return ""
    
    # Remove extra whitespace
    sanitized = re.sub(r'\s+', ' ', text.strip())
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()
    
    return sanitized

def validate_due_date(due_date: date, min_days_ahead: int = 0) -> tuple[bool, str]:
    """
    Validate due date
    """
    today = date.today()
    min_date = today + timedelta(days=min_days_ahead)
    
    if due_date < min_date:
        if min_days_ahead == 0:
            return False, "Data não pode ser no passado"
        else:
            return False, f"Data deve ser pelo menos {min_days_ahead} dias à frente"
    
    # Check if date is too far in the future (e.g., more than 2 years)
    max_date = today + timedelta(days=730)  # 2 years
    if due_date > max_date:
        return False, "Data muito distante no futuro"
    
    return True, ""

def calculate_business_days(start_date: date, end_date: date) -> int:
    """
    Calculate business days between two dates (excluding weekends)
    """
    if start_date > end_date:
        return 0
    
    business_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Monday = 0, Sunday = 6
        if current_date.weekday() < 5:  # Monday to Friday
            business_days += 1
        current_date += timedelta(days=1)
    
    return business_days

def format_phone_display(phone: str) -> str:
    """
    Format phone number for display
    """
    try:
        clean_phone = re.sub(r'\D', '', phone)
        
        # Remove country code for display
        if clean_phone.startswith('55'):
            clean_phone = clean_phone[2:]
        
        # Format as (XX) XXXXX-XXXX or (XX) XXXX-XXXX
        if len(clean_phone) == 11:
            return f"({clean_phone[:2]}) {clean_phone[2:7]}-{clean_phone[7:]}"
        elif len(clean_phone) == 10:
            return f"({clean_phone[:2]}) {clean_phone[2:6]}-{clean_phone[6:]}"
        else:
            return phone
            
    except Exception:
        return phone

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text with suffix if longer than max_length
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def get_reminder_days() -> list[int]:
    """
    Get configured reminder days
    """
    return Config.REMINDER_DAYS

def is_business_hour(hour: int = None) -> bool:
    """
    Check if current time (or specified hour) is within business hours
    """
    if hour is None:
        current_time = get_local_time()
        hour = current_time.hour
    
    # Business hours: 8 AM to 6 PM
    return 8 <= hour <= 18

def mask_sensitive_data(data: str, mask_char: str = "*", show_last: int = 4) -> str:
    """
    Mask sensitive data showing only last N characters
    """
    if not data or len(data) <= show_last:
        return data
    
    masked_length = len(data) - show_last
    return mask_char * masked_length + data[-show_last:]

def parse_callback_data(callback_data: str) -> tuple[str, list]:
    """
    Parse callback data into action and parameters
    """
    parts = callback_data.split('_')
    action = parts[0]
    params = parts[1:] if len(parts) > 1 else []
    return action, params

def build_callback_data(action: str, *params) -> str:
    """
    Build callback data from action and parameters
    """
    parts = [action] + [str(p) for p in params]
    return '_'.join(parts)

def log_user_action(user_id: str, action: str, details: str = None):
    """
    Log user action for audit purposes
    """
    try:
        log_message = f"User {user_id} performed action: {action}"
        if details:
            log_message += f" - {details}"
        logger.info(log_message)
    except Exception as e:
        logger.error(f"Error logging user action: {e}")

def handle_database_error(error: Exception, operation: str) -> str:
    """
    Handle database errors and return user-friendly message
    """
    logger.error(f"Database error during {operation}: {error}")
    
    error_str = str(error).lower()
    
    if 'connection' in error_str:
        return "Erro de conexão com o banco de dados. Tente novamente."
    elif 'timeout' in error_str:
        return "Operação demorou muito para responder. Tente novamente."
    elif 'unique' in error_str or 'duplicate' in error_str:
        return "Este registro já existe."
    else:
        return "Erro interno. Tente novamente mais tarde."

def validate_user_permissions(user, required_status: str = 'active') -> tuple[bool, str]:
    """
    Validate user permissions
    """
    if not user:
        return False, "Usuário não encontrado."
    
    if not user.is_active:
        return False, "Conta inativa. Assine o plano para continuar."
    
    if required_status == 'trial_or_active':
        if user.is_trial:
            trial_days_left = (user.trial_end_date - datetime.utcnow()).days
            if trial_days_left <= 0:
                return False, "Período de teste expirado."
        elif not user.next_due_date or user.next_due_date < datetime.utcnow():
            return False, "Assinatura vencida."
    
    return True, ""
