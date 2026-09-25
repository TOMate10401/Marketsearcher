from concurrent.futures import ThreadPoolExecutor

from .vinted import vinted_scrape
from .ebay import ebay_api_search
from .kleinanzeigen import kleinanzeigen_scraper


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
