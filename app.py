import hashlib
import json
import os
import re
from datetime import datetime
from io import BytesIO

import requests
import streamlit as st

from constants import CATEGORIES, HEADERS
from favorites import (
    add_favorite,
    item_key,
    items_to_csv,
    load_favorites,
    remove_favorite,
    save_favorites,
)
from filtering import (
    filter_by_keywords,
    filter_by_price,
    parse_exclude,
    sort_items,
)
from scrapers import get_ebay_token, run_sources


SORT_OPTIONS = (
    "Keine Sortierung",
    "Preis aufsteigend",
    "Preis absteigend",
    "Titel",
)

RADIUS_OPTIONS = (5, 10, 20, 50, 100, 200)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_image_bytes(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
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


def _search_signature(search_term, use_vinted, use_ebay, use_kleinanzeigen):
    sig = {k: v for k, v in search_term.items() if k != "exclude"}
    sig["sources"] = [use_vinted, use_ebay, use_kleinanzeigen]
    return json.dumps(sig, sort_keys=True, default=str)


def _fav_button_key(key):
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _saved(key, default):
    return st.session_state.get("saved_search", {}).get(key, default)


def _save_search_state(search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_option):
    st.session_state.saved_search = {
        "category": search_term["category"],
        "term": search_term["term"],
        "use_vinted": use_vinted,
        "use_ebay": use_ebay,
        "use_kleinanzeigen": use_kleinanzeigen,
        "gender": search_term.get("gender", ""),
        "size": search_term.get("size", []),
        "condition": search_term.get("condition", []),
        "min_price": search_term["min_price"],
        "max_price": search_term["max_price"],
        "exclude": search_term["exclude"],
        "zip": search_term["zip"],
        "radius": search_term["radius"],
        "sort": sort_option,
    }


def _render_card(item, favorites):
    key = item_key(item)
    is_favorite = key in favorites

    with st.container(border=True):
        img_data = _load_image_bytes(item.get("image_url"))
        if img_data:
            st.image(img_data)

        title = (item.get("title") or "").strip() or "(ohne Titel)"
        safe_title = title.replace("[", "(").replace("]", ")")
        link = item.get("link") or ""

        title_str = f"{'⭐ ' if is_favorite else ''}{safe_title}"
        if link:
            st.markdown(f"**[{title_str}]({link})**")
        else:
            st.markdown(f"**{title_str}**")

        if item.get("distance"):
            st.caption(item["distance"])

        if item.get("price"):
            st.markdown(f"💰 **{item['price']}**")
        if item.get("condition"):
            st.caption(f"Zustand: {item['condition']}")

        if st.button(
            "★" if is_favorite else "☆",
            key=f"fav-{_fav_button_key(key)}",
            use_container_width=True,
        ):
            if is_favorite:
                remove_favorite(st.session_state.favorites, item)
            else:
                add_favorite(
                    st.session_state.favorites,
                    item,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
            save_favorites(st.session_state.favorites)
            st.rerun()


def _render_grid(items, favorites, columns=3):
    if not items:
        st.info("Keine Ergebnisse gefunden.")
        return
    cols = st.columns(columns)
    for idx, item in enumerate(items):
        with cols[idx % columns]:
            _render_card(item, favorites)


def _render_favorites_page():
    favorites = st.session_state.favorites

    head_col, back_col, clear_col = st.columns([3, 2, 2])
    with head_col:
        st.header(f"⭐ Favoriten ({len(favorites)})")
    with back_col:
        if st.button("← Zurück zur Suche", use_container_width=True):
            st.session_state.view = "search"
            st.rerun()
    with clear_col:
        if st.button("🗑 Alle löschen", use_container_width=True):
            st.session_state.favorites = {}
            save_favorites({})
            st.rerun()

    if not favorites:
        st.info(
            "Noch keine Favoriten gespeichert. "
            "Markiere Artikel in der Suche mit ☆, um sie hier zu sammeln."
        )
        return

    st.download_button(
        "⬇️ Favoriten als CSV",
        data=items_to_csv(list(favorites.values())),
        file_name="marketsearcher_favoriten.csv",
        mime="text/csv",
    )

    _render_grid(list(favorites.values()), favorites)


def _build_search_term():
    saved_category = _saved("category", "Alle Kategorien")
    if saved_category not in CATEGORIES:
        saved_category = "Alle Kategorien"

    saved_gender = _saved("gender", "")
    gender_options = ("", "male", "female")
    gender_index = (
        gender_options.index(saved_gender) if saved_gender in gender_options else 0
    )

    saved_radius = _saved("radius", 50)
    radius_index = (
        RADIUS_OPTIONS.index(saved_radius)
        if saved_radius in RADIUS_OPTIONS
        else RADIUS_OPTIONS.index(50)
    )

    saved_sort = _saved("sort", "Keine Sortierung")
    sort_index = (
        SORT_OPTIONS.index(saved_sort) if saved_sort in SORT_OPTIONS else 0
    )

    search_term = {}
    search_term["category"] = st.selectbox(
        "Kategorie", CATEGORIES, index=CATEGORIES.index(saved_category)
    )
    search_term["term"] = st.text_input("Suchbegriff", value=_saved("term", ""))

    with st.expander("Erweiterte Filter"):
        col1, col2, col3 = st.columns(3)
        with col1:
            use_vinted = st.checkbox("Vinted", value=_saved("use_vinted", True))
        with col2:
            use_ebay = st.checkbox("eBay", value=_saved("use_ebay", True))
        with col3:
            use_kleinanzeigen = st.checkbox(
                "Kleinanzeigen", value=_saved("use_kleinanzeigen", True)
            )

        is_fashion = search_term["category"] in ("Alle Kategorien", "Mode & Kleidung")

        if is_fashion:
            search_term["gender"] = st.selectbox(
                "Gender", gender_options, index=gender_index
            )
            search_term["size"] = st.multiselect(
                "Größe", ("XS", "S", "M", "L", "XL", "XXL"),
                default=_saved("size", []),
            )
            search_term["condition"] = st.multiselect(
                "Zustand", ("neu", "wie neu", "sehr gut", "gut", "gebraucht"),
                default=_saved("condition", []),
            )
        else:
            search_term["gender"] = ""
            search_term["size"] = []
            search_term["condition"] = []

        sc1, sc2 = st.columns(2)
        search_term["min_price"] = sc1.text_input(
            "Mindestpreis (EUR)", value=_saved("min_price", "")
        )
        search_term["max_price"] = sc2.text_input(
            "Maximalpreis (EUR)", value=_saved("max_price", "")
        )

        search_term["exclude"] = st.text_input(
            "Ausschließen (kommagetrennt, z.B. defekt, Ersatzteile)",
            value=_saved("exclude", ""),
        )

        loc1, loc2 = st.columns(2)
        search_term["zip"] = loc1.text_input(
            "PLZ (optional, nur eBay & Kleinanzeigen)", value=_saved("zip", "")
        )
        search_term["radius"] = loc2.selectbox(
            "Umkreis (km)", RADIUS_OPTIONS, index=radius_index
        )

        if search_term["zip"].strip() and use_vinted:
            st.caption(
                "ℹ️ Der Standortfilter wirkt nicht bei Vinted "
                "(Versand-Marktplatz ohne Standortsuche)."
            )

    return search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_index


def main():
    st.title("Marketsearcher")

    os.environ["EBAY_ENV"] = "production"
    st.caption("🔷 Verwende eBay Production (echte Daten)")

    if "favorites" not in st.session_state:
        st.session_state.favorites = load_favorites()

    if st.session_state.get("view") == "favorites":
        _render_favorites_page()
        return

    fav_col = st.columns([4, 1])[1]
    with fav_col:
        fav_clicked = st.button(
            f"⭐ Favoriten ({len(st.session_state.favorites)})",
            use_container_width=True,
        )

    (
        search_term,
        use_vinted,
        use_ebay,
        use_kleinanzeigen,
        sort_index,
    ) = _build_search_term()

    sort_option = st.selectbox("Sortieren nach", SORT_OPTIONS, index=sort_index)

    if fav_clicked:
        _save_search_state(
            search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_option
        )
        st.session_state.view = "favorites"
        st.rerun()

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

    favorites = st.session_state.favorites

    exclude_words = parse_exclude(search_term.get("exclude"))
    items = filter_by_keywords(st.session_state.result_items, exclude_words)
    items = filter_by_price(items, search_term)
    items = sort_items(items, sort_option)

    st.caption(f"{len(items)} Ergebnisse · Seite {st.session_state.result_page}")

    st.download_button(
        "⬇️ Ergebnisse als CSV",
        data=items_to_csv(items),
        file_name="marketsearcher_ergebnisse.csv",
        mime="text/csv",
    )

    _render_grid(items, favorites)

    if st.session_state.get("no_more"):
        st.caption("Keine weiteren Ergebnisse.")
        return

    if st.button("Mehr laden"):
        next_page = st.session_state.result_page + 1
        new_items, _blocked, errors = run_sources(
            search_term, token, next_page, use_vinted, use_ebay, use_kleinanzeigen
        )
        existing = {item_key(it) for it in st.session_state.result_items}
        added = [it for it in new_items if item_key(it) not in existing]
        st.session_state.result_items += added
        st.session_state.result_page = next_page
        if errors:
            st.session_state.search_errors += errors
        if not added:
            st.session_state.no_more = True
        st.rerun()


if __name__ == "__main__":
    main()
