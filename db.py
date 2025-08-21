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

def atualizar_cliente(cid: int, **fields) -> bool:
    """Atualiza campos do cliente. Campos: nome, telefone, pacote, valor, vencimento, info, email."""
    allowed = {"nome", "telefone", "pacote", "valor", "vencimento", "info", "email"}
    set_parts, values = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "vencimento" and isinstance(v, str):
            try:
                v = datetime.fromisoformat(v).date()
            except ValueError:
                pass
        set_parts.append(f"{k}=%s")
        values.append(v)
    if not set_parts:
        return False
    values.append(cid)
    query = "UPDATE clientes SET " + ", ".join(set_parts) + " WHERE id=%s;"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
        conn.commit()
    return True

def renovar_vencimento(cid: int, months: int) -> Optional[date]:
    """Soma 'months' ao vencimento atual (ou hoje se vazio) e retorna a nova data."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT vencimento FROM clientes WHERE id=%s;", (cid,))
            row = cur.fetchone()
            if not row:
                return None
            base = row["vencimento"] or date.today()
            new_date = _add_months(base, months)
            cur.execute("UPDATE clientes SET vencimento=%s WHERE id=%s;", (new_date, cid))
        conn.commit()
        return new_date

def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = [31, 29 if (y%4==0 and (y%100!=0 or y%400==0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m-1]
    day = min(d.day, last_day)
    return date(y, m, day)

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
