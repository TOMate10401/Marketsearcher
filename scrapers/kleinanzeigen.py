import json
import re

from bs4 import BeautifulSoup

from constants import CATEGORY_MAP
from filtering import parse_price_filter, price_to_float
from .common import get


def kleinanzeigen_scraper(search_term, page=1):
    category = search_term.get("category", "Alle Kategorien")
    ka_cat = CATEGORY_MAP.get(category, {}).get("kleinanzeigen")

    if category != "Alle Kategorien" and not ka_cat:
        return []

    term = search_term["term"].strip().replace(" ", "-") or "alles"
    if category != "Alle Kategorien" and ka_cat:
        url = f"https://www.kleinanzeigen.de/s-{term}/{ka_cat}"
    else:
        url = f"https://www.kleinanzeigen.de/s-{term}/k0"

    zip_code = (search_term.get("zip") or "").strip()
    radius = search_term.get("radius")
    if zip_code and radius:
        url += f"l{zip_code}r{int(radius)}"

    params = []
    min_price = parse_price_filter(search_term.get("min_price"))
    if min_price is not None:
        params.append(f"price_min={int(min_price)}")

    max_price = parse_price_filter(search_term.get("max_price"))
    if max_price is not None:
        params.append(f"price_max={int(max_price)}")

    if page > 1:
        params.append(f"pageNum={page}")

    if params:
        url += "?" + "&".join(params)

    try:
        page_resp = get(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(page_resp.content, features="lxml")
    articles = soup.find_all("article", attrs={"data-adid": True})

    items = []
    for art in articles:
        href = art.get("data-href", "")
        if href and not href.startswith("http"):
            href = "https://www.kleinanzeigen.de" + href

        title = ""
        script = art.find("script", type="application/ld+json")
        if script:
            try:
                title = json.loads(script.get_text()).get("title", "")
            except (ValueError, TypeError):
                title = ""
        if not title:
            h = art.find("h3") or art.find("h2")
            if h:
                title = h.get_text(strip=True)

        img = art.find("img")
        img_src = img.get("src", "") if img else ""

        price = ""
        for el in art.find_all(string=re.compile(r"€|VB|Zu verschenken")):
            price = " ".join(el.split())
            break

        items.append(
            {
                "source": "Kleinanzeigen",
                "title": title,
                "price": price,
                "price_value": price_to_float(price),
                "link": href,
                "image_url": img_src,
                "condition": "",
            }
        )

    return items
