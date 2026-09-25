import json
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from filtering import price_to_float
from scrapers.common import get

PRICE_TOLERANCE = 0.05

STATUS_OK = "ok"
STATUS_GONE = "gone"
STATUS_ERROR = "error"


def extract_item_id(source, link):
    if not link:
        return ""
    if source == "Kleinanzeigen":
        m = re.search(r"/(\d{8,})-\d+-\d+", link)
        return m.group(1) if m else ""
    if source == "eBay":
        m = re.search(r"/itm/(\d+)", link)
        return m.group(1) if m else ""
    if source == "Vinted":
        m = re.search(r"/items/(\d+)", link)
        return m.group(1) if m else ""
    return ""


def _result(status, current_price="", price_value=None):
    return {
        "status": status,
        "current_price": current_price,
        "current_price_value": price_value,
    }


def check_kleinanzeigen(link):
    try:
        resp = get(link)
    except requests.RequestException:
        return _result(STATUS_ERROR)
    if resp.status_code != 200:
        return _result(STATUS_GONE)
    soup = BeautifulSoup(resp.content, features="lxml")
    if not soup.find(id="viewad-title"):
        return _result(STATUS_GONE)
    price = soup.find(id="viewad-price")
    price_text = price.get_text(strip=True) if price else ""
    return _result(
        STATUS_OK,
        price_text,
        price_to_float(price_text) if price_text else None,
    )


def check_vinted(link):
    try:
        resp = get(link)
    except requests.RequestException:
        return _result(STATUS_ERROR)
    if resp.status_code != 200:
        return _result(STATUS_GONE)
    soup = BeautifulSoup(resp.content, features="lxml")
    ld = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            ld = data
            break
    if ld is None:
        return _result(STATUS_GONE)

    offers = ld.get("offers") or {}
    availability = (offers.get("availability") or "").lower()
    price = offers.get("price") or ld.get("price")
    if availability and "instock" not in availability:
        return _result(STATUS_GONE, str(price), price_to_float(price))
    return _result(
        STATUS_OK,
        str(price) if price is not None else "",
        price_to_float(price) if price is not None else None,
    )


def check_ebay(link, token):
    item_id = extract_item_id("eBay", link)
    if not item_id:
        return _result(STATUS_ERROR)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
    }
    url = f"https://api.ebay.com/buy/browse/v1/item/{item_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException:
        return _result(STATUS_ERROR)

    if resp.status_code == 404:
        return _result(STATUS_GONE)
    if resp.status_code != 200:
        return _result(STATUS_ERROR)

    try:
        data = resp.json()
    except ValueError:
        return _result(STATUS_ERROR)

    price_obj = data.get("price") or {}
    price = price_obj.get("value")
    price_str = (
        f"{price} {price_obj.get('currency', 'EUR')}" if price is not None else ""
    )
    return _result(
        STATUS_OK,
        price_str,
        price_to_float(price) if price is not None else None,
    )


def check_favorite(entry, ebay_token=None):
    """Prüft einen Favoriten. Liefert dict mit status/price-Info."""
    source = entry.get("source")
    link = entry.get("link") or ""

    if source == "Kleinanzeigen":
        return check_kleinanzeigen(link)
    if source == "Vinted":
        return check_vinted(link)
    if source == "eBay":
        return check_ebay(link, ebay_token)
    return _result(STATUS_ERROR)


def check_favorites(entries, ebay_token=None, max_workers=6):
    """Prüft alle Favoriten parallel. Liefert {favorite_key: result}."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_favorite, entry, ebay_token): entry
            for entry in entries
        }
        results = {}
        for future, entry in futures.items():
            key = f"{entry.get('source')}|{entry.get('link') or entry.get('title')}"
            try:
                results[key] = future.result()
            except Exception:
                results[key] = _result(STATUS_ERROR)
    return results


def price_changed(old_value, new_value, tolerance=PRICE_TOLERANCE):
    """True, wenn sich der Preis signifikant (Toleranz 5%) geändert hat."""
    if old_value is None or new_value is None:
        return False
    if old_value == 0 and new_value == 0:
        return False
    if old_value == 0 or new_value == 0:
        return True
    return abs(new_value - old_value) / old_value > tolerance
