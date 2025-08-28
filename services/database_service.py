from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import logging
from config import Config
from models import Base, User, Client, Subscription, MessageTemplate, MessageLog, SystemSettings

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        self.engine = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False
        )
        self.SessionLocal = scoped_session(sessionmaker(bind=self.engine))
        self.create_tables()
    
    def create_tables(self):
        """Create all database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def create_default_templates(self, user_id):
        """Create default message templates for a specific user"""
        default_templates = [
            {
                'name': '📅 Lembrete 2 dias antes',
                'template_type': 'reminder_2days',
                'subject': 'Lembrete: Vencimento em 2 dias',
                'content': '📅 LEMBRETE: 2 DIAS PARA VENCER\n\nOlá {nome}! \n\n📺 Seu plano "{plano}" vencerá em 2 dias.\n📅 Data de vencimento: {vencimento}\n💰 Valor: R$ {valor}\n\nPara renovar, entre em contato conosco.\n\nObrigado! 😊'
            },
            {
                'name': '⏰ Lembrete 1 dia antes',
                'template_type': 'reminder_1day',
                'subject': 'Lembrete: Vencimento amanhã',
                'content': '⏰ ÚLTIMO AVISO: VENCE AMANHÃ!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" vence AMANHÃ ({vencimento}).\n💰 Valor: R$ {valor}\n\nNão esqueça de renovar para continuar aproveitando nossos serviços!\n\nRenove agora! 🚀'
            },
            {
                'name': '🚨 Vencimento hoje',
                'template_type': 'reminder_due',
                'subject': 'Vencimento hoje',
                'content': '🚨 ATENÇÃO: VENCE HOJE!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" vence HOJE ({vencimento}).\n💰 Valor: R$ {valor}\n\nRenove agora para não perder o acesso aos nossos serviços.\n\nContate-nos para renovar! 💬'
            },
            {
                'name': '❌ Em atraso',
                'template_type': 'reminder_overdue',
                'subject': 'Plano vencido',
                'content': '❌ PLANO VENCIDO - AÇÃO NECESSÁRIA!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" venceu em {vencimento}.\n💰 Valor: R$ {valor}\n\n⚠️ Renove o quanto antes para reativar seus serviços.\n\nEstamos aqui para ajudar! 🤝'
            },
            {
                'name': '🎉 Boas-vindas',
                'template_type': 'welcome',
                'subject': 'Bem-vindo!',
                'content': '🎉 SEJA BEM-VINDO(A)!\n\nOlá {nome}!\n\n🌟 Seja muito bem-vindo(a) à nossa família!\n\n📺 Seu plano "{plano}" está ativo e vence em {vencimento}.\n💰 Valor: R$ {valor}\n\nEstamos muito felizes em tê-lo(a) conosco! \n\nAproveite nossos serviços! 🚀'
            },
            {
                'name': '✅ Renovação confirmada',
                'template_type': 'renewal',
                'subject': 'Plano renovado com sucesso!',
                'content': '✅ RENOVAÇÃO CONFIRMADA COM SUCESSO!\n\nOlá {nome}!\n\n🎊 Seu plano "{plano}" foi renovado com sucesso!\n\n📅 Novo vencimento: {vencimento}\n💰 Valor: R$ {valor}\n\nObrigado pela confiança! Continue aproveitando nossos serviços. 🌟'
            }
        ]
        
        with self.get_session() as session:
            for template_data in default_templates:
                existing = session.query(MessageTemplate).filter_by(
                    template_type=template_data['template_type'],
                    user_id=user_id
                ).first()
                
                if not existing:
                    template_data['user_id'] = user_id
                    template_data['is_default'] = True  # Mark as default template
                    template = MessageTemplate(**template_data)
                    session.add(template)
                    logger.info(f"Created default template for user {user_id}: {template_data['name']}")
    
    def restore_default_templates(self, user_id):
        """Restore all default templates to original state"""
        default_templates = [
            {
                'name': '📅 Lembrete 2 dias antes',
                'template_type': 'reminder_2days',
                'subject': 'Lembrete: Vencimento em 2 dias',
                'content': '📅 LEMBRETE: 2 DIAS PARA VENCER\n\nOlá {nome}! \n\n📺 Seu plano "{plano}" vencerá em 2 dias.\n📅 Data de vencimento: {vencimento}\n💰 Valor: R$ {valor}\n\nPara renovar, entre em contato conosco.\n\nObrigado! 😊'
            },
            {
                'name': '⏰ Lembrete 1 dia antes',
                'template_type': 'reminder_1day',
                'subject': 'Lembrete: Vencimento amanhã',
                'content': '⏰ ÚLTIMO AVISO: VENCE AMANHÃ!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" vence AMANHÃ ({vencimento}).\n💰 Valor: R$ {valor}\n\nNão esqueça de renovar para continuar aproveitando nossos serviços!\n\nRenove agora! 🚀'
            },
            {
                'name': '🚨 Vencimento hoje',
                'template_type': 'reminder_due',
                'subject': 'Vencimento hoje',
                'content': '🚨 ATENÇÃO: VENCE HOJE!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" vence HOJE ({vencimento}).\n💰 Valor: R$ {valor}\n\nRenove agora para não perder o acesso aos nossos serviços.\n\nContate-nos para renovar! 💬'
            },
            {
                'name': '❌ Em atraso',
                'template_type': 'reminder_overdue',
                'subject': 'Plano vencido',
                'content': '❌ PLANO VENCIDO - AÇÃO NECESSÁRIA!\n\nOlá {nome}!\n\n📺 Seu plano "{plano}" venceu em {vencimento}.\n💰 Valor: R$ {valor}\n\n⚠️ Renove o quanto antes para reativar seus serviços.\n\nEstamos aqui para ajudar! 🤝'
            },
            {
                'name': '🎉 Boas-vindas',
                'template_type': 'welcome',
                'subject': 'Bem-vindo!',
                'content': '🎉 SEJA BEM-VINDO(A)!\n\nOlá {nome}!\n\n🌟 Seja muito bem-vindo(a) à nossa família!\n\n📺 Seu plano "{plano}" está ativo e vence em {vencimento}.\n💰 Valor: R$ {valor}\n\nEstamos muito felizes em tê-lo(a) conosco! \n\nAproveite nossos serviços! 🚀'
            },
            {
                'name': '✅ Renovação confirmada',
                'template_type': 'renewal',
                'subject': 'Plano renovado com sucesso!',
                'content': '✅ RENOVAÇÃO CONFIRMADA COM SUCESSO!\n\nOlá {nome}!\n\n🎊 Seu plano "{plano}" foi renovado com sucesso!\n\n📅 Novo vencimento: {vencimento}\n💰 Valor: R$ {valor}\n\nObrigado pela confiança! Continue aproveitando nossos serviços. 🌟'
            }
        ]
        
        with self.get_session() as session:
            # Update existing default templates
            for template_data in default_templates:
                existing = session.query(MessageTemplate).filter_by(
                    template_type=template_data['template_type'],
                    user_id=user_id,
                    is_default=True
                ).first()
                
                if existing:
                    # Update existing default template
                    existing.name = template_data['name']
                    existing.subject = template_data['subject']
                    existing.content = template_data['content']
                    existing.is_active = True
                    logger.info(f"Restored default template for user {user_id}: {template_data['name']}")
                else:
                    # Create new default template if missing
                    template_data['user_id'] = user_id
                    template_data['is_default'] = True
                    template = MessageTemplate(**template_data)
                    session.add(template)
                    logger.info(f"Created missing default template for user {user_id}: {template_data['name']}")

# Global database service instance
db_service = DatabaseService()
