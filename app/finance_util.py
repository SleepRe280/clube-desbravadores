"""Valores monetários em centavos (BRL) para evitar float."""


def format_brl_cents(cents: int | None) -> str:
    if cents is None:
        return "R$ 0,00"
    n = int(cents)
    neg = n < 0
    n = abs(n)
    inteiro, frac = divmod(n, 100)
    s = f"{inteiro},{frac:02d}"
    return ("-" if neg else "") + "R$ " + s


def parse_money_brl(raw: str) -> int | None:
    """Converte texto tipo '50', '50,00', '1.234,56' em centavos."""
    s = (raw or "").strip().replace(" ", "").replace("R$", "").replace("r$", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    if v < 0:
        return None
    return int(round(v * 100))
