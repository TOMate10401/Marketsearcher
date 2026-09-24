import json
import os
import re
import base64

import requests
from bs4 import BeautifulSoup
import streamlit as st


CATEGORIES = [
    "Alle Kategorien",
    "Mode & Kleidung",
    "Elektronik",
    "Haus & Garten",
    "Sport & Outdoor",
    "Buecher, Filme & Musik",
    "Hobbys & Sammeln",
    "Auto, Rad & Boot",
    "Familie, Kind & Baby",
    "Beauty & Gesundheit",
    "Haustiere",
    "Immobilien",
]

CATEGORY_MAP = {
    "Mode & Kleidung": {
        "vinted": "1904",
        "ebay": "11450",
        "kleinanzeigen": "c169",
    },
    "Elektronik": {
        "vinted": "2994",
        "ebay": "58058",
        "kleinanzeigen": "c93",
    },
    "Haus & Garten": {
        "vinted": "1918",
        "ebay": "11700",
        "kleinanzeigen": "c76",
    },
    "Sport & Outdoor": {
        "vinted": "4332",
        "ebay": "888",
        "kleinanzeigen": "c178",
    },
    "Buecher, Filme & Musik": {
        "vinted": "2309",
        "ebay": "267",
        "kleinanzeigen": "c77",
    },
    "Hobbys & Sammeln": {
        "vinted": "4824",
        "ebay": "1",
        "kleinanzeigen": "c86",
    },
    "Auto, Rad & Boot": {
        "vinted": None,
        "ebay": "131090",
        "kleinanzeigen": "c21",
    },
    "Familie, Kind & Baby": {
        "vinted": "1193",
        "ebay": "171146",
        "kleinanzeigen": "c78",
    },
    "Beauty & Gesundheit": {
        "vinted": None,
        "ebay": "26395",
        "kleinanzeigen": "c59",
    },
    "Haustiere": {
        "vinted": None,
        "ebay": None,
        "kleinanzeigen": "c80",
    },
    "Immobilien": {
        "vinted": None,
        "ebay": None,
        "kleinanzeigen": "c33",
    },
}

VINTED_GENDER = {
    "male": "5",
    "female": "1904",
}

VINTED_SIZE = {
    "XS": "206",
    "S": "207",
    "M": "208",
    "L": "209",
    "XL": "210",
    "XXL": "211",
}

VINTED_CONDITION = {
    "neu": "6",
    "wie neu": "1",
    "sehr gut": "2",
    "gut": "3",
    "gebraucht": "4",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

PRODUCTION_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
DEFAULT_SCOPE = "https://api.ebay.com/oauth/api_scope"


def _load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()


def _b64_credentials(client_id, client_secret):
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def get_ebay_token():
    """Holt ein eBay Application Access Token aus der Umgebung oder .env."""
    _load_env()
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


def _price_to_float(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d,\.]", "", price_str)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _get(url):
    return requests.get(url, headers=HEADERS, timeout=20)


def vinted_scrape(search_term):
    category = search_term.get("category", "Alle Kategorien")
    vinted_cat = CATEGORY_MAP.get(category, {}).get("vinted")

    if category != "Alle Kategorien" and not vinted_cat:
        return []

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

    if search_term.get("min_price") not in ("", None):
        url += "&price_from=" + str(search_term["min_price"])

    if search_term.get("max_price") not in ("", None):
        url += "&price_to=" + str(search_term["max_price"])

    try:
        page = _get(url)
    except requests.RequestException:
        return []

    if page.status_code != 200:
        st.session_state["vinted_blocked"] = True
        return []

    soup = BeautifulSoup(page.content, features="lxml")
    items = soup.find_all("div", class_="feed-grid__item")

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

        item_dict = {
            "source": "Vinted",
            "product_id": product_id,
            "title": _text(f"product-item-id-{product_id}--description-title"),
            "price": _text(f"product-item-id-{product_id}--price-text"),
            "condition": _text(
                f"product-item-id-{product_id}--description-subtitle"
            ),
            "link": _attr(
                "a", f"product-item-id-{product_id}--overlay-link", "href"
            ),
            "image_url": _attr(
                "img", f"product-item-id-{product_id}--image--img", "src"
            ),
        }
        item_dict["price_value"] = _price_to_float(item_dict["price"])
        vinted_items.append(item_dict)

    return vinted_items


def ebay_api_search(search_term, token=None):
    """Suche über die eBay Browse API (Production)."""
    base_url = "https://api.ebay.com"

    # Token holen, falls nicht mitgegeben
    if not token:
        token = get_ebay_token()
        if not token:
            st.error("eBay Token konnte nicht generiert werden. Prüfe .env-Datei.")
            return []

    term = search_term["term"].strip()
    category = search_term.get("category", "Alle Kategorien")
    ebay_cat = CATEGORY_MAP.get(category, {}).get("ebay")

    if category != "Alle Kategorien" and not ebay_cat:
        return []

    # API-Request
    url = f"{base_url}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
    }
    params = {"q": term, "limit": 50}
    if ebay_cat:
        params["filter"] = f"categories:{{{ebay_cat}}}"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            st.warning(f"eBay API Fehler: {resp.status_code} - {resp.text}")
            return []
        data = resp.json()
    except requests.RequestException as e:
        st.error(f"eBay API Request fehlgeschlagen: {e}")
        return []

    # Ergebnisse parsen
    ebay_items = []
    for item in data.get("itemSummaries", []):
        price_value = None
        price_str = ""
        if "price" in item and "value" in item["price"]:
            price_value = _price_to_float(item["price"]["value"])
            price_str = f"{item['price']['value']} {item['price'].get('currency', 'EUR')}"

        ebay_items.append(
            {
                "source": "eBay",
                "title": item.get("title", ""),
                "price": price_str,
                "price_value": price_value,
                "link": item.get("itemAffiliateWebUrl", ""),
                "image_url": item.get("image", {}).get("imageUrl", ""),
                "condition": item.get("condition", ""),
            }
        )
    return ebay_items


