"""Taeglicher Lauf ueber alle Wuensche: Suche ausfuehren, Ergebnisse mergen,
markierte Artikel auf Verfuegbarkeit/Preis pruefen.

Aufruf auf dem Pi per cron/systemd-Timer, z.B.:
    0 8 * * * cd /pfad/zum/repo && /usr/bin/python3 daily_run.py >> daily_run.log 2>&1
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_env
from constants import MAX_PAGES_PER_RUN, STATUS_MARKED
import db
from checker import check_favorites
from scrapers import get_ebay_token, run_sources

RUN_DELAY_SECONDS = float(os.environ.get("DAILY_RUN_DELAY", "5"))


def run_wish(conn, wish, ebay_token):
    query = dict(wish["query"])
    query.setdefault("term", "")
    query.setdefault("category", "Alle Kategorien")
    sources = [
        query.get(k, True) for k in ("use_vinted", "use_ebay", "use_kleinanzeigen")
    ]
    if not any(sources):
        db.finish_run(conn, wish["id"], "keine Quellen aktiv")
        return

    found = []
    errors = []
    vinted_blocked = False
    for page in range(1, MAX_PAGES_PER_RUN + 1):
        items, blocked, page_errors = run_sources(
            query, ebay_token, page, *sources
        )
        found.extend(items)
        errors.extend(page_errors)
        vinted_blocked = vinted_blocked or blocked
        if not items:
            break
        time.sleep(RUN_DELAY_SECONDS)

    added, updated, removed = db.merge_run(conn, wish["id"], found)

    marked = db.get_items(conn, wish["id"], statuses=[STATUS_MARKED])
    entries = [
        {"source": it["source"], "link": it.get("link") or ""} for it in marked
    ]
    if entries:
        results = check_favorites(entries, ebay_token=ebay_token)
        for it in marked:
            key = f"{it['source']}|{it.get('link') or it.get('title')}"
            if key in results:
                db.apply_check_result(
                    conn, wish["id"], it["source"], it["item_id"], results[key]
                )

    status_parts = [f"+{added} neu, {updated} aktualisiert, {removed} entfernt"]
    if vinted_blocked:
        status_parts.append("Vinted blockiert")
    for err in errors[:3]:
        status_parts.append(err[:80])
    db.finish_run(conn, wish["id"], "; ".join(status_parts))


def main():
    load_env()
    db.init_db()
    conn = db.get_conn()
    wishes = db.list_wishes(conn)
    if not wishes:
        print("Keine Wuensche gespeichert.")
        return

    token = None
    if any(w["query"].get("use_ebay", True) for w in wishes):
        token = get_ebay_token()
        if not token:
            print("WARNUNG: eBay-Token konnte nicht erzeugt werden (.env pruefen).")

    for wish in wishes:
        print(f"[{wish['id']}] {wish['name']} ...")
        try:
            run_wish(conn, wish, token)
        except Exception as exc:
            db.finish_run(conn, wish["id"], f"Fehler: {exc}")
            print(f"  Fehler: {exc}")
        time.sleep(RUN_DELAY_SECONDS)
    conn.close()


if __name__ == "__main__":
    main()
