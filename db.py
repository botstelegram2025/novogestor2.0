import sqlite3
from datetime import datetime, timedelta

DB_NAME = "clientes.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT,
        email TEXT,
        pacote TEXT,
        valor REAL,
        vencimento DATE,
        informacoes TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        conteudo TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def add_cliente(nome, telefone, email, pacote, valor, vencimento, informacoes=""):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clientes (nome, telefone, email, pacote, valor, vencimento, informacoes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (nome, telefone, email, pacote, valor, vencimento, informacoes))
    conn.commit()
    conn.close()

def listar_clientes():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes ORDER BY date(vencimento) ASC")
    rows = cur.fetchall()
    conn.close()
    return rows

def listar_clientes_vencendo():
    hoje = datetime.now().date()
    limite = hoje + timedelta(days=3)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE date(vencimento) <= ? ORDER BY date(vencimento)", (limite,))
    rows = cur.fetchall()
    conn.close()
    return rows

def atualizar_cliente(campo, valor, cliente_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(f"UPDATE clientes SET {campo} = ? WHERE id = ?", (valor, cliente_id))
    conn.commit()
    conn.close()

def excluir_cliente(cliente_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
    conn.commit()
    conn.close()

def add_template(tipo, conteudo):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO templates (tipo, conteudo) VALUES (?, ?)", (tipo, conteudo))
    conn.commit()
    conn.close()

def get_template(tipo):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT conteudo FROM templates WHERE tipo = ? ORDER BY id DESC LIMIT 1", (tipo,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
