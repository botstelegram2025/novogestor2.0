# db.py
import os
import psycopg2
import psycopg2.extras
from typing import List, Optional, Dict, Any
from datetime import date, datetime

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Defina DATABASE_URL nas variáveis de ambiente")

def connect():
    # Se precisar SSL forçado: acrescente ?sslmode=require à URL (Railway aceita sem)
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            # Tabela de clientes
            cur.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                telefone TEXT,
                email TEXT,
                pacote TEXT,
                valor NUMERIC(12,2),
                vencimento DATE,
                info TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Garantir colunas para upgrades
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pacote TEXT;")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS valor NUMERIC(12,2);")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS vencimento DATE;")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS info TEXT;")

            # Tabela de usuários (cadastro no 1º acesso)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                tg_id BIGINT UNIQUE NOT NULL,
                nome TEXT,
                email TEXT,
                telefone TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """)
        conn.commit()

# ----------------- CLIENTES -----------------
def inserir_cliente(
    nome: str,
    telefone: Optional[str],
    pacote: Optional[str],
    valor: Optional[float],
    vencimento: Optional[str],
    info: Optional[str],
) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clientes (nome, telefone, pacote, valor, vencimento, info) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (nome, telefone, pacote, valor, vencimento, info),
            )
            new_id = cur.fetchone()[0]
        conn.commit
