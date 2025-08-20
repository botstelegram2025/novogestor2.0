# db.py
import os
import psycopg2
import psycopg2.extras
from typing import List, Optional, Dict, Any

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Defina DATABASE_URL nas variáveis de ambiente")

def connect():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            # Tabela clientes com novos campos
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
            # Garantir colunas (para quem já tinha tabela antiga)
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pacote TEXT;")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS valor NUMERIC(12,2);")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS vencimento DATE;")
            cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS info TEXT;")

            # Tabela usuarios (cadastro do primeiro acesso)
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
def inserir_cliente(nome: str, telefone: Optional[str], pacote: Optional[str],
                    valor: Optional[float], vencimento: Optional[str], info: Optional[str]) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clientes (nome, telefone, pacote, valor, vencimento, info) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (nome, telefone, pacote, valor, vencimento, info),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id

def listar_clientes(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, nome, telefone, pacote, valor, vencimento, info, created_at "
                "FROM clientes ORDER BY id DESC LIMIT %s OFFSET %s;",
                (limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

def contar_clientes() -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM clientes;")
            return cur.fetchone()[0]

def buscar_cliente_por_id(cid: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM clientes WHERE id = %s;", (cid,))
            row = cur.fetchone()
            return dict(row) if row else None

def deletar_cliente(cid: int) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clientes WHERE id = %s;", (cid,))
        conn.commit()
        return True

# ----------------- USUÁRIOS -----------------
def buscar_usuario(tg_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM usuarios WHERE tg_id = %s;", (tg_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def inserir_usuario(tg_id: int, nome: str, email: str, telefone: str) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (tg_id, nome, email, telefone) "
                "VALUES (%s, %s, %s, %s) RETURNING id;",
                (tg_id, nome, email, telefone),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
