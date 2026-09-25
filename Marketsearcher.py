import json
import os
import re
import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

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


def _parse_price_filter(value):
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


def _parse_exclude(value):
    if not value:
        return []
    return [w.strip().lower() for w in str(value).split(",") if w.strip()]


def _get(url):
    return requests.get(url, headers=HEADERS, timeout=20)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_image_bytes(url):
    try:
        resp = _get(url)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except requests.RequestException:
        pass
    return None


def _load_image_bytes(url):
    if not url:
        return None
    data = _fetch_image_bytes(url)
    return BytesIO(data) if data else None


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

    min_price = _parse_price_filter(search_term.get("min_price"))
    if min_price is not None:
        url += "&price_from=" + str(min_price)

    max_price = _parse_price_filter(search_term.get("max_price"))
    if max_price is not None:
        url += "&price_to=" + str(max_price)

    try:
        page = _get(url)
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
            full_title = overlay["title"].split(", Marke:")[0].strip()
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
        item_dict["price_value"] = _price_to_float(item_dict["price"])
        vinted_items.append(item_dict)

    return vinted_items, False


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

    min_price = _parse_price_filter(search_term.get("min_price"))
    max_price = _parse_price_filter(search_term.get("max_price"))
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
            price_value = _price_to_float(item["price"]["value"])
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
    min_price = _parse_price_filter(search_term.get("min_price"))
    if min_price is not None:
        params.append(f"price_min={int(min_price)}")

    max_price = _parse_price_filter(search_term.get("max_price"))
    if max_price is not None:
        params.append(f"price_max={int(max_price)}")

    if page > 1:
        params.append(f"pageNum={page}")

    if params:
        url += "?" + "&".join(params)

    try:
        page_resp = _get(url)
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
                "price_value": _price_to_float(price),
                "link": href,
                "image_url": img_src,
                "condition": "",
            }
        )

    return items


def run_sources(search_term, token, page, use_vinted, use_ebay, use_kleinanzeigen):
    """Führt alle aktiven Quellen parallel aus. Liefert (items, vinted_blocked, errors)."""
    items = []
    errors = []
    vinted_blocked = False

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        if use_vinted and page == 1:
            futures[executor.submit(vinted_scrape, search_term)] = "vinted"
        if use_ebay:
            futures[executor.submit(ebay_api_search, search_term, token, page)] = "ebay"
        if use_kleinanzeigen:
            futures[executor.submit(kleinanzeigen_scraper, search_term, page)] = "kleinanzeigen"

        for future, source in futures.items():
            try:
                result = future.result()
            except Exception as exc:
                errors.append(f"{source}: Unerwarteter Fehler ({exc})")
                continue

            if source == "vinted":
                source_items, vinted_blocked = result
            elif source == "ebay":
                source_items, source_errors = result
                errors.extend(source_errors)
            else:
                source_items = result

            items.extend(source_items)

    return items, vinted_blocked, errors


def filter_by_price(items, search_term):
    min_price = _parse_price_filter(search_term.get("min_price"))
    max_price = _parse_price_filter(search_term.get("max_price"))
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


def _search_signature(search_term, use_vinted, use_ebay, use_kleinanzeigen):
    sig = {k: v for k, v in search_term.items() if k != "exclude"}
    sig["sources"] = [use_vinted, use_ebay, use_kleinanzeigen]
    return json.dumps(sig, sort_keys=True, default=str)


def _item_key(item):
    return (item.get("source"), item.get("link") or item.get("title"))


def _render_card(item):
    with st.container(border=True):
        img_data = _load_image_bytes(item.get("image_url"))
        if img_data:
            st.image(img_data)

        title = (item.get("title") or "").strip() or "(ohne Titel)"
        safe_title = title.replace("[", "(").replace("]", ")")
        link = item.get("link") or ""

        if link:
            st.markdown(f"**[{safe_title}]({link})**")
        else:
            st.markdown(f"**{safe_title}**")

        meta = [item.get("source", "")]
        if item.get("distance"):
            meta.append(item["distance"])
        st.caption(" · ".join(m for m in meta if m))

        if item.get("price"):
            st.markdown(f"💰 **{item['price']}**")
        if item.get("condition"):
            st.caption(f"Zustand: {item['condition']}")
        if link:
            st.markdown(f"[🔗 Link]({link})")


