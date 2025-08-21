import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não definido")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS clients ("
                "id SERIAL PRIMARY KEY,"
                "name TEXT NOT NULL,"
                "phone TEXT,"
                "email TEXT,"
                "package TEXT,"
                "value NUMERIC(10,2),"
                "due_date DATE,"
                "info TEXT,"
                "created_at TIMESTAMP DEFAULT NOW()"
                ");")
    cur.execute("CREATE TABLE IF NOT EXISTS templates ("
                "key TEXT PRIMARY KEY,"
                "title TEXT NOT NULL,"
                "body TEXT NOT NULL"
                ");")
    # seeds (UPSERT)
    seeds = [
        ("D2", "2 dias antes", "Oi {nome}! Seu plano {pacote} vence em {dias_para_vencer} dias (venc.: {vencimento}). Valor: {valor}."),
        ("D1", "1 dia antes", "Olá {nome}! Seu plano vence amanhã ({vencimento}). Valor: {valor}."),
        ("D0", "Dia do vencimento", "Olá {nome}! Hoje é o vencimento ({vencimento}). Valor: {valor}."),
        ("DA1", "1 dia após", "Olá {nome}, identificamos atraso de {dias_atraso} dia. Venc.: {vencimento}. Valor: {valor}."),
        ("RENOV", "Renovação", "Olá {nome}, renovamos seu {pacote}. Próx. vencimento: {vencimento}. Obrigado!"),
        ("OUTRO", "Outro", "Olá {nome}! Mensagem padrão sobre seu plano {pacote}.")
    ]
    for k, t, b in seeds:
        cur.execute("INSERT INTO templates(key, title, body) VALUES (%s,%s,%s) "
                    "ON CONFLICT (key) DO UPDATE SET title=EXCLUDED.title, body=EXCLUDED.body;",
                    (k, t, b))
    conn.commit()
    cur.close()
    conn.close()

# --------- Clients ---------
def add_client(name, phone=None, email=None, package=None, value=None, due_date=None, info=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO clients(name, phone, email, package, value, due_date, info) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id;",
                (name, phone, email, package, value, due_date, info))
    cid = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return cid

def list_clients(limit=20, offset=0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients ORDER BY due_date ASC NULLS LAST, id ASC LIMIT %s OFFSET %s;", (limit, offset))
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS c FROM clients;")
    total = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return rows, total

def list_due_or_overdue(days=3, limit=100, offset=0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients "
                "WHERE due_date IS NOT NULL AND due_date <= CURRENT_DATE + INTERVAL '%s day' "
                "ORDER BY due_date ASC, id ASC LIMIT %s OFFSET %s;", (days, limit, offset))
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS c FROM clients WHERE due_date IS NOT NULL AND due_date <= CURRENT_DATE + INTERVAL '%s day';", (days,))
    total = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return rows, total

def get_client(cid: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients WHERE id=%s;", (cid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def update_client(cid: int, **fields):
    if not fields:
        return
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k}=%s")
        vals.append(v)
    vals.append(cid)
    sql = "UPDATE clients SET " + ", ".join(sets) + " WHERE id=%s;"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, vals)
    conn.commit()
    cur.close()
    conn.close()

def delete_client(cid: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM clients WHERE id=%s;", (cid,))
    conn.commit()
    cur.close()
    conn.close()

# --------- Templates ---------
def list_templates():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM templates ORDER BY key;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_template(key: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM templates WHERE key=%s;", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def update_template(key: str, body: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE templates SET body=%s WHERE key=%s;", (body, key))
    conn.commit()
    cur.close()
    conn.close()
