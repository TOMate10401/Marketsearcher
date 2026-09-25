import json
import os
import re
from datetime import datetime
from io import BytesIO

import requests
import streamlit as st

from config import load_env
from constants import CATEGORIES, HEADERS
from filtering import (
    filter_by_keywords,
    filter_by_price,
    parse_exclude,
    sort_items,
)
from favorites import (
    add_favorite,
    item_key,
    items_to_csv,
    load_favorites,
    remove_favorite,
    save_favorites,
)
from scrapers import get_ebay_token, run_sources


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

        meta = [item.get("source", "")]
        if item.get("distance"):
            meta.append(item["distance"])
        st.caption(" · ".join(m for m in meta if m))

        if item.get("price"):
            st.markdown(f"💰 **{item['price']}**")
        if item.get("condition"):
            st.caption(f"Zustand: {item['condition']}")

        col_link, col_fav = st.columns([3, 1])
        with col_link:
            if link:
                st.markdown(f"[🔗 Link]({link})")
        with col_fav:
            fav_label = "★" if is_favorite else "☆"
            if st.button(fav_label, key=f"fav-{abs(hash(key))}", use_container_width=True):
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


def main():
    st.title("Marketsearcher")

    os.environ["EBAY_ENV"] = "production"
    st.caption("🔷 Verwende eBay Production (echte Daten)")

    if "favorites" not in st.session_state:
        st.session_state.favorites = load_favorites()

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
        search_term["gender"] = st.selectbox("Gender", ("", "male", "female"))
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

    favorites = st.session_state.favorites

    with st.sidebar:
        st.subheader(f"⭐ Favoriten ({len(favorites)})")
        show_favorites = st.checkbox("Nur Favoriten anzeigen")
        if st.checkbox("Alle Favoriten löschen"):
            st.session_state.favorites = {}
            save_favorites({})
            st.rerun()

    exclude_words = parse_exclude(search_term.get("exclude"))
    items = st.session_state.result_items
    if show_favorites:
        items = [it for it in items if item_key(it) in favorites]
    items = filter_by_keywords(items, exclude_words)
    items = filter_by_price(items, search_term)
    items = sort_items(items, sort_option)

    st.caption(f"{len(items)} Ergebnisse · Seite {st.session_state.result_page}")

    exp1, exp2 = st.columns(2)
    with exp1:
        st.download_button(
            "⬇️ Ergebnisse als CSV",
            data=items_to_csv(items),
            file_name="marketsearcher_ergebnisse.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with exp2:
        st.download_button(
            "⬇️ Favoriten als CSV",
            data=items_to_csv(list(favorites.values())),
            file_name="marketsearcher_favoriten.csv",
            mime="text/csv",
            use_container_width=True,
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
