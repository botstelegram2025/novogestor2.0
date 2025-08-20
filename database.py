import os
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:kqUGBfsvXagvnWFOnOjMwBKECmsTaUHF@postgres.railway.internal:5432/railway"
)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    telefone = Column(String, unique=True, index=True)
    pacote = Column(String)
    plano = Column(Float)
    vencimento = Column(Date)
    servidor = Column(String)

Base.metadata.create_all(bind=engine)

class DatabaseManager:
    def __init__(self):
        self.db = SessionLocal()

    def listar_clientes(self, ativo_apenas=True):
        clientes = self.db.query(Cliente).all()
        lista = []
        for c in clientes:
            d = c.__dict__.copy()
            if 'vencimento' in d and d['vencimento']:
                d['vencimento'] = d['vencimento'].strftime("%Y-%m-%d")
            d.pop('_sa_instance_state', None)
            lista.append(d)
        return lista

    def adicionar_cliente(self, nome, telefone, pacote, valor, vencimento, servidor):
        if isinstance(vencimento, str):
            try:
                vencimento = datetime.strptime(vencimento, "%Y-%m-%d").date()
            except Exception as e:
                print(f"Data de vencimento inválida: {e}")
                return False
        try:
            cliente = Cliente(
                nome=nome,
                telefone=telefone,
                pacote=pacote,
                plano=valor,
                vencimento=vencimento,
                servidor=servidor
            )
            self.db.add(cliente)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Erro ao salvar cliente: {e}")
            return False

    def atualizar_cliente(self, cliente_id, campo, valor):
        cliente = self.db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if cliente:
            if campo == "vencimento":
                if isinstance(valor, str):
                    try:
                        valor = datetime.strptime(valor, "%Y-%m-%d").date()
                    except Exception as e:
                        print(f"Data de vencimento inválida: {e}")
                        return False
            setattr(cliente, campo, valor)
            self.db.commit()
            return True
        return False

    def excluir_cliente(self, cliente_id):
        cliente = self.db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if cliente:
            self.db.delete(cliente)
            self.db.commit()
            return True
        return False

    def buscar_cliente_por_telefone(self, telefone):
        cliente = self.db.query(Cliente).filter(Cliente.telefone == telefone).first()
        if cliente:
            d = cliente.__dict__.copy()
            if 'vencimento' in d and d['vencimento']:
                d['vencimento'] = d['vencimento'].strftime("%Y-%m-%d")
            d.pop('_sa_instance_state', None)
            return d
        return None

    def get_configuracoes(self):
        # Adapte conforme sua tabela/configuração real
        return {"empresa_nome": "Minha Empresa", "pix_key": "chavepix", "contato_suporte": "@suporte"}

    def salvar_configuracoes(self, empresa, pix, suporte):
        # Implemente se quiser persistir as configurações
        return True

    def registrar_renovacao(self, cliente_id, dias, valor):
        # Implemente se quiser registrar renovação (crie tabela se necessário)
        return True
