import base64
import os

import requests

from config import load_env
from constants import CATEGORY_MAP
from filtering import parse_price_filter, price_to_float

PRODUCTION_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
DEFAULT_SCOPE = "https://api.ebay.com/oauth/api_scope"


def _b64_credentials(client_id, client_secret):
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def get_ebay_token():
    """Holt ein eBay Application Access Token aus der Umgebung oder .env."""
    load_env()
    client_id = os.environ.get("EBAY_CLIENT_ID")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    token_url = PRODUCTION_TOKEN_URL
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {_b64_credentials(client_id, client_secret)}",
    }
    data = {"grant_type": "client_credentials", "scope": DEFAULT_SCOPE}

    try:
        resp = requests.post(token_url, headers=headers, data=data, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except requests.RequestException:
        pass
    return None


def ebay_api_search(search_term, token=None, page=1):
    """Suche über die eBay Browse API (Production). Liefert (items, errors)."""
    base_url = "https://api.ebay.com"

    if not token:
        token = get_ebay_token()
        if not token:
            return [], ["eBay Token konnte nicht generiert werden. Prüfe .env-Datei."]

    term = search_term["term"].strip()
    category = search_term.get("category", "Alle Kategorien")
    ebay_cat = CATEGORY_MAP.get(category, {}).get("ebay")

    if category != "Alle Kategorien" and not ebay_cat:
        return [], []

    url = f"{base_url}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
    }
    params = {"q": term, "limit": 50}
    if page > 1:
        params["offset"] = (page - 1) * params["limit"]

    filters = []
    if ebay_cat:
        filters.append(f"categories:{{{ebay_cat}}}")

    min_price = parse_price_filter(search_term.get("min_price"))
    max_price = parse_price_filter(search_term.get("max_price"))
    price_range = f"[{min_price if min_price is not None else ''}..{max_price if max_price is not None else ''}]"
    if min_price is not None or max_price is not None:
        filters.append(f"price:{price_range}")

    zip_code = (search_term.get("zip") or "").strip()
    radius = search_term.get("radius")
    if zip_code and radius:
        filters.append(f"pickupPostalCode:{zip_code}")
        filters.append("pickupCountry:DE")
        filters.append(f"pickupRadius:{int(radius)}")
        filters.append("pickupRadiusUnit:km")

    if filters:
        params["filter"] = ",".join(filters)

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            return [], [f"eBay API Fehler: {resp.status_code} - {resp.text}"]
        data = resp.json()
    except requests.RequestException as e:
        return [], [f"eBay API Request fehlgeschlagen: {e}"]
    except ValueError:
        return [], ["eBay API Antwort war kein gültiges JSON."]

    ebay_items = []
    for item in data.get("itemSummaries", []):
        price_value = None
        price_str = ""
        if "price" in item and "value" in item["price"]:
            price_value = price_to_float(item["price"]["value"])
            price_str = f"{item['price']['value']} {item['price'].get('currency', 'EUR')}"

        image = item.get("image") or {}
        image_url = image.get("imageUrl", "")
        if not image_url:
            for thumb in item.get("thumbnailImages") or []:
                image_url = thumb.get("imageUrl", "")
                if image_url:
                    break
        link = item.get("itemAffiliateWebUrl") or item.get("itemWebUrl", "")

        distance = ""
        item_distance = item.get("itemDistance") or {}
        if item_distance.get("value") is not None:
            distance = f"{item_distance.get('value')} {item_distance.get('unit', 'km')}"

        ebay_items.append(
            {
                "source": "eBay",
                "title": item.get("title", ""),
                "price": price_str,
                "price_value": price_value,
                "link": link,
                "image_url": image_url,
                "condition": item.get("condition", ""),
                "distance": distance,
            }
        )
    return ebay_items, []
