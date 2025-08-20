from typing import Dict, Any, List

class UserManager:
    def __init__(self, db):
        self.db = db
        self._users: Dict[int, Dict[str, Any]] = {}

    def verificar_acesso(self, chat_id: int) -> bool:
        # Liberado por padrão
        return True

    def get_valor_mensal(self) -> float:
        return 19.90

    def cadastrar_usuario(self, chat_id: int, **dados) -> Dict[str, Any]:
        self._users[chat_id] = {'chat_id': chat_id, **dados}
        return self._users[chat_id]

    def obter_estatisticas(self) -> Dict[str, Any]:
        return {'usuarios': len(self._users)}

    def obter_usuario(self, chat_id: int) -> Dict[str, Any]:
        return self._users.get(chat_id, {'chat_id': chat_id})

    def obter_estatisticas_faturamento(self) -> Dict[str, Any]:
        return {'mensal': len(self._users) * self.get_valor_mensal()}

    def atualizar_dados_usuario(self, chat_id: int, **campos) -> bool:
        u = self._users.setdefault(chat_id, {'chat_id': chat_id})
        u.update(campos)
        return True

    def ativar_plano(self, chat_id: int):
        self.atualizar_dados_usuario(chat_id, plano_ativo=True)

    def obter_estatisticas_usuario(self, chat_id: int) -> Dict[str, Any]:
        return {'chat_id': chat_id, 'envios': 0}

    def listar_usuarios_vencendo(self) -> List[Dict[str, Any]]:
        return []

    def listar_todos_usuarios(self) -> List[Dict[str, Any]]:
        return list(self._users.values())

    def listar_usuarios_por_status(self, status: str) -> List[Dict[str, Any]]:
        return [u for u in self._users.values() if u.get('status') == status]

    def cadastrar_usuario_manual(self, chat_id: int, **dados) -> Dict[str, Any]:
        return self.cadastrar_usuario(chat_id, **dados)

    def buscar_usuarios(self, termo: str) -> List[Dict[str, Any]]:
        termo = (termo or '').lower()
        return [u for u in self._users.values() if termo in str(u)]
    
    def ativar_usuario(self, chat_id: int):
        self.atualizar_dados_usuario(chat_id, ativo=True)
