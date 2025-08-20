from typing import Any, Dict, List, Optional

class TemplateManager:
    def __init__(self, db):
        self.db = db
        # simples cache em memória
        self._templates = {}

    def listar_templates(self, chat_id_usuario: int = None) -> List[Dict[str, Any]]:
        return list(self._templates.values()) or [
            {"id": 1, "nome": "Boas-vindas", "conteudo": "Olá {nome}, bem-vindo!", "ativo": True, "tipo": "texto"},
        ]

    def criar_template(self, nome: str, conteudo: str, tipo: str = "texto", ativo: bool = True) -> Dict[str, Any]:
        new_id = max(self._templates.keys() or [0]) + 1
        tpl = {"id": new_id, "nome": nome, "conteudo": conteudo, "tipo": tipo, "ativo": ativo, "uso": 0}
        self._templates[new_id] = tpl
        return tpl

    def get_template_by_id(self, template_id: int) -> Optional[Dict[str, Any]]:
        return self._templates.get(int(template_id))

    def buscar_template_por_id(self, template_id: int, chat_id_usuario: int = None) -> Optional[Dict[str, Any]]:
        return self.get_template_by_id(template_id)

    def atualizar_campo(self, template_id: int, campo: str, valor, chat_id_usuario: int = None) -> bool:
        tpl = self._templates.get(int(template_id))
        if not tpl:
            return False
        tpl[campo] = valor
        return True

    def excluir_template(self, template_id: int, chat_id_usuario: int = None) -> bool:
        return self._templates.pop(int(template_id), None) is not None

    def processar_template(self, conteudo: str, cliente: Dict[str, Any]) -> str:
        try:
            return conteudo.format(**cliente)
        except Exception:
            return conteudo

    # compat com chamadas no código
    def incrementar_uso_template(self, template_id: int):
        self.increment_usage(template_id)

    def increment_usage(self, template_id: int):
        tpl = self._templates.get(int(template_id))
        if tpl:
            tpl["uso"] = tpl.get("uso", 0) + 1
