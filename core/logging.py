"""
Professional Structured Logging System
Provides centralized, structured logging with context and correlation IDs
"""
import logging
import logging.handlers
import json
import traceback
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from contextvars import ContextVar
import uuid

# Context variables for request correlation
correlation_id_ctx: ContextVar[str] = ContextVar('correlation_id', default='')
user_id_ctx: ContextVar[str] = ContextVar('user_id', default='')
operation_ctx: ContextVar[str] = ContextVar('operation', default='')

class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for logs"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
            'correlation_id': correlation_id_ctx.get(''),
            'user_id': user_id_ctx.get(''),
            'operation': operation_ctx.get(''),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 
                          'msecs', 'relativeCreated', 'thread', 'threadName', 
                          'processName', 'process', 'message', 'exc_info', 'exc_text', 
                          'stack_info'):
                log_entry['extra'] = log_entry.get('extra', {})
                log_entry['extra'][key] = value
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)

class SimpleFormatter(logging.Formatter):
    """Human-readable formatter for development"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Add correlation context to message
        correlation_id = correlation_id_ctx.get('')
        user_id = user_id_ctx.get('')
        operation = operation_ctx.get('')
        
        context_parts = []
        if correlation_id:
            context_parts.append(f"correlation_id={correlation_id}")
        if user_id:
            context_parts.append(f"user_id={user_id}")
        if operation:
            context_parts.append(f"operation={operation}")
        
        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        
        # Format the base message
        original_format = super().format(record)
        return f"{original_format}{context_str}"

class LoggerManager:
    """Centralized logger management"""
    
    _instance = None
    _loggers: Dict[str, logging.Logger] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def setup_logging(self, 
                     level: str = "INFO",
                     format_str: Optional[str] = None,
                     file_path: Optional[str] = None,
                     max_file_size: int = 10485760,  # 10MB
                     backup_count: int = 5,
                     structured: bool = True):
        """Setup application-wide logging configuration"""
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level.upper()))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        
        if structured:
            console_formatter = StructuredFormatter()
        else:
            console_formatter = SimpleFormatter(
                format_str or '%(asctime)s | %(levelname)8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
            )
        
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # File handler if specified
        if file_path:
            file_handler = logging.handlers.RotatingFileHandler(
                file_path, 
                maxBytes=max_file_size, 
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(getattr(logging, level.upper()))
            
            if structured:
                file_formatter = StructuredFormatter()
            else:
                file_formatter = SimpleFormatter(
                    format_str or '%(asctime)s | %(levelname)8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
                )
            
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        
        # Set specific logger levels
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('telegram').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger with the specified name"""
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]

# Global logger manager instance
logger_manager = LoggerManager()

class LogContext:
    """Context manager for structured logging with correlation IDs"""
    
    def __init__(self, 
                 operation: str = '',
                 user_id: str = '',
                 correlation_id: Optional[str] = None,
                 **extra_context):
        self.operation = operation
        self.user_id = user_id
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.extra_context = extra_context
        self.tokens = []
    
    def __enter__(self):
        # Set context variables
        self.tokens.append(('correlation_id', correlation_id_ctx.set(self.correlation_id)))
        self.tokens.append(('user_id', user_id_ctx.set(self.user_id)))
        self.tokens.append(('operation', operation_ctx.set(self.operation)))
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context variables
        for name, token in reversed(self.tokens):
            if name == 'correlation_id':
                correlation_id_ctx.reset(token)
            elif name == 'user_id':
                user_id_ctx.reset(token)
            elif name == 'operation':
                operation_ctx.reset(token)

def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance"""
    if name is None:
        # Get caller's module name
        frame = sys._getframe(1)
        name = frame.f_globals.get('__name__', 'unknown')
    
    return logger_manager.get_logger(name)

def setup_logging(level: str = "INFO", 
                 structured: bool = True,
                 file_path: Optional[str] = None):
    """Setup application logging"""
    logger_manager.setup_logging(
        level=level,
        structured=structured,
        file_path=file_path
    )

# Convenience functions for common logging patterns
def log_function_call(logger: logging.Logger, function_name: str, **kwargs):
    """Log function entry with parameters"""
    logger.debug(f"Entering {function_name}", extra={
        'event_type': 'function_entry',
        'function': function_name,
        'parameters': kwargs
    })

def log_function_result(logger: logging.Logger, function_name: str, success: bool, **kwargs):
    """Log function exit with result"""
    level = logging.DEBUG if success else logging.WARNING
    logger.log(level, f"Exiting {function_name} - {'success' if success else 'failure'}", extra={
        'event_type': 'function_exit',
        'function': function_name,
        'success': success,
        **kwargs
    })

def log_error(logger: logging.Logger, error: Exception, operation: str = '', **context):
    """Log error with full context"""
    logger.error(f"Error in {operation}: {str(error)}", extra={
        'event_type': 'error',
        'operation': operation,
        'error_type': error.__class__.__name__,
        'error_message': str(error),
        **context
    }, exc_info=True)

def log_business_event(logger: logging.Logger, event: str, **context):
    """Log business events for analytics"""
    logger.info(f"Business event: {event}", extra={
        'event_type': 'business_event',
        'event': event,
        **context
    })

def log_performance(logger: logging.Logger, operation: str, duration_ms: float, **context):
    """Log performance metrics"""
    logger.info(f"Performance: {operation} took {duration_ms:.2f}ms", extra={
        'event_type': 'performance',
        'operation': operation,
        'duration_ms': duration_ms,
        **context
    })