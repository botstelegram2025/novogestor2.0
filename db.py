# db.py
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, date

logger = logging.getLogger("db")

DB_PATH = "bot_gestor.db"
DATE_FMT = "%Y-%m-%d"   # ISO (armazenamento)
HUMAN_FMT = "%d/%m/%Y"  # Exibição

def _apply_pragmas(con: sqlite3.Connection):
    cur = con.cursor()
    # Segurança e performance
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.close()

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    _apply_pragmas(con)
    try:
        yield con
        con.commit()
    except Exception as e:
        con.rollback()
        logger.exception("DB error, rollback applied: %s", e)
        raise
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
        # Índices úteis
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_due ON clients(due_date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);")

        # Tabela de templates (um por offset, por enquanto)
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
                cur.execute(
                    "INSERT OR IGNORE INTO templates (label, offset_days, content) VALUES (?, ?, ?)",
                    (label, off, content)
                )
            except sqlite3.IntegrityError:
                pass
        logger.info("DB init ok (clients/templates).")

def add_client(name, phone, package, price, info, due_date_iso):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO clients (name, phone, package, price, info, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, phone, package, price, info, due_date_iso, now, now))
        cid = cur.lastrowid
        logger.info("add_client | id=%s name=%r due=%s", cid, name, due_date_iso)
        return cid

def get_clients():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM clients ORDER BY name ASC;")
        rows = [dict(r) for r in cur.fetchall()]
        logger.debug("get_clients | count=%d", len(rows))
        return rows

def get_client(client_id):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM clients WHERE id = ?;", (client_id,))
        r = cur.fetchone()
        logger.debug("get_client | id=%s found=%s", client_id, bool(r))
        return dict(r) if r else None

def update_client_field(client_id, field, value):
    if field not in {"name", "phone", "package", "price", "info", "due_date"}:
        raise ValueError("Campo inválido.")
    # Validação leve
    if field == "price":
        try:
            value = float(value)
        except Exception:
            raise ValueError("Preço inválido.")
    if field == "due_date":
        # Confirma formato ISO
        try:
            datetime.strptime(str(value), DATE_FMT)
        except Exception:
            raise ValueError(f"Data de vencimento deve estar em ISO {DATE_FMT}.")

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        cur = con.cursor()
        cur.execute(f"UPDATE clients SET {field} = ?, updated_at = ? WHERE id = ?;", (value, now, client_id))
        ok = cur.rowcount > 0
        logger.info("update_client_field | id=%s field=%s ok=%s", client_id, field, ok)
        return ok

def delete_client(client_id):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM clients WHERE id = ?;", (client_id,))
        ok = cur.rowcount > 0
        logger.info("delete_client | id=%s ok=%s", client_id, ok)
        return ok

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
    logger.info("renew_client | id=%s base=%s new_due=%s ok=%s", client_id, base, new_due, ok)
    return ok, new_due

def list_templates():
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM templates ORDER BY offset_days ASC;")
        rows = [dict(r) for r in cur.fetchall()]
        logger.debug("list_templates | count=%d", len(rows))
        return rows

def get_template_by_offset(offset_days):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM templates WHERE offset_days = ?;", (offset_days,))
        r = cur.fetchone()
        logger.debug("get_template_by_offset | off=%s found=%s", offset_days, bool(r))
        return dict(r) if r else None

def set_template(offset_days, label, content):
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO templates (label, offset_days, content)
            VALUES (?, ?, ?)
            ON CONFLICT(offset_days) DO UPDATE SET label=excluded.label, content=excluded.content
        """, (label, offset_days, content))
        logger.info("set_template | off=%s label=%r (upsert)", offset_days, label)
    return True

# ---------- Helpers ----------

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

def get_status(iso_str):
    """Retorna 'overdue'|'soon'|'ok' para uso em filtros futuros."""
    days = days_until_due(iso_str)
    if days is None:
        return "unknown"
    if days < 0:
        return "overdue"
    if days <= 3:
        return "soon"
    return "ok"

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
    except Exception as e:
        logger.warning("render_template fallback (placeholders) | err=%s | content=%r", e, content)
        return content

# ---------- (Opcional) Migração para permitir múltiplos templates por offset ----------
def migrate_templates_allow_duplicates():
    """
    Remove a restrição UNIQUE(offset_days) recriando a tabela.
    NÃO é chamada automaticamente. Execute manualmente se quiser permitir vários
    templates com o mesmo offset.

    Atenção: mantém os dados existentes.
    """
    with _conn() as con:
        cur = con.cursor()
        logger.info("Migrando tabela templates para permitir duplicados de offset_days...")
        # 1) Renomeia tabela antiga
        cur.execute("ALTER TABLE templates RENAME TO templates_old;")
        # 2) Cria nova tabela sem UNIQUE
        cur.execute("""
        CREATE TABLE templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            offset_days INTEGER,
            content TEXT NOT NULL
        );
        """)
        # 3) Copia dados
        cur.execute("""
        INSERT INTO templates (label, offset_days, content)
        SELECT label, offset_days, content FROM templates_old;
        """)
        # 4) Drop tabela antiga
        cur.execute("DROP TABLE templates_old;")
        logger.info("Migração concluída.")
