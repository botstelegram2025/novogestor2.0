# db.py
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, date

DB_PATH = "bot_gestor.db"
DATE_FMT = "%Y-%m-%d"  # ISO (armazenamento)
HUMAN_FMT = "%d/%m/%Y"  # Exibição

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with _conn() as con:
        cur = con.cursor()
        # Tabela de clientes
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            package TEXT,
            price REAL,
            info TEXT,
            due_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        # Tabela de templates
        cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            offset_days INTEGER,
            content TEXT NOT NULL,
            UNIQUE(offset_days)
        );
        """)
        # Pré-popular templates padrão (se não existirem)
        defaults = [
            ("2 dias antes", -2, "Olá {nome}! Passando para lembrar que seu pagamento vence em {dias} dias, em {vencimento}. Qualquer dúvida, estou por aqui."),
            ("1 dia antes", -1, "Oi {nome}, tudo bem? Amanhã ({vencimento}) vence sua assinatura do pacote {pacote} no valor de R$ {valor:.2f}."),
            ("No dia", 0, "Olá {nome}! Hoje é o vencimento ({vencimento}) da sua mensalidade do pacote {pacote}. Conto com você 😉"),
            ("1 dia depois", 1, "Oi {nome}, vi aqui que o vencimento foi ontem ({vencimento}). Precisa de algo? Posso te mandar o link de pagamento."),
            ("Renovação", 30, "Oi {nome}! Obrigado por renovar o pacote {pacote}. Atualizamos seu vencimento para {vencimento}.")
        ]
        for label, off, content in defaults:
            try:
                cur.execute("INSERT OR IGNORE INTO templates (label, offset_days, content) VALUES (?, ?, ?)", (label, off, content))
            except sqlite3.IntegrityError:
                pass

def add_client(name, phone, package, price, info, due_date_iso):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO clients (name, phone, package, price, info, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, phone, package, price, info, due_date_iso, now, now))
        return cur.lastrowid

def get_clients():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM clients ORDER BY name ASC;")
        return [dict(r) for r in cur.fetchall()]

def get_client(client_id):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM clients WHERE id = ?;", (client_id,))
        r = cur.fetchone()
        return dict(r) if r else None

def update_client_field(client_id, field, value):
    if field not in {"name", "phone", "package", "price", "info", "due_date"}:
        raise ValueError("Campo inválido.")
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        cur = con.cursor()
        cur.execute(f"UPDATE clients SET {field} = ?, updated_at = ? WHERE id = ?;", (value, now, client_id))
        return cur.rowcount > 0

def delete_client(client_id):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM clients WHERE id = ?;", (client_id,))
        return cur.rowcount > 0

def renew_client(client_id, cycle_days=30):
    c = get_client(client_id)
    if not c:
        return False
    # Se vencido, renova a partir de hoje; se ainda vigente, soma ao vencimento atual
    try:
        current_due = datetime.strptime(c["due_date"], DATE_FMT).date()
    except Exception:
        current_due = date.today()
    base = date.today() if current_due < date.today() else current_due
    new_due = base + timedelta(days=cycle_days)
    ok = update_client_field(client_id, "due_date", new_due.strftime(DATE_FMT))
    return ok, new_due

def list_templates():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM templates ORDER BY offset_days ASC;")
        return [dict(r) for r in cur.fetchall()]

def get_template_by_offset(offset_days):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM templates WHERE offset_days = ?;", (offset_days,))
        r = cur.fetchone()
        return dict(r) if r else None

def set_template(offset_days, label, content):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO templates (label, offset_days, content)
            VALUES (?, ?, ?)
            ON CONFLICT(offset_days) DO UPDATE SET label=excluded.label, content=excluded.content
        """, (label, offset_days, content))
    return True

# Helpers

def iso_to_human(iso_str):
    try:
        d = datetime.strptime(iso_str, DATE_FMT).date()
        return d.strftime(HUMAN_FMT)
    except Exception:
        return iso_str

def human_to_iso(human_str):
    d = datetime.strptime(human_str.strip(), HUMAN_FMT).date()
    return d.strftime(DATE_FMT)

def days_until_due(iso_str):
    try:
        d = datetime.strptime(iso_str, DATE_FMT).date()
    except Exception:
        return None
    return (d - date.today()).days

def status_emoji(iso_str):
    days = days_until_due(iso_str)
    if days is None:
        return "⚪"
    if days < 0:
        return "🔴"
    if days <= 3:
        return "🟡"
    return "🟢"

def render_template(content, client_row, ref_days=None):
    di = days_until_due(client_row["due_date"])
    ctx = {
        "nome": client_row.get("name") or "",
        "telefone": client_row.get("phone") or "",
        "pacote": client_row.get("package") or "",
        "valor": float(client_row.get("price") or 0.0),
        "info": client_row.get("info") or "",
        "vencimento": iso_to_human(client_row.get("due_date") or ""),
        "dias": ref_days if ref_days is not None else (di if di is not None else "")
    }
    try:
        return content.format(**ctx)
    except Exception:
        return content
