from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone_number = Column(String(20))
    email = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    trial_start_date = Column(DateTime, default=datetime.utcnow)
    trial_end_date = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=7))
    is_active = Column(Boolean, default=True)
    is_trial = Column(Boolean, default=True)
    last_payment_date = Column(DateTime)
    next_due_date = Column(DateTime)
    
    # Relationships
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    message_logs = relationship("MessageLog", back_populates="user", cascade="all, delete-orphan")
    message_templates = relationship("MessageTemplate", back_populates="user", cascade="all, delete-orphan")

class Client(Base):
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(100))
    plan_name = Column(String(100))
    plan_price = Column(Float)
    due_date = Column(Date, nullable=False)
    server = Column(String(100))  # Server information
    other_info = Column(Text)  # MAC, chave, OTP, etc
    status = Column(String(20), default='active')  # active, inactive, suspended
    auto_reminders_enabled = Column(Boolean, default=True)  # Individual client reminder control
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="clients")
    message_logs = relationship("MessageLog", back_populates="client", cascade="all, delete-orphan")

class Subscription(Base):
    __tablename__ = 'subscriptions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    payment_id = Column(String(100))  # Mercado Pago payment ID
    amount = Column(Float, nullable=False)
    status = Column(String(20), default='pending')  # pending, approved, rejected, cancelled
    payment_method = Column(String(50), default='pix')
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    expires_at = Column(DateTime)
    pix_qr_code = Column(Text)
    pix_qr_code_base64 = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")

class MessageTemplate(Base):
    __tablename__ = 'message_templates'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)
    template_type = Column(String(50), nullable=False)  # reminder_2days, reminder_1day, reminder_due, reminder_overdue, welcome, renewal
    subject = Column(String(200))
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Protect default templates from editing
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="message_templates")

class MessageLog(Base):
    __tablename__ = 'message_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id'))
    template_type = Column(String(50), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    message_content = Column(Text, nullable=False)
    status = Column(String(20), default='pending')  # pending, sent, failed
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="message_logs")
    client = relationship("Client", back_populates="message_logs")

class SystemSettings(Base):
    __tablename__ = 'system_settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserScheduleSettings(Base):
    __tablename__ = 'user_schedule_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    morning_reminder_time = Column(String(5), default='09:00')  # Format: HH:MM
    daily_report_time = Column(String(5), default='08:00')     # Format: HH:MM
    auto_send_enabled = Column(Boolean, default=True)          # Enable/disable automated sending
    is_active = Column(Boolean, default=True)
    last_morning_run = Column(Date)  # Track last execution dates
    last_report_run = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="schedule_settings")
