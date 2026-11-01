import hashlib
import json
import os
import re
from datetime import datetime

import streamlit as st

import db
from checker import (
    STATUS_GONE,
    check_favorites,
    extract_item_id,
    price_changed,
)
from constants import MAX_WISHES, SORT_OPTIONS
from favorites import (
    add_favorite,
    apply_check_result,
    item_key,
    items_to_csv,
    load_favorites,
    remove_favorite,
    remove_gone,
    save_favorites,
)
from filtering import (
    filter_by_keywords,
    filter_by_price,
    filter_by_required,
    filter_out_defective,
    parse_exclude,
    sort_items,
)
from scrapers import get_ebay_token, run_sources
from search_form import build_search_form
from ui_common import fav_button_key, load_image_bytes, render_title_link
from wishlist_ui import DEFAULT_QUERY, render_wish_detail, render_wishlist_page


def _search_signature(search_term, use_vinted, use_ebay, use_kleinanzeigen):
    sig = {
        k: v
        for k, v in search_term.items()
        if k not in ("exclude", "required", "required_title_only", "hide_defect")
    }
    sig["sources"] = [use_vinted, use_ebay, use_kleinanzeigen]
    return json.dumps(sig, sort_keys=True, default=str)


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
        "required": search_term["required"],
        "required_title_only": search_term["required_title_only"],
        "hide_defect": search_term["hide_defect"],
        "zip": search_term["zip"],
        "radius": search_term["radius"],
        "sort": sort_option,
    }


CHECK_CACHE_TTL = 600


