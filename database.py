from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

class DatabaseManager:
    """Implementação mínima e segura em memória.
    Troque por Postgres depois (ex.: psycopg2 / SQLAlchemy).
    """
    def __init__(self):
        self._clientes: Dict[int, Dict[str, Any]] = {}
        self._templates: Dict[int, Dict[str, Any]] = {}
        self._logs_envio: List[Dict[str, Any]] = []
        self._config: Dict[str, Any] = {}
        self._fila: List[Dict[str, Any]] = []
        self._auto_id_cliente = 1
        self._auto_id_template = 1

    # Conexão
    def get_connection(self):  # compatibilidade
        return None

    # Clientes
    def listar_clientes(self) -> List[Dict[str, Any]]:
        return list(self._clientes.values())

    def listar_clientes_vencendo(self, dias: int = 3) -> List[Dict[str, Any]]:
        out = []
        today = datetime.utcnow().date()
        for c in self._clientes.values():
            venc = c.get("vencimento")
            if isinstance(venc, datetime):
                venc = venc.date()
            if venc and today <= venc <= today + timedelta(days=dias):
                out.append(c)
        return out

    def buscar_clientes_por_telefone(self, termo: str) -> List[Dict[str, Any]]:
        termo = (termo or "").strip()
        return [c for c in self._clientes.values() if termo in str(c.get("telefone",""))]

    def criar_cliente(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        cid = self._auto_id_cliente
        self._auto_id_cliente += 1
        dados = dict(dados or {})
        dados.setdefault("id", cid)
        self._clientes[cid] = dados
        return dados

    def buscar_cliente_por_id(self, cid: int) -> Optional[Dict[str, Any]]:
        return self._clientes.get(int(cid))

    get_client_by_id = buscar_cliente_por_id  # alias

    def atualizar_vencimento_cliente(self, cid: int, novo_vencimento) -> bool:
        c = self._clientes.get(int(cid))
        if not c:
            return False
        c["vencimento"] = novo_vencimento
        return True

    def atualizar_cliente(self, cid: int, **campos) -> bool:
        c = self._clientes.get(int(cid))
        if not c:
            return False
        c.update(campos)
        return True

    def excluir_cliente(self, cid: int) -> bool:
        return self._clientes.pop(int(cid), None) is not None

    def obter_preferencias_cliente(self, cid: int) -> Dict[str, Any]:
        c = self._clientes.get(int(cid), {})
        return c.get("preferencias", {})

    def atualizar_preferencias_cliente(self, cid: int, prefs: Dict[str, Any]) -> bool:
        c = self._clientes.get(int(cid))
        if not c:
            return False
        c["preferencias"] = dict(prefs or {})
        return True

    # Templates
    def listar_templates(self) -> List[Dict[str, Any]]:
        return list(self._templates.values())

    def obter_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        return self._templates.get(int(template_id))

    def atualizar_template_campo(self, template_id: int, campo: str, valor) -> bool:
        t = self._templates.get(int(template_id))
        if not t:
            return False
        t[campo] = valor
        return True

    # Métricas / logs
    def registrar_envio(self, cliente_id: int, sucesso: bool, canal: str = "whatsapp", detalhe: str = ""):
        self._logs_envio.append({
            "cliente_id": int(cliente_id),
            "sucesso": bool(sucesso),
            "canal": canal,
            "detalhe": detalhe,
            "ts": datetime.utcnow()
        })

    def log_message(self, mensagem: str):
        self._logs_envio.append({"mensagem": mensagem, "ts": datetime.utcnow()})

    def obter_logs_periodo(self, dias: int = 1) -> List[Dict[str, Any]]:
        limite = datetime.utcnow() - timedelta(days=dias)
        return [l for l in self._logs_envio if l.get("ts") and l["ts"] >= limite]

    def obter_logs_envios(self) -> List[Dict[str, Any]]:
        return self._logs_envio[-200:]

    # Configuração
    def atualizar_configuracao(self, chave: str, valor):
        self._config[chave] = valor

    def obter_configuracao(self, chave: str, default=None):
        return self._config.get(chave, default)

    def salvar_configuracao(self, chave: str, valor):
        self.atualizar_configuracao(chave, valor)

    # Estatísticas
    def contar_clientes(self) -> int:
        return len(self._clientes)

    def contar_templates_ativos(self) -> int:
        return len([t for t in self._templates.values() if t.get("ativo", True)])

    def contar_mensagens_hoje(self) -> int:
        return len([l for l in self._logs_envio if l.get("ts") and l["ts"].date() == datetime.utcnow().date()])

    def obter_estatisticas_clientes(self) -> dict:
        return {
            "total": self.contar_clientes(),
            "ativos": len([c for c in self._clientes.values() if c.get("ativo", True)]),
        }

    def obter_todas_mensagens_fila(self) -> list:
        return list(self._fila)

    def cancelar_mensagem_fila(self, msg_id: str) -> bool:
        before = len(self._fila)
        self._fila = [m for m in self._fila if m.get("id") != msg_id]
        return len(self._fila) != before

    def fetch_all(self, query: str) -> list:
        # Compatibilidade simples; retorna vazio
        return []

    def obter_mensagens_pendentes(self) -> list:
        return [m for m in self._fila if not m.get("enviado")]

    def obter_estatisticas_usuario(self, chat_id: int) -> dict:
        return {"chat_id": chat_id, "total_envios": len(self._logs_envio)}
