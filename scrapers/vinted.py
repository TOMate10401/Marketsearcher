import requests
from bs4 import BeautifulSoup

from constants import CATEGORY_MAP, VINTED_CONDITION, VINTED_GENDER, VINTED_SIZE
from filtering import parse_price_filter, price_to_float
from .common import get


def vinted_scrape(search_term):
    """Liefert (items, blocked). Keine Streamlit-Aufrufe (thread-sicher)."""
    category = search_term.get("category", "Alle Kategorien")
    vinted_cat = CATEGORY_MAP.get(category, {}).get("vinted")

    if category != "Alle Kategorien" and not vinted_cat:
        return [], False

    term = search_term["term"].strip().replace(" ", "+")
    url = "https://www.vinted.de/catalog?search_text=" + term

    if category != "Alle Kategorien" and vinted_cat:
        url += "&catalog[]=" + vinted_cat

    if search_term.get("gender") and search_term["gender"] != "":
        url += "&catalog[]=" + VINTED_GENDER[search_term["gender"]]

    if search_term.get("size"):
        for x in search_term["size"]:
            url += "&size_ids[]=" + VINTED_SIZE[x]

    if search_term.get("condition"):
        for x in search_term["condition"]:
            url += "&status_ids[]=" + VINTED_CONDITION[x]

    min_price = parse_price_filter(search_term.get("min_price"))
    if min_price is not None:
        url += "&price_from=" + str(min_price)

    max_price = parse_price_filter(search_term.get("max_price"))
    if max_price is not None:
        url += "&price_to=" + str(max_price)

    try:
        page = get(url)
    except requests.RequestException:
        return [], False

    if page.status_code != 200:
        return [], True

    soup = BeautifulSoup(page.content, features="lxml")
    items = soup.find_all(attrs={"data-testid": "grid-item"})

    vinted_items = []
    for item in items:
        id_div = item.find(
            "div", {"data-testid": lambda x: x and x.startswith("product-item-id-")}
        )
        if not id_div:
            continue
        product_id = id_div["data-testid"].split("-")[-1]

        def _text(testid):
            el = item.find("p", {"data-testid": testid})
            return el.text.strip() if el else ""

        def _attr(tag, testid, attr):
            el = item.find(tag, {"data-testid": testid})
            return el[attr] if el and el.has_attr(attr) else ""

        overlay = item.find(
            "a", {"data-testid": f"product-item-id-{product_id}--overlay-link"}
        )
        full_title = ""
        if overlay and overlay.get("title"):
            full_title = overlay["title"].split(", Marke:")[0]
            full_title = full_title.split(", Zustand:")[0]
            full_title = full_title.split(", Größe:")[0].strip()
        item_dict = {
            "source": "Vinted",
            "product_id": product_id,
            "title": full_title
            or _text(f"product-item-id-{product_id}--description-title"),
            "price": _text(f"product-item-id-{product_id}--price-text"),
            "condition": _text(
                f"product-item-id-{product_id}--description-subtitle"
            ),
            "link": (
                "https://www.vinted.de"
                + _attr(
                    "a", f"product-item-id-{product_id}--overlay-link", "href"
                )
            ),
            "image_url": _attr(
                "img", f"product-item-id-{product_id}--image--img", "src"
            ),
        }
        item_dict["price_value"] = price_to_float(item_dict["price"])
        vinted_items.append(item_dict)

    return vinted_items, False
