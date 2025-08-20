import base64
from typing import Dict

def _fake_qr_png_b64() -> str:
    # 1x1 PNG transparente
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="

class MercadoPagoIntegration:
    def __init__(self):
        pass

    def gerar_pix_plano_mensal(self, user_id: int, nome_usuario: str = "") -> Dict:
        return {{
            "success": True,
            "qr_code": _fake_qr_png_b64(),
            "pix_copia_cola": f"00020126580014BR.GOV.BCB.PIX0114fake-chave-pix520400005303986540519.905802BR5925{nome_usuario or 'Usuario'}6009SaoPaulo62070503***6304ABCD",
            "valor": 19.90,
            "status": "pending"
        }}

    def gerar_pix_renovacao(self, user_id: int, nome_usuario: str = "") -> Dict:
        return self.gerar_pix_plano_mensal(user_id, nome_usuario)
