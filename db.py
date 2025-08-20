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
    # Se precisar SSL forçado: acrescente ?sslmode=require à URL (Railway geralmente aceita sem)
    return psycopg2.connect(DATABASE_URL)

# ----------------- Templates (defaults) -----------------
DEFAULT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "D2": {
        "title": "Cobrança • 2 dias antes",
        "body": (
            "Olá {nome}! 👋\n"
            "Lembramos que sua fatura do plano {pacote} no valor de {valor} "
            "vence em {vencimento} (faltam {dias_para_vencer} dias). "
            "Qualquer dúvida, estou à disposição. ✅"
        ),
    },
    "D1": {
        "title": "Cobrança • 1 dia antes",
        "body": (
            "Olá {nome}! 👋\n"
            "A fatura do plano {pacote} (valor {valor}) vence amanhã, dia {vencimento}. "
            "Se precisar, posso te enviar as formas de pagamento. 🙂"
        ),
    },
    "D0": {
        "title": "Cobrança • vence hoje",
        "body": (
            "Olá {nome}! 👋\n"
            "Sua fatura do plano {pacote} (valor {valor}) vence hoje ({vencimento}). "
            "Conte comigo para qualquer suporte. ✅"
        ),
    },
    "DA1": {
        "title": "Cobrança • 1 dia após",
        "body": (
            "Olá {nome}! 👋\n"
            "Notamos que sua fatura do plano {pacote} (valor {valor}) venceu em {vencimento} "
            "({dias_atraso} dia(s) de atraso). Pode me confirmar o pagamento ou preciso te enviar novamente? 🙏"
        ),
    },
    "RENOV": {
        "title": "Renovação de plano",
        "body": (
            "Olá {nome}! 👋\n"
            "Podemos confirmar a renovação do seu plano {pacote} por {valor}? "
            "Vencimento atual: {vencimento}. Responda por aqui e já deixo tudo certo. 🔁"
        ),
    },
    "OUTRO": {
        "title": "Mensagem genérica",
        "body": (
            "Olá {nome}! 👋\n"
            "Segue uma mensagem sobre seu plano {pacote} (valor {valor}, vencimento {vencimento}). "
            "Qualquer dúvida, fico à disposição. 🙂"
        ),
    },
}

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

            # Tabela de templates
            cur.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id SERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Inserir defaults caso não existam
            for k, t in DEFAULT_TEMPLATES.items():
                cur.execute(
                    "INSERT INTO templates (key, title, body) VALUES (%s, %s, %s) "
                    "ON CONFLICT (key) DO NOTHING;",
                    (k, t["title"], t["body"])
                )
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

# ----------------- TEMPLATES -----------------
def list_templates() -> List[Dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT key, title, body FROM templates ORDER BY key;")
            return [dict(r) for r in cur.fetchall()]

def get_template(key: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT key, title, body FROM templates WHERE key=%s;", (key,))
            row = cur.fetchone()
            return dict(row) if row else None

def update_template(key: str, title: Optional[str] = None, body: Optional[str] = None) -> bool:
    sets, vals = [], []
    if title is not None:
        sets.append("title=%s")
        vals.append(title)
    if body is not None:
        sets.append("body=%s")
        vals.append(body)
    if not sets:
        return False
    vals.append(key)
    query = "UPDATE templates SET " + ", ".join(sets) + ", updated_at=NOW() WHERE key=%s;"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, vals)
        conn.commit()
    return True

def reset_template(key: str) -> bool:
    default = DEFAULT_TEMPLATES.get(key)
    if not default:
        return False
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO templates (key, title, body) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET title=EXCLUDED.title, body=EXCLUDED.body, updated_at=NOW();",
                (key, default["title"], default["body"])
            )
        conn.commit()
    return True
