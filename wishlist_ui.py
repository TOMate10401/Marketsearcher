import os
from datetime import datetime

import streamlit as st

import db
from checker import STATUS_GONE, price_changed
from constants import (
    MAX_MARKED_PER_WISH,
    MAX_WISHES,
    SORT_OPTIONS,
    STATUS_HIDDEN,
    STATUS_MARKED,
    STATUS_NEW,
)
from favorites import add_favorite, item_key, load_favorites, remove_favorite, save_favorites
from filtering import (
    filter_by_keywords,
    filter_by_price,
    filter_by_required,
    filter_out_defective,
    parse_exclude,
    sort_items,
)
from daily_run import run_wish
from scrapers import get_ebay_token
from search_form import build_search_form
from ui_common import fav_button_key, load_image_bytes, render_title_link

EXPORT_DIR = os.environ.get("EXPORT_DIR", "data/exports")

DEFAULT_QUERY = {
    "category": "Alle Kategorien",
    "term": "",
    "use_vinted": True,
    "use_ebay": True,
    "use_kleinanzeigen": True,
    "gender": "",
    "size": [],
    "condition": [],
    "min_price": "",
    "max_price": "",
    "exclude": "",
    "required": "",
    "required_title_only": False,
    "hide_defect": False,
    "zip": "",
    "radius": 50,
    "sort": "Keine Sortierung",
}


def _item_db_key(item):
    return f"{item['source']}|{item['item_id']}"


def _wish_button_key(wish_id, action, item):
    return f"w{wish_id}-{action}-{_item_db_key(item)}"


def _render_item_card(conn, wish, item, favorites):
    key = item_key(item)
    is_favorite = key in favorites
    is_marked = item.get("status") == STATUS_MARKED
    gone = is_marked and item.get("check_status") == STATUS_GONE

    with st.container(border=True):
        if gone:
            st.caption("Nicht mehr verfügbar")
        img = None if gone else load_image_bytes(item.get("image_url"))
        if img:
            st.image(img)

        render_title_link(item.get("title"), item.get("link") if not gone else "", star=is_favorite)

        if item.get("distance"):
            st.caption(item["distance"])

        if gone:
            st.markdown(f"~~{item.get('price', '')}~~")
        else:
            current_price = item.get("current_price") or ""
            if (
                is_marked
                and current_price
                and price_changed(item.get("price_value"), item.get("current_price_value"))
            ):
                st.markdown(f"💰 **{current_price}**")
                st.caption(f"Zuletzt gespeicherter Preis: {item.get('price', '')}")
            elif item.get("price"):
                st.markdown(f"💰 **{item['price']}**")

        if item.get("condition"):
            st.caption(item["condition"])

        wish_id = wish["id"]
        b1, b2, b3 = st.columns(3)
        with b1:
            label = "⭐" if is_marked else "☆"
            if st.button(label, key=_wish_button_key(wish_id, "mark", item),
                         use_container_width=True,
                         help="Markieren (max. %d pro Wunsch)" % MAX_MARKED_PER_WISH):
                try:
                    db.set_item_status(
                        conn, wish_id, item["source"], item["item_id"],
                        STATUS_NEW if is_marked else STATUS_MARKED,
                    )
                except ValueError as e:
                    st.error(str(e))
                st.rerun()
        with b2:
            if item.get("status") == STATUS_HIDDEN:
                if st.button("↩️", key=_wish_button_key(wish_id, "unhide", item),
                             use_container_width=True, help="Wieder einblenden"):
                    db.set_item_status(conn, wish_id, item["source"], item["item_id"], STATUS_NEW)
                    st.rerun()
            else:
                if st.button("👁️", key=_wish_button_key(wish_id, "hide", item),
                             use_container_width=True, help="Ausblenden (nur dieser Wunsch)"):
                    db.set_item_status(conn, wish_id, item["source"], item["item_id"], STATUS_HIDDEN)
                    st.rerun()
        with b3:
            if st.button("★" if is_favorite else "☆",
                         key=f"fav-{fav_button_key(key)}",
                         use_container_width=True, help="Favorit (global)"):
                if is_favorite:
                    remove_favorite(st.session_state.favorites, item)
                else:
                    add_favorite(
                        st.session_state.favorites, item,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                    )
                save_favorites(st.session_state.favorites)
                st.rerun()


