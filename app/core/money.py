from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def round_money(value: Decimal | float | int) -> Decimal:
    # str() evita arrastrar el error binario cuando SQLite devuelve float en las sumas.
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def to_local(amount_usd: Decimal, rate: Decimal) -> Decimal:
    return round_money(Decimal(amount_usd) * Decimal(rate))


def price_with_margin(cost_usd: Decimal, margin_pct: Decimal | None) -> Decimal:
    """Precio de venta = costo × (1 + margen / 100)."""
    margin = Decimal(str(margin_pct or 0))
    return round_money(Decimal(str(cost_usd)) * (1 + margin / 100))
