import os
import psycopg2
import psycopg2.extras
from typing import List, Optional, Dict, Any

DATABASE_URL = os.getenv("DATABASE_URL")

def connect():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

def inserir_cliente(nome: str, telefone: Optional[str], email: Optional[str]) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes (nome, telefone, email) VALUES (%s, %s, %s) RETURNING id;",
            (nome, telefone, email),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id

def listar_clientes(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    with connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, nome, telefone, email, created_at FROM clientes ORDER BY id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

def contar_clientes() -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes;")
        return cur.fetchone()[0]

def buscar_cliente_por_id(cid: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM clientes WHERE id = %s;", (cid,))
        row = cur.fetchone()
        return dict(row) if row else None
