import re

def padronizar_telefone(telefone: str) -> str:
    if not telefone:
        return ""
    digits = re.sub(r"\D", "", str(telefone))
    # Remove leading zeros, keep last 11 digits if too long
    digits = digits.lstrip("0")
    if len(digits) > 11:
        digits = digits[-11:]
    return digits

def validar_telefone_whatsapp(telefone: str) -> bool:
    t = padronizar_telefone(telefone)
    return len(t) in (10, 11) and t.isdigit()

def formatar_telefone_exibicao(telefone: str) -> str:
    t = padronizar_telefone(telefone)
    if len(t) == 11:
        return f"({t[:2]}) {t[2:7]}-{t[7:]}"
    if len(t) == 10:
        return f"({t[:2]}) {t[2:6]}-{t[6:]}"
    return telefone

def houve_conversao_telefone(original: str, convertido: str) -> bool:
    return padronizar_telefone(original) != padronizar_telefone(convertido)