def _render_card(item, favorites):
    key = item_key(item)
    is_favorite = key in favorites

    with st.container(border=True):
        img_data = load_image_bytes(item.get("image_url"))
        if img_data:
            st.image(img_data)

        render_title_link(item.get("title"), item.get("link"), star=is_favorite)

        if item.get("distance"):
            st.caption(item["distance"])

        if item.get("price"):
            st.markdown(f"💰 **{item['price']}**")
        if item.get("condition"):
            st.caption(item["condition"])

        if st.button(
            "★" if is_favorite else "☆",
            key=f"fav-{fav_button_key(key)}",
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


def _render_favorite_card(entry, favorites):
    """Karte fuer die Favoriten-Seite mit Verfuegbarkeits-/Preis-Badge."""
    key = item_key(entry)
    is_favorite = key in favorites
    gone = entry.get("check_status") == STATUS_GONE

    with st.container(border=True):
        if gone:
            st.caption("Nicht mehr verfügbar")
        img_data = None if gone else load_image_bytes(entry.get("image_url"))
        if img_data:
            st.image(img_data)

        render_title_link(
            entry.get("title"), entry.get("link") if not gone else "", star=is_favorite
        )

        if entry.get("distance"):
            st.caption(entry["distance"])

        if gone:
            st.markdown(f"~~{entry.get('price', '')}~~")
        else:
            current_price = entry.get("current_price") or ""
            if current_price and price_changed(
                entry.get("price_value"), entry.get("current_price_value")
            ):
                st.markdown(f"💰 **{current_price}**")
                st.caption(f"Zuletzt gespeicherter Preis: {entry.get('price', '')}")
            elif entry.get("price"):
                st.markdown(f"💰 **{entry['price']}**")

        if entry.get("condition"):
            st.caption(entry["condition"])

        if st.button(
            "★" if is_favorite else "☆",
            key=f"fav-{fav_button_key(key)}",
            use_container_width=True,
        ):
            if is_favorite:
                remove_favorite(st.session_state.favorites, entry)
            else:
                add_favorite(
                    st.session_state.favorites,
                    entry,
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


def _run_favorites_check():
    """Prueft alle Favoriten parallel, wenn der Cache abgelaufen ist."""
    favorites = st.session_state.favorites
    if not favorites:
        return

    now = datetime.now()
    checked_at = now.strftime("%Y-%m-%d %H:%M")
    cache_time = st.session_state.get("fav_check_time", {})

    to_check = []
    for key, entry in favorites.items():
        if not entry.get("item_id"):
            entry["item_id"] = extract_item_id(
                entry.get("source"), entry.get("link")
            )
        if (now.timestamp() - cache_time.get(key, 0)) > CHECK_CACHE_TTL:
            to_check.append(entry)

    if not to_check:
        return

    token = st.session_state.get("ebay_token")
    results = check_favorites(to_check, ebay_token=token)

    for key, result in results.items():
        apply_check_result(favorites, key, result, checked_at)
        cache_time[key] = now.timestamp()

    st.session_state.fav_check_time = cache_time
    save_favorites(favorites)


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
        if st.button("Erledigte entfernen", use_container_width=True):
            cleaned, removed = remove_gone(st.session_state.favorites)
            st.session_state.favorites = cleaned
            save_favorites(cleaned)
            st.rerun()

    if not favorites:
        st.info(
            "Noch keine Favoriten gespeichert. "
            "Markiere Artikel in der Suche mit ☆, um sie hier zu sammeln."
        )
        return

    _run_favorites_check()

    gone_count = sum(
        1 for v in favorites.values() if v.get("check_status") == STATUS_GONE
    )
    if gone_count:
        st.caption(
            f"{gone_count} Favoriten sind nicht mehr verfügbar. "
            "Mit 'Erledigte entfernen' kannst du sie aufräumen."
        )

    st.download_button(
        "⬇️ Favoriten als CSV",
        data=items_to_csv(list(favorites.values())),
        file_name="marketsearcher_favoriten.csv",
        mime="text/csv",
    )

    entries = list(st.session_state.favorites.values())
    if not entries:
        st.info("Keine Ergebnisse gefunden.")
        return
    cols = st.columns(3)
    for idx, entry in enumerate(entries):
        with cols[idx % 3]:
            _render_favorite_card(entry, st.session_state.favorites)


def _render_nav(fav_count):
    c1, c2, c3 = st.columns([4, 1, 1])
    with c2:
        if st.button(f"⭐ Favoriten ({fav_count})", use_container_width=True):
            st.session_state.view = "favorites"
            st.rerun()
    with c3:
        if st.button("🎯 Wunschliste", use_container_width=True):
            st.session_state.view = "wishlist"
            st.rerun()


def _save_current_search_as_wish(search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_option):
    conn = st.session_state.db_conn
    if db.wish_count(conn) >= MAX_WISHES:
        st.error(f"Maximal {MAX_WISHES} Wünsche erlaubt.")
        return
    term = search_term["term"].strip()
    name = term or "Wunsch"
    query = {**DEFAULT_QUERY}
    query.update(
        {
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
            "required": search_term["required"],
            "required_title_only": search_term["required_title_only"],
            "hide_defect": search_term["hide_defect"],
            "zip": search_term["zip"],
            "radius": search_term["radius"],
            "sort": sort_option,
        }
    )
    wish_id = db.create_wish(conn, name, query)
    st.session_state.view = "wish_detail"
    st.session_state.wish_id = wish_id
    st.rerun()


def main():
    st.title("Marketsearcher")

    os.environ["EBAY_ENV"] = "production"
    st.caption("🔧 Verwende eBay Production (echte Daten)")

    if "db_conn" not in st.session_state:
        db.init_db()
        st.session_state.db_conn = db.get_conn()
    conn = st.session_state.db_conn

    if "favorites" not in st.session_state:
        st.session_state.favorites = load_favorites()

    view = st.session_state.get("view", "search")
    if view == "favorites":
        _render_favorites_page()
        return
    if view == "wishlist":
        render_wishlist_page(conn)
        return
    if view == "wish_detail":
        render_wish_detail(conn, st.session_state.get("wish_id"))
        return

    _render_nav(len(st.session_state.favorites))

    (
        search_term,
        use_vinted,
        use_ebay,
        use_kleinanzeigen,
    ) = build_search_form(defaults=st.session_state.get("saved_search", {}))

    saved_sort = _saved("sort", "Keine Sortierung")
    sort_index = SORT_OPTIONS.index(saved_sort) if saved_sort in SORT_OPTIONS else 0
    sort_option = st.selectbox("Sortieren nach", SORT_OPTIONS, index=sort_index)

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
    required_words = parse_exclude(search_term.get("required"))
    items = filter_by_keywords(st.session_state.result_items, exclude_words)
    items = filter_by_required(
        items,
        required_words,
        title_only=search_term.get("required_title_only", False),
    )
    items = filter_out_defective(items, search_term.get("hide_defect", False))
    items = filter_by_price(items, search_term)
    items = sort_items(items, sort_option)

    st.caption(f"{len(items)} Ergebnisse · Seite {st.session_state.result_page}")

    dl_col, wish_col = st.columns(2)
    with dl_col:
        st.download_button(
            "⬇️ Ergebnisse als CSV",
            data=items_to_csv(items),
            file_name="marketsearcher_ergebnisse.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with wish_col:
        if st.button(
            "🎯 Als Wunsch speichern", use_container_width=True,
            help=f"Aktuelle Suche als Wunsch speichern (max. {MAX_WISHES})",
        ):
            _save_search_state(
                search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_option
            )
            _save_current_search_as_wish(
                search_term, use_vinted, use_ebay, use_kleinanzeigen, sort_option
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
