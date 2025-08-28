"""
Professional Input Validation System
Comprehensive validation with sanitization and security checks
"""
import re
import html
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from core.exceptions import ValidationError

class Validator:
    """Base validator class"""
    
    def __init__(self, required: bool = True, allow_none: bool = False):
        self.required = required
        self.allow_none = allow_none
    
    def validate(self, value: Any, field_name: str = "field") -> Any:
        """Main validation method"""
        # Check if value is None
        if value is None:
            if self.allow_none:
                return None
            if self.required:
                raise ValidationError(f"{field_name} is required", field=field_name)
            return None
        
        # Perform specific validation
        return self._validate_value(value, field_name)
    
    def _validate_value(self, value: Any, field_name: str) -> Any:
        """Override in subclasses"""
        return value

class StringValidator(Validator):
    """String validation with sanitization"""
    
    def __init__(self, 
                 min_length: int = 0,
                 max_length: int = 10000,
                 pattern: Optional[str] = None,
                 strip_whitespace: bool = True,
                 sanitize_html: bool = True,
                 allowed_chars: Optional[str] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = re.compile(pattern) if pattern else None
        self.strip_whitespace = strip_whitespace
        self.sanitize_html = sanitize_html
        self.allowed_chars = set(allowed_chars) if allowed_chars else None
    
    def _validate_value(self, value: Any, field_name: str) -> str:
        # Convert to string
        if not isinstance(value, str):
            value = str(value)
        
        # Strip whitespace if requested
        if self.strip_whitespace:
            value = value.strip()
        
        # Sanitize HTML if requested
        if self.sanitize_html:
            value = html.escape(value)
        
        # Check length
        if len(value) < self.min_length:
            raise ValidationError(
                f"{field_name} must be at least {self.min_length} characters long",
                field=field_name,
                value=value
            )
        
        if len(value) > self.max_length:
            raise ValidationError(
                f"{field_name} must be at most {self.max_length} characters long",
                field=field_name,
                value=value
            )
        
        # Check pattern
        if self.pattern and not self.pattern.match(value):
            raise ValidationError(
                f"{field_name} format is invalid",
                field=field_name,
                value=value
            )
        
        # Check allowed characters
        if self.allowed_chars and not set(value).issubset(self.allowed_chars):
            invalid_chars = set(value) - self.allowed_chars
            raise ValidationError(
                f"{field_name} contains invalid characters: {', '.join(invalid_chars)}",
                field=field_name,
                value=value
            )
        
        return value

class PhoneValidator(Validator):
    """Brazilian phone number validation"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Brazilian phone pattern: +55 (11) 99999-9999 or variations
        self.phone_pattern = re.compile(r'^\+?55\s*\(?(\d{2})\)?\s*9?\s*(\d{4,5})-?(\d{4})$')
    
    def _validate_value(self, value: Any, field_name: str) -> str:
        # Convert to string and clean
        phone = str(value).strip()
        
        # Remove common formatting
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Validate length (10-13 digits including country code)
        if len(phone) < 10 or len(phone) > 13:
            raise ValidationError(
                f"{field_name} must be a valid Brazilian phone number",
                field=field_name,
                value=value
            )
        
        # Add country code if missing
        if not phone.startswith('55'):
            if phone.startswith('+55'):
                phone = phone[1:]  # Remove + but keep 55
            elif len(phone) <= 11:
                phone = '55' + phone
        
        # Validate format
        if len(phone) not in [12, 13]:  # 55 + 10 or 11 digits
            raise ValidationError(
                f"{field_name} has invalid length for Brazilian phone",
                field=field_name,
                value=value
            )
        
        return phone

class EmailValidator(Validator):
    """Email validation"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email_pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
    
    def _validate_value(self, value: Any, field_name: str) -> str:
        email = str(value).strip().lower()
        
        if not self.email_pattern.match(email):
            raise ValidationError(
                f"{field_name} must be a valid email address",
                field=field_name,
                value=value
            )
        
        return email

class NumberValidator(Validator):
    """Numeric validation"""
    
    def __init__(self,
                 min_value: Optional[float] = None,
                 max_value: Optional[float] = None,
                 decimal_places: Optional[int] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.decimal_places = decimal_places
    
    def _validate_value(self, value: Any, field_name: str) -> float:
        try:
            if isinstance(value, str):
                # Handle Brazilian decimal format (comma as decimal separator)
                value = value.replace(',', '.')
            
            number = float(value)
            
            # Check range
            if self.min_value is not None and number < self.min_value:
                raise ValidationError(
                    f"{field_name} must be at least {self.min_value}",
                    field=field_name,
                    value=value
                )
            
            if self.max_value is not None and number > self.max_value:
                raise ValidationError(
                    f"{field_name} must be at most {self.max_value}",
                    field=field_name,
                    value=value
                )
            
            # Check decimal places
            if self.decimal_places is not None:
                decimal_value = Decimal(str(number))
                if decimal_value.as_tuple().exponent < -self.decimal_places:
                    raise ValidationError(
                        f"{field_name} cannot have more than {self.decimal_places} decimal places",
                        field=field_name,
                        value=value
                    )
            
            return number
            
        except (ValueError, InvalidOperation):
            raise ValidationError(
                f"{field_name} must be a valid number",
                field=field_name,
                value=value
            )

class DateValidator(Validator):
    """Date validation"""
    
    def __init__(self,
                 date_format: str = "%Y-%m-%d",
                 min_date: Optional[date] = None,
                 max_date: Optional[date] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.date_format = date_format
        self.min_date = min_date
        self.max_date = max_date
    
    def _validate_value(self, value: Any, field_name: str) -> date:
        if isinstance(value, date):
            parsed_date = value
        elif isinstance(value, datetime):
            parsed_date = value.date()
        else:
            try:
                # Try Brazilian format first (dd/mm/yyyy)
                if isinstance(value, str) and '/' in value:
                    parsed_date = datetime.strptime(value, "%d/%m/%Y").date()
                else:
                    parsed_date = datetime.strptime(str(value), self.date_format).date()
            except ValueError:
                raise ValidationError(
                    f"{field_name} must be a valid date in format {self.date_format}",
                    field=field_name,
                    value=value
                )
        
        # Check range
        if self.min_date and parsed_date < self.min_date:
            raise ValidationError(
                f"{field_name} cannot be before {self.min_date}",
                field=field_name,
                value=value
            )
        
        if self.max_date and parsed_date > self.max_date:
            raise ValidationError(
                f"{field_name} cannot be after {self.max_date}",
                field=field_name,
                value=value
            )
        
        return parsed_date

class ChoiceValidator(Validator):
    """Choice validation from a list of allowed values"""
    
    def __init__(self, choices: List[Any], case_sensitive: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.choices = choices
        self.case_sensitive = case_sensitive
        if not case_sensitive:
            self.choices_lower = [str(choice).lower() for choice in choices]
    
    def _validate_value(self, value: Any, field_name: str) -> Any:
        if self.case_sensitive:
            if value not in self.choices:
                raise ValidationError(
                    f"{field_name} must be one of: {', '.join(map(str, self.choices))}",
                    field=field_name,
                    value=value
                )
        else:
            value_lower = str(value).lower()
            if value_lower not in self.choices_lower:
                raise ValidationError(
                    f"{field_name} must be one of: {', '.join(map(str, self.choices))}",
                    field=field_name,
                    value=value
                )
            # Return the original case version
            index = self.choices_lower.index(value_lower)
            value = self.choices[index]
        
        return value

class ValidationSchema:
    """Schema for validating complex data structures"""
    
    def __init__(self, fields: Dict[str, Validator]):
        self.fields = fields
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against schema"""
        validated_data = {}
        errors = {}
        
        # Validate each field
        for field_name, validator in self.fields.items():
            try:
                value = data.get(field_name)
                validated_data[field_name] = validator.validate(value, field_name)
            except ValidationError as e:
                errors[field_name] = e.message
        
        # Check for unexpected fields
        unexpected_fields = set(data.keys()) - set(self.fields.keys())
        if unexpected_fields:
            for field in unexpected_fields:
                errors[field] = "Unexpected field"
        
        if errors:
            raise ValidationError(
                f"Validation failed: {errors}",
                context={'field_errors': errors}
            )
        
        return validated_data

# Common validation schemas
CLIENT_SCHEMA = ValidationSchema({
    'name': StringValidator(min_length=2, max_length=100),
    'phone_number': PhoneValidator(),
    'plan_name': StringValidator(min_length=1, max_length=50),
    'plan_price': NumberValidator(min_value=0.01, max_value=1000.0, decimal_places=2),
    'server_info': StringValidator(max_length=200, required=False),
    'due_date': DateValidator(min_date=date.today()),
    'other_info': StringValidator(max_length=500, required=False),
})

USER_SCHEMA = ValidationSchema({
    'phone_number': PhoneValidator(),
    'first_name': StringValidator(min_length=1, max_length=50),
})

TEMPLATE_SCHEMA = ValidationSchema({
    'name': StringValidator(min_length=2, max_length=100),
    'content': StringValidator(min_length=10, max_length=4000),
    'template_type': ChoiceValidator(['welcome', 'reminder_2_days', 'reminder_1_day', 
                                    'reminder_due_date', 'reminder_overdue', 'renewal']),
})