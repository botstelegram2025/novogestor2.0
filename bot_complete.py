# db.py
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

DB_URL = os.getenv("DATABASE_URL")

@contextmanager
def get_conn():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL não definido")
    conn = psycopg2.connect(DB_URL)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        # Tabela de usuários do bot
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            tg_id BIGINT PRIMARY KEY,
            nome TEXT,
            email TEXT,
            telefone TEXT
        );
        """)
        # Tabela de clientes
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            pacote TEXT,
            valor NUMERIC(12,2),
            vencimento DATE,
            info TEXT
        );
        """)
        # Tabela de templates
        cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        );
        """)
        # Popular templates padrão se não existirem
        cur.execute("SELECT COUNT(*) FROM templates;")
        if cur.fetchone()[0] == 0:
            cur.executemany("""
            INSERT INTO templates (key, title, body) VALUES (%s,%s,%s)
            """, [
                ("D2",   "Cobrança • 2 dias antes", "Olá {nome}, lembrando que seu {pacote} vence em {dias_para_vencer} dias (venc.: {vencimento}). Valor: {valor}."),
                ("D1",   "Cobrança • 1 dia antes",  "Olá {nome}, seu {pacote} vence amanhã ({vencimento}). Valor: {valor}."),
                ("D0",   "Cobrança • hoje",         "Olá {nome}, vencimento do {pacote} é hoje ({vencimento}). Valor: {valor}."),
                ("DA1",  "Cobrança • 1 dia após",   "Olá {nome}, identificamos atraso de {dias_atraso} dia no {pacote} (venc.: {vencimento}). Valor: {valor}."),
                ("RENOV","Renovação de plano",       "Olá {nome}, renovamos seu {pacote}. Novo vencimento: {vencimento}."),
                ("OUTRO","Mensagem genérica",         "Olá {nome}, tudo bem? Este é um lembrete referente ao seu {pacote} (venc.: {vencimento}). Valor: {valor}.")
            ])
        # Tabela de configurações (settings)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        # Valores padrão do agendador
        cur.execute("INSERT INTO settings (key, value) VALUES ('scheduler_enabled','1') ON CONFLICT (key) DO NOTHING;")
        cur.execute("INSERT INTO settings (key, value) VALUES ('schedule_times','09:00,18:00') ON CONFLICT (key) DO NOTHING;")
        # Tabela de logs de WhatsApp
        cur.execute("""
        CREATE TABLE IF NOT EXISTS wa_logs (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            client_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            phone TEXT,
            ok BOOLEAN,
            info TEXT,
            message TEXT
        );
        """)
        conn.commit()

# ---------- Usuários ----------
def inserir_usuario(tg_id: int, nome: str, email: str, telefone: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO usuarios (tg_id, nome, email, telefone)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (tg_id) DO UPDATE SET nome=EXCLUDED.nome, email=EXCLUDED.email, telefone=EXCLUDED.telefone;
        """, (tg_id, nome, email, telefone))
        conn.commit()

def buscar_usuario(tg_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE tg_id=%s", (tg_id,))
        return cur.fetchone()

# ---------- Clientes ----------
def inserir_cliente(nome: str, telefone: Optional[str], pacote: Optional[str], valor: Optional[float], vencimento: Optional[str], info: Optional[str]) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO clientes (nome, telefone, pacote, valor, vencimento, info)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id;
        """, (nome, telefone, pacote, valor, vencimento, info))
        cid = cur.fetchone()[0]
        conn.commit()
        return cid

def listar_clientes(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
        SELECT * FROM clientes
        ORDER BY vencimento NULLS LAST, id ASC
        LIMIT %s OFFSET %s;
        """, (limit, offset))
        return cur.fetchall()

def contar_clientes() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes;")
        return cur.fetchone()[0]

def buscar_cliente_por_id(cid: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM clientes WHERE id=%s;", (cid,))
        return cur.fetchone()

def atualizar_cliente(cid: int, **fields):
    if not fields:
        return
    cols = []
    vals = []
    for k, v in fields.items():
        cols.append(f"{k}=%s")
        vals.append(v)
    vals.append(cid)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE clientes SET {', '.join(cols)} WHERE id=%s;", vals)
        conn.commit()

def deletar_cliente(cid: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM clientes WHERE id=%s;", (cid,))
        conn.commit()

def renovar_vencimento(cid: int, months: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE clientes SET vencimento = COALESCE(vencimento, CURRENT_DATE) + (%s || ' months')::interval WHERE id=%s RETURNING vencimento;", (months, cid))
        new_date = cur.fetchone()[0]
        conn.commit()
        return new_date

# ---------- Templates ----------
def list_templates() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM templates ORDER BY title asc;")
        return cur.fetchall()

def get_template(key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM templates WHERE key=%s;", (key,))
        return cur.fetchone()

def update_template(key: str, body: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO templates (key, title, body)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET body=EXCLUDED.body;
        """, (key, key, body))
        conn.commit()

def reset_template(key: str) -> bool:
    defaults = {
        "D2":   "Olá {nome}, lembrando que seu {pacote} vence em {dias_para_vencer} dias (venc.: {vencimento}). Valor: {valor}.",
        "D1":   "Olá {nome}, seu {pacote} vence amanhã ({vencimento}). Valor: {valor}.",
        "D0":   "Olá {nome}, vencimento do {pacote} é hoje ({vencimento}). Valor: {valor}.",
        "DA1":  "Olá {nome}, identificamos atraso de {dias_atraso} dia no {pacote} (venc.: {vencimento}). Valor: {valor}.",
        "RENOV":"Olá {nome}, renovamos seu {pacote}. Novo vencimento: {vencimento}.",
        "OUTRO":"Olá {nome}, tudo bem? Este é um lembrete referente ao seu {pacote} (venc.: {vencimento}). Valor: {valor}."
    }
    if key not in defaults:
        return False
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        UPDATE templates SET body=%s, title=%s WHERE key=%s;
        """, (defaults[key], key, key))
        conn.commit()
        return True

# ---------- Settings ----------
def get_setting(key: str, default: str | None = None) -> Optional[str]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=%s;", (key,))
        row = cur.fetchone()
        return row[0] if row else default

def set_setting(key: str, value: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO settings (key, value) VALUES (%s,%s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
        """, (key, value))
        conn.commit()

# ---------- WA Logs ----------
def add_wa_log(client_id: Optional[int], phone: Optional[str], message: str, ok: bool, info: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO wa_logs (client_id, phone, message, ok, info) VALUES (%s,%s,%s,%s,%s);
        """, (client_id, phone, message, ok, info))
        conn.commit()

def list_wa_logs(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
        SELECT l.*, c.nome AS cliente_nome
        FROM wa_logs l
        LEFT JOIN clientes c ON c.id = l.client_id
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT %s OFFSET %s;
        """, (limit, offset))
        return cur.fetchall()

def count_wa_logs() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM wa_logs;")
        return cur.fetchone()[0]
