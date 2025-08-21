import os
from typing import Optional, Dict, Any, List
from datetime import date, datetime
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

DEFAULT_TEMPLATES = {
    "D2":   ("2 dias antes",          "Oi {nome}! Seu plano {pacote} vence em {dias_para_vencer} dias (venc.: {vencimento}). Valor: {valor}."),
    "D1":   ("1 dia antes",            "Olá {nome}! Seu plano vence amanhã ({vencimento}). Valor: {valor}."),
    "D0":   ("Dia do vencimento",      "Olá {nome}! Hoje é o vencimento ({vencimento}). Valor: {valor}."),
    "DA1":  ("1 dia após",             "Olá {nome}, identificamos atraso de {dias_atraso} dia(s). Venc.: {vencimento}. Valor: {valor}."),
    "RENOV":("Renovação",              "Olá {nome}, renovamos seu {pacote}. Próx. vencimento: {vencimento}. Obrigado!"),
    "OUTRO":("Outro",                  "Olá {nome}! Mensagem padrão sobre seu plano {pacote}."),
}

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("Defina DATABASE_URL no ambiente (Postgres).")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Usuários
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            tg_id BIGINT PRIMARY KEY,
            nome TEXT,
            email TEXT,
            telefone TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Clientes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            pacote TEXT,
            valor NUMERIC(10,2),
            vencimento DATE,
            info TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Templates
    cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        );
    """)
    # Seed templates
    for k, (title, body) in DEFAULT_TEMPLATES.items():
        cur.execute("""
            INSERT INTO templates (key, title, body)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET title = EXCLUDED.title, body = EXCLUDED.body;
        """, (k, title, body))
    conn.commit()
    cur.close(); conn.close()

# -------- Usuários --------
def buscar_usuario(tg_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE tg_id = %s;", (tg_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def inserir_usuario(tg_id: int, nome: str, email: str, telefone: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO usuarios (tg_id, nome, email, telefone)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (tg_id) DO UPDATE SET nome=EXCLUDED.nome, email=EXCLUDED.email, telefone=EXCLUDED.telefone;
    """, (tg_id, nome, email, telefone))
    conn.commit()
    cur.close(); conn.close()

# -------- Clientes --------
def inserir_cliente(nome: str, telefone: Optional[str], pacote: Optional[str],
                    valor: Optional[float], vencimento: Optional[str], info: Optional[str]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clientes (nome, telefone, pacote, valor, vencimento, info)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
    """, (nome, telefone, pacote, valor, vencimento, info))
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return new_id

def listar_clientes(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM clientes
        ORDER BY vencimento ASC NULLS LAST, id ASC
        LIMIT %s OFFSET %s;
    """, (limit, offset))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def contar_clientes() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM clientes;")
    c = int(cur.fetchone()["c"])
    cur.close(); conn.close()
    return c

def listar_clientes_due(days: int = 3, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM clientes
        WHERE vencimento IS NOT NULL AND vencimento <= CURRENT_DATE + INTERVAL '%s day'
        ORDER BY vencimento ASC, id ASC
        LIMIT %s OFFSET %s;
    """, (days, limit, offset))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def buscar_cliente_por_id(cid: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE id = %s;", (cid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def deletar_cliente(cid: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE id = %s;", (cid,))
    conn.commit()
    cur.close(); conn.close()

def atualizar_cliente(cid: int, **fields):
    if not fields:
        return
    keys = []
    vals = []
    for k, v in fields.items():
        keys.append(f"{k} = %s")
        vals.append(v)
    vals.append(cid)
    sql = "UPDATE clientes SET " + ", ".join(keys) + " WHERE id = %s;"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, vals)
    conn.commit()
    cur.close(); conn.close()

def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    from calendar import monthrange
    last = monthrange(y, m)[1]
    return date(y, m, min(d.day, last))

def renovar_vencimento(cid: int, months: int) -> date:
    c = buscar_cliente_por_id(cid)
    if not c or not c.get("vencimento"):
        base = date.today()
    else:
        base = c["vencimento"] if isinstance(c["vencimento"], date) else datetime.fromisoformat(str(c["vencimento"])).date()
    new_date = _add_months(base, months)
    atualizar_cliente(cid, vencimento=new_date.isoformat())
    return new_date

# -------- Templates --------
def list_templates() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, title, body FROM templates ORDER BY key;")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def get_template(key: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, title, body FROM templates WHERE key = %s;", (key,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def update_template(key: str, body: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE templates SET body = %s WHERE key = %s;", (body, key))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok

def reset_template(key: str) -> bool:
    if key not in DEFAULT_TEMPLATES:
        return False
    title, body = DEFAULT_TEMPLATES[key]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO templates (key, title, body)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET title=EXCLUDED.title, body=EXCLUDED.body;
    """, (key, title, body))
    conn.commit()
    cur.close(); conn.close()
    return True
