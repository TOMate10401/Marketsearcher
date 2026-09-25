import re


def price_to_float(price_str):
    if price_str is None:
        return None
    if isinstance(price_str, (int, float)):
        return float(price_str)
    if not price_str.strip():
        return None
    cleaned = re.sub(r"[^\d,\.]", "", price_str.strip())
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_price_filter(value):
    if value in ("", None):
        return None
    cleaned = str(value).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def parse_exclude(value):
    if not value:
        return []
    return [w.strip().lower() for w in str(value).split(",") if w.strip()]


def filter_by_price(items, search_term):
    min_price = parse_price_filter(search_term.get("min_price"))
    max_price = parse_price_filter(search_term.get("max_price"))
    if min_price is None and max_price is None:
        return items

    filtered = []
    for item in items:
        price = item.get("price_value")
        if price is None:
            filtered.append(item)
            continue
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        filtered.append(item)
    return filtered


def filter_by_keywords(items, exclude_words):
    if not exclude_words:
        return items
    return [
        item
        for item in items
        if not any(w in (item.get("title") or "").lower() for w in exclude_words)
    ]


def sort_items(items, key):
    if not items:
        return items

    def _price_key(d):
        v = d.get("price_value")
        return v if v is not None else float("inf")

    def _price_key_desc(d):
        v = d.get("price_value")
        return v if v is not None else float("-inf")

    if key == "Preis aufsteigend":
        return sorted(items, key=_price_key)
    if key == "Preis absteigend":
        return sorted(items, key=_price_key_desc, reverse=True)
    if key == "Titel":
        return sorted(items, key=lambda d: d.get("title", "").lower())
    return items
