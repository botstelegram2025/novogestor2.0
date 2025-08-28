"""
Professional Configuration Management System
Centralized configuration with validation and environment support
"""
import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class DatabaseConfig:
    """Database configuration with validation"""
    url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    pool_size: int = field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "10")))
    pool_timeout: int = field(default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30")))
    echo_queries: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")
    
    def __post_init__(self):
        if not self.url:
            raise ValueError("DATABASE_URL is required")

@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_WEBHOOK_URL"))
    max_connections: int = field(default_factory=lambda: int(os.getenv("TELEGRAM_MAX_CONNECTIONS", "40")))
    
    def __post_init__(self):
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

@dataclass
class WhatsAppConfig:
    """WhatsApp service configuration"""
    service_url: str = field(default_factory=lambda: os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001"))
    timeout: int = field(default_factory=lambda: int(os.getenv("WHATSAPP_TIMEOUT", "30")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("WHATSAPP_MAX_RETRIES", "3")))
    backoff_factor: float = field(default_factory=lambda: float(os.getenv("WHATSAPP_BACKOFF_FACTOR", "1.5")))

@dataclass
class PaymentConfig:
    """Payment service configuration"""
    mercado_pago_token: str = field(default_factory=lambda: os.getenv("MERCADO_PAGO_TOKEN", ""))
    webhook_secret: str = field(default_factory=lambda: os.getenv("MERCADO_PAGO_WEBHOOK_SECRET", ""))
    monthly_price: float = field(default_factory=lambda: float(os.getenv("MONTHLY_PRICE", "20.0")))
    trial_days: int = field(default_factory=lambda: int(os.getenv("TRIAL_DAYS", "7")))

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: LogLevel = field(default_factory=lambda: LogLevel(os.getenv("LOG_LEVEL", "INFO")))
    format: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", 
        "%(asctime)s | %(levelname)8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"))
    file_path: str = field(default_factory=lambda: os.getenv("LOG_FILE", "app.log"))
    max_file_size: int = field(default_factory=lambda: int(os.getenv("LOG_MAX_SIZE", "10485760")))  # 10MB
    backup_count: int = field(default_factory=lambda: int(os.getenv("LOG_BACKUP_COUNT", "5")))
    structured: bool = field(default_factory=lambda: os.getenv("LOG_STRUCTURED", "true").lower() == "true")

@dataclass
class SchedulerConfig:
    """Scheduler configuration"""
    check_interval: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_INTERVAL", "60")))
    max_workers: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_WORKERS", "5")))
    timeout: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_TIMEOUT", "300")))

@dataclass
class SecurityConfig:
    """Security configuration"""
    rate_limit_requests: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_REQUESTS", "100")))
    rate_limit_window: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW", "3600")))
    max_message_length: int = field(default_factory=lambda: int(os.getenv("MAX_MESSAGE_LENGTH", "4096")))
    allowed_file_types: list = field(default_factory=lambda: os.getenv("ALLOWED_FILE_TYPES", "jpg,jpeg,png,pdf").split(","))

@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration"""
    metrics_enabled: bool = field(default_factory=lambda: os.getenv("METRICS_ENABLED", "true").lower() == "true")
    health_check_interval: int = field(default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "30")))
    alerting_enabled: bool = field(default_factory=lambda: os.getenv("ALERTING_ENABLED", "false").lower() == "true")
    webhook_endpoint: Optional[str] = field(default_factory=lambda: os.getenv("MONITORING_WEBHOOK"))

@dataclass
class AppSettings:
    """Main application settings"""
    environment: Environment = field(default_factory=lambda: Environment(os.getenv("ENVIRONMENT", "development")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Client Management Bot"))
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "America/Sao_Paulo"))
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    def validate(self) -> bool:
        """Validate all configuration settings"""
        try:
            # Validate required configurations
            if not self.telegram.token:
                raise ValueError("TELEGRAM_BOT_TOKEN is required")
            
            if not self.database.url:
                raise ValueError("DATABASE_URL is required")
                
            # Validate numeric ranges
            if self.database.pool_size <= 0:
                raise ValueError("DB_POOL_SIZE must be positive")
                
            if self.payment.monthly_price <= 0:
                raise ValueError("MONTHLY_PRICE must be positive")
                
            if self.payment.trial_days < 0:
                raise ValueError("TRIAL_DAYS must be non-negative")
                
            return True
            
        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for logging/debugging"""
        result = {}
        for key, value in self.__dict__.items():
            if hasattr(value, '__dict__'):
                result[key] = value.__dict__
            else:
                result[key] = value
        
        # Mask sensitive data
        if 'telegram' in result and 'token' in result['telegram']:
            result['telegram']['token'] = result['telegram']['token'][:10] + "..."
        if 'payment' in result and 'mercado_pago_token' in result['payment']:
            result['payment']['mercado_pago_token'] = result['payment']['mercado_pago_token'][:10] + "..."
            
        return result

# Global settings instance
settings = AppSettings()

def get_settings() -> AppSettings:
    """Get application settings instance"""
    return settings

def validate_settings() -> bool:
    """Validate application settings"""
    return settings.validate()