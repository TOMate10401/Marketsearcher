import csv
import json
import os
from io import StringIO

FAVORITES_PATH = os.environ.get("FAVORITES_PATH", "favorites.json")

FAVORITE_FIELDS = [
    "source",
    "title",
    "price",
    "price_value",
    "link",
    "condition",
    "distance",
    "image_url",
    "item_id",
    "saved_at",
    "last_checked",
    "check_status",
    "current_price",
    "current_price_value",
]

CHECK_FIELDS = ("last_checked", "check_status", "current_price")


def item_key(item):
    return f"{item.get('source')}|{item.get('link') or item.get('title')}"


def load_favorites(path=FAVORITES_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_favorites(favorites, path=FAVORITES_PATH):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(favorites, fh, ensure_ascii=False, indent=2)


def add_favorite(favorites, item, saved_at):
    key = item_key(item)
    if key in favorites:
        return favorites, False
    entry = {
        field: item.get(field, "")
        for field in FAVORITE_FIELDS
        if field not in ("saved_at",) and field not in CHECK_FIELDS
    }
    entry["saved_at"] = saved_at
    favorites[key] = entry
    return favorites, True


def remove_favorite(favorites, item):
    key = item_key(item)
    if key not in favorites:
        return favorites, False
    del favorites[key]
    return favorites, True


def apply_check_result(favorites, key, result, checked_at):
    """Speichert das Check-Ergebnis an einem Favoriten."""
    if key not in favorites:
        return favorites
    entry = favorites[key]
    entry["last_checked"] = checked_at
    entry["check_status"] = result.get("status", "")
    if result.get("current_price"):
        entry["current_price"] = result["current_price"]
    if result.get("current_price_value") is not None:
        entry["current_price_value"] = result["current_price_value"]
    return favorites


def remove_gone(favorites):
    """Entfernt alle als 'gone' markierten Favoriten. Liefert (favorites, removed_count)."""
    gone_keys = [k for k, v in favorites.items() if v.get("check_status") == "gone"]
    for key in gone_keys:
        del favorites[key]
    return favorites, len(gone_keys)


def items_to_csv(items):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=FAVORITE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = {field: item.get(field, "") for field in FAVORITE_FIELDS}
        writer.writerow(row)
    return output.getvalue()