def _render_grid(items, columns=3):
    if not items:
        st.info("Keine Ergebnisse gefunden.")
        return
    cols = st.columns(columns)
    for idx, item in enumerate(items):
        with cols[idx % columns]:
            _render_card(item)


def main():
    st.title("Marketsearcher")

    os.environ["EBAY_ENV"] = "production"
    st.caption("🔷 Verwende eBay Production (echte Daten)")

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

    search_term["exclude"] = st.text_input(
        "Ausschließen (kommagetrennt, z.B. defekt, Ersatzteile)", ""
    )

    loc1, loc2 = st.columns(2)
    search_term["zip"] = loc1.text_input(
        "PLZ (optional, nur eBay & Kleinanzeigen)", ""
    )
    search_term["radius"] = loc2.selectbox(
        "Umkreis (km)", (5, 10, 20, 50, 100, 200), index=3
    )

    if search_term["zip"].strip() and use_vinted:
        st.caption(
            "ℹ️ Der Standortfilter wirkt nicht bei Vinted "
            "(Versand-Marktplatz ohne Standortsuche)."
        )

    sort_option = st.selectbox(
        "Sortieren nach", ("Keine Sortierung", "Preis aufsteigend",
                           "Preis absteigend", "Titel")
    )

    if not search_term["term"].strip():
        st.info("Suchbegriff eingeben, um Ergebnisse zu sehen.")
        return

    zip_clean = re.sub(r"\D", "", search_term["zip"])
    if search_term["zip"].strip() and len(zip_clean) != 5:
        st.warning("Bitte eine gültige 5-stellige PLZ angeben.")
        return
    search_term["zip"] = zip_clean
    if not zip_clean:
        search_term["radius"] = None

    if use_ebay:
        if "ebay_token" not in st.session_state:
            st.session_state.ebay_token = None
        if not st.session_state.ebay_token:
            st.session_state.ebay_token = get_ebay_token()

    sig = _search_signature(search_term, use_vinted, use_ebay, use_kleinanzeigen)
    if st.session_state.get("search_sig") != sig:
        st.session_state.search_sig = sig
        st.session_state.result_items = []
        st.session_state.result_page = 0
        st.session_state.search_errors = []
        st.session_state.vinted_blocked = False
        st.session_state.no_more = False

    token = st.session_state.get("ebay_token")

    if st.session_state.result_page == 0:
        new_items, blocked, errors = run_sources(
            search_term, token, 1, use_vinted, use_ebay, use_kleinanzeigen
        )
        st.session_state.result_items = new_items
        st.session_state.result_page = 1
        st.session_state.search_errors = errors
        st.session_state.vinted_blocked = blocked

    for err in st.session_state.search_errors:
        st.warning(err)

    if st.session_state.vinted_blocked:
        st.warning(
            "Vinted blockiert automatische Abfragen (Bot-Schutz). "
            "Vinted-Ergebnisse konnten nicht geladen werden."
        )

    exclude_words = _parse_exclude(search_term.get("exclude"))
    items = filter_by_keywords(st.session_state.result_items, exclude_words)
    items = filter_by_price(items, search_term)
    items = sort_items(items, sort_option)

    st.caption(
        f"{len(items)} Ergebnisse · Seite {st.session_state.result_page}"
    )

    _render_grid(items)

    if st.session_state.get("no_more"):
        st.caption("Keine weiteren Ergebnisse.")
        return

    if st.button("Mehr laden"):
        next_page = st.session_state.result_page + 1
        new_items, _blocked, errors = run_sources(
            search_term, token, next_page, use_vinted, use_ebay, use_kleinanzeigen
        )
        existing = {_item_key(it) for it in st.session_state.result_items}
        added = [it for it in new_items if _item_key(it) not in existing]
        st.session_state.result_items += added
        st.session_state.result_page = next_page
        if errors:
            st.session_state.search_errors += errors
        if not added:
            st.session_state.no_more = True
        st.rerun()


if __name__ == "__main__":
    main()