def kleinanzeigen_scraper(search_term):
    category = search_term.get("category", "Alle Kategorien")
    ka_cat = CATEGORY_MAP.get(category, {}).get("kleinanzeigen")

    if category != "Alle Kategorien" and not ka_cat:
        return []

    term = search_term["term"].strip().replace(" ", "-") or "alles"
    if category != "Alle Kategorien" and ka_cat:
        url = f"https://www.kleinanzeigen.de/s-{term}/{ka_cat}"
    else:
        url = f"https://www.kleinanzeigen.de/s-{term}/k0"

    try:
        page = _get(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(page.content, features="lxml")
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
                "price_value": _price_to_float(price),
                "link": href,
                "image_url": img_src,
                "condition": "",
            }
        )

    return items


def sort_items(items, key):
    if not items:
        return items
    if key == "Preis aufsteigend":
        return sorted(
            items, key=lambda d: d.get("price_value") or float("inf")
        )
    if key == "Preis absteigend":
        return sorted(
            items,
            key=lambda d: d.get("price_value") or float("inf"),
            reverse=True,
        )
    if key == "Titel":
        return sorted(items, key=lambda d: d.get("title", "").lower())
    return items


def main():
    st.title("Marketsearcher")

    os.environ["EBAY_ENV"] = "production"
    st.caption("🔹 Verwende eBay Production (echte Daten)")

    search_term = {}
    search_term["category"] = st.selectbox("Kategorie", CATEGORIES)
    search_term["term"] = st.text_input("Suchbegriff", "")

    col1, col2, col3 = st.columns(3)
    with col1:
        use_vinted = st.checkbox("Vinted", value=True)
    with col2:
        use_ebay = st.checkbox("eBay", value=True)
    with col3:
        use_kleinanzeigen = st.checkbox("Kleinanzeigen", value=True)

    is_fashion = search_term["category"] in ("Alle Kategorien", "Mode & Kleidung")

    if is_fashion:
        search_term["gender"] = st.selectbox(
            "Gender", ("", "male", "female")
        )
        search_term["size"] = st.multiselect(
            "Größe", ("XS", "S", "M", "L", "XL", "XXL")
        )
        search_term["condition"] = st.multiselect(
            "Zustand", ("neu", "wie neu", "sehr gut", "gut", "gebraucht")
        )
    else:
        search_term["gender"] = ""
        search_term["size"] = []
        search_term["condition"] = []

    sc1, sc2 = st.columns(2)
    search_term["min_price"] = sc1.text_input("Mindestpreis (EUR)", "")
    search_term["max_price"] = sc2.text_input("Maximalpreis (EUR)", "")

    sort_option = st.selectbox(
        "Sortieren nach", ("Keine Sortierung", "Preis aufsteigend",
                           "Preis absteigend", "Titel")
    )

    if not search_term["term"].strip():
        st.info("Suchbegriff eingeben, um Ergebnisse zu sehen.")
        return

    st.session_state["vinted_blocked"] = False

    items = []
    if use_vinted:
        items += vinted_scrape(search_term)
    if use_ebay:
        # Token-Caching für die Session
        if "ebay_token" not in st.session_state:
            st.session_state.ebay_token = None
        if not st.session_state.ebay_token:
            st.session_state.ebay_token = get_ebay_token()
        items += ebay_api_search(search_term, token=st.session_state.ebay_token)
    if use_kleinanzeigen:
        items += kleinanzeigen_scraper(search_term)

    if st.session_state.get("vinted_blocked"):
        st.warning(
            "Vinted blockiert automatische Abfragen (Bot-Schutz). "
            "Vinted-Ergebnisse konnten nicht geladen werden."
        )


    items = sort_items(items, sort_option)

    st.caption(f"{len(items)} Ergebnisse")
    for item in items:
        st.subheader(item["title"])
        st.caption(item["source"])
        if item["condition"]:
            st.write(f"Zustand: {item['condition']}")
        if item["price"]:
            st.write(f"Preis: {item['price']}")
        if item["link"]:
            st.write(f"Link: {item['link']}")
        if item["image_url"]:
            st.image(item["image_url"])
        st.divider()


if __name__ == "__main__":
    main()
