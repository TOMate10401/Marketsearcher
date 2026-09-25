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
    "saved_at",
]


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
    entry = {field: item.get(field, "") for field in FAVORITE_FIELDS if field != "saved_at"}
    entry["saved_at"] = saved_at
    favorites[key] = entry
    return favorites, True


def remove_favorite(favorites, item):
    key = item_key(item)
    if key not in favorites:
        return favorites, False
    del favorites[key]
    return favorites, True


def items_to_csv(items):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=FAVORITE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = {field: item.get(field, "") for field in FAVORITE_FIELDS}
        writer.writerow(row)
    return output.getvalue()
