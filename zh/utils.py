from decimal import Decimal


def format_currency(amount, currency="USD"):
    if not amount:
        amount = Decimal(0)
    prefix = "$" if currency == "USD" else ""
    return f"{prefix}{amount:,.2f} {currency}"  # noqa: E231
