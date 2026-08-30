import re


def format_brazilian_phone(value):
    """Formata telefones brasileiros completos sem completar dados ausentes."""
    if value is None:
        return None
    original = str(value).strip()
    digits = re.sub(r"\D", "", original)
    if len(digits) in {12, 13} and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return original
