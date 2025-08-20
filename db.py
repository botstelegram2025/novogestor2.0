def init_db():
    with connect() as conn:
        cur = conn.cursor()
        # tabela clientes (já existia)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # nova tabela usuarios
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

def buscar_usuario(tg_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE tg_id = %s;", (tg_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def inserir_usuario(tg_id: int, nome: str, email: str, telefone: str) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usuarios (tg_id, nome, email, telefone) VALUES (%s, %s, %s, %s) RETURNING id;",
            (tg_id, nome, email, telefone),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
