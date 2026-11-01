from concurrent.futures import ThreadPoolExecutor

import requests

from .common import get

VINTED_CHECK_URL = "https://www.vinted.de/catalog?search_text=marketsearcher-healthcheck"
KLEINANZEIGEN_CHECK_URL = "https://www.kleinanzeigen.de/s-marketsearcher-healthcheck/k0"
EBAY_CHECK_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

SOURCES = ("Vinted", "eBay", "Kleinanzeigen")


def _check_http(url):
    """True, wenn die Seite mit 200 antwortet (Bot-Block zaehlt als nicht ok)."""
    try:
        resp = get(url)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _check_ebay(token):
    if not token:
        return False
    try:
        resp = requests.get(
            EBAY_CHECK_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
            },
            params={"q": "marketsearcher healthcheck", "limit": 1},
            timeout=20,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def check_sources(ebay_token=None, max_workers=3):
    """Prueft alle drei Quellen parallel. Liefert {quelle: True/False}."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_vinted = executor.submit(_check_http, VINTED_CHECK_URL)
        fut_ka = executor.submit(_check_http, KLEINANZEIGEN_CHECK_URL)
        fut_ebay = executor.submit(_check_ebay, ebay_token)
        return {
            "Vinted": fut_vinted.result(),
            "eBay": fut_ebay.result(),
            "Kleinanzeigen": fut_ka.result(),
        }