def _apply_query_filters(items, query):
    exclude_words = parse_exclude(query.get("exclude"))
    required_words = parse_exclude(query.get("required"))
    items = filter_by_keywords(items, exclude_words)
    items = filter_by_required(
        items, required_words, title_only=query.get("required_title_only", False)
    )
    items = filter_out_defective(items, query.get("hide_defect", False))
    items = filter_by_price(items, query)
    return items


def render_wish_detail(conn, wish_id):
    wish = db.get_wish(conn, wish_id)
    if not wish:
        st.session_state.view = "wishlist"
        st.rerun()
        return

    head_col, back_col = st.columns([4, 1])
    with head_col:
        st.header(f"🎯 {wish['name']}")
    with back_col:
        if st.button("← Zurück", use_container_width=True):
            st.session_state.view = "wishlist"
            st.rerun()

    if wish.get("last_run_at"):
        st.caption(f"Letzter Lauf: {wish['last_run_at']} — {wish.get('last_run_status') or ''}")

    run_col, hint_col = st.columns([2, 3])
    with run_col:
        manual_run = st.button("🔎 Jetzt suchen", key="wish-manual-run")
    with hint_col:
        st.caption(
            "ℹ️ Eigentlich nicht nötig: Diese Suche läuft automatisch einmal "
            "täglich (cron auf dem Pi). Manuell nur zum Testen gedacht."
        )
    if manual_run:
        token = st.session_state.get("ebay_token")
        if wish["query"].get("use_ebay", True) and not token:
            token = get_ebay_token()
            st.session_state.ebay_token = token
        with st.spinner("Suche läuft (Seite 1–3 + Verfügbarkeitscheck der markierten) ..."):
            run_wish(conn, wish, token)
        st.rerun()

    with st.expander("🔍 Suchanfrage bearbeiten", expanded=False):
        query_defaults = {**DEFAULT_QUERY, **wish["query"]}
        search_term, use_vinted, use_ebay, use_kleinanzeigen = build_search_form(
            defaults=query_defaults, form_key="wish"
        )
        if st.button("💾 Suchanfrage speichern", key="wish-save-query"):
            query = {
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
                "sort": wish["query"].get("sort", "Keine Sortierung"),
            }
            db.update_wish_query(conn, wish_id, query)
            st.success("Suchanfrage gespeichert.")
            st.rerun()

    query = {**DEFAULT_QUERY, **wish["query"]}

    counts = db.item_counts(conn, wish_id)
    toggle_col, sort_col, csv_col = st.columns([3, 2, 2])
    with toggle_col:
        show_marked = st.checkbox("⭐ Markiert", value=True, key="show-marked")
        show_new = st.checkbox("🆕 Unbewertet", value=True, key="show-new")
        show_hidden = st.checkbox("👁️ Ausgeblendet", value=False, key="show-hidden")
    with sort_col:
        saved_sort = query.get("sort", "Keine Sortierung")
        sort_index = SORT_OPTIONS.index(saved_sort) if saved_sort in SORT_OPTIONS else 0
        sort_option = st.selectbox("Sortieren nach", SORT_OPTIONS, index=sort_index, key="wish-sort")
    with csv_col:
        st.write("")
        csv_data = db.export_csv(conn, wish_id)
        st.download_button(
            "⬇️ CSV", data=csv_data,
            file_name=f"wunsch_{wish_id}.csv", mime="text/csv",
            use_container_width=True,
        )
        if st.button("💾 CSV auf Server", use_container_width=True, key="wish-csv-server"):
            os.makedirs(EXPORT_DIR, exist_ok=True)
            path = os.path.join(EXPORT_DIR, f"wunsch_{wish_id}_{datetime.now():%Y%m%d}.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(csv_data)
            st.success(f"Gespeichert: {path}")

    statuses = []
    if show_marked:
        statuses.append(STATUS_MARKED)
    if show_new:
        statuses.append(STATUS_NEW)
    if show_hidden:
        statuses.append(STATUS_HIDDEN)
    items = db.get_items(conn, wish_id, statuses=statuses or None)

    if show_marked:
        gone_count = sum(
            1 for it in items if it.get("status") == STATUS_MARKED and it.get("check_status") == STATUS_GONE
        )
        if gone_count:
            if st.button(f"🧹 {gone_count} nicht mehr verfügbare entfernen", key="wish-clear-gone"):
                removed = db.remove_gone_marked(conn, wish_id)
                st.success(f"{removed} entfernt.")
                st.rerun()

    items = _apply_query_filters(items, query)
    items = sort_items(items, sort_option)

    st.caption(f"{len(items)} Artikel · unbewertet {counts.get(STATUS_NEW, 0)} · "
               f"markiert {counts.get(STATUS_MARKED, 0)}/{MAX_MARKED_PER_WISH} · "
               f"ausgeblendet {counts.get(STATUS_HIDDEN, 0)}")

    if not items:
        st.info("Keine Artikel in dieser Ansicht.")
        return

    favorites = st.session_state.favorites
    cols = st.columns(3)
    for idx, item in enumerate(items):
        with cols[idx % 3]:
            _render_item_card(conn, wish, item, favorites)


def render_wishlist_page(conn):
    st.header("🎯 Wunschliste")

    wishes = db.list_wishes(conn)

    if st.button("➕ Neuer Wunsch", disabled=len(wishes) >= MAX_WISHES,
                 help=f"Maximal {MAX_WISHES} Wuensche" if len(wishes) >= MAX_WISHES else None):
        name = f"Wunsch {len(wishes) + 1}"
        wish_id = db.create_wish(conn, name, dict(DEFAULT_QUERY))
        st.session_state.view = "wish_detail"
        st.session_state.wish_id = wish_id
        st.rerun()

    if not wishes:
        st.info("Noch keine Wuensche. Lege mit '➕ Neuer Wunsch' einen an "
                "oder speichere eine Suche direkt als Wunsch.")
        return

    for w in wishes:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                if st.button(f"🎯 **{w['name']}** — {w['query'].get('term') or '(kein Begriff)'} "
                             f"({w['total']} Artikel)", key=f"open-{w['id']}", use_container_width=True):
                    st.session_state.view = "wish_detail"
                    st.session_state.wish_id = w["id"]
                    st.rerun()
                st.caption(
                    f"🆕 {w['cnt_new']} unbewertet · ⭐ {w['cnt_marked']} markiert"
                    + (f" ({w['cnt_gone']} nicht mehr verfügbar)" if w["cnt_gone"] else "")
                    + f" · 👁️ {w['cnt_hidden']} ausgeblendet"
                    + (f" · letzter Lauf: {w['last_run_at']} — {w['last_run_status']}"
                       if w.get("last_run_at") else " · noch kein Lauf")
                )
            with c2:
                with st.expander("⚙️"):
                    new_name = st.text_input("Name", value=w["name"], key=f"rename-{w['id']}")
                    if st.button("Umbenennen", key=f"do-rename-{w['id']}", use_container_width=True):
                        if new_name.strip():
                            db.rename_wish(conn, w["id"], new_name)
                            st.rerun()
                    if st.button("🗑️ Löschen", key=f"del-{w['id']}", use_container_width=True):
                        db.delete_wish(conn, w["id"])
                        st.rerun()
