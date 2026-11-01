import streamlit as st

from constants import CATEGORIES, RADIUS_OPTIONS


def _default(defaults, key, fallback):
    value = defaults.get(key, fallback)
    return fallback if value is None else value


def build_search_form(defaults=None, form_key=None):
    """Rendert das Suchformular. Liefert (search_term, use_vinted, use_ebay, use_kleinanzeigen).

    defaults: vorbefuellende Werte (z.B. gespeicherte Wunsch-Query oder saved_search).
    form_key: optionaler Prefix fuer Widget-Keys, damit das Formular mehrfach
    auf einer Seite gerendert werden kann.
    """
    defaults = defaults or {}

    def k(name):
        return f"{form_key}_{name}" if form_key else name

    saved_category = _default(defaults, "category", "Alle Kategorien")
    if saved_category not in CATEGORIES:
        saved_category = "Alle Kategorien"

    gender_options = ("", "male", "female")
    saved_gender = _default(defaults, "gender", "")
    gender_index = (
        gender_options.index(saved_gender) if saved_gender in gender_options else 0
    )

    saved_radius = _default(defaults, "radius", 50)
    radius_index = (
        RADIUS_OPTIONS.index(saved_radius)
        if saved_radius in RADIUS_OPTIONS
        else RADIUS_OPTIONS.index(50)
    )

    search_term = {}
    search_term["category"] = st.selectbox(
        "Kategorie", CATEGORIES, index=CATEGORIES.index(saved_category), key=k("category")
    )
    search_term["term"] = st.text_input(
        "Suchbegriff", value=_default(defaults, "term", ""), key=k("term")
    )

    with st.expander("Erweiterte Filter"):
        col1, col2, col3 = st.columns(3)
        with col1:
            use_vinted = st.checkbox(
                "Vinted", value=_default(defaults, "use_vinted", True), key=k("use_vinted")
            )
        with col2:
            use_ebay = st.checkbox(
                "eBay", value=_default(defaults, "use_ebay", True), key=k("use_ebay")
            )
        with col3:
            use_kleinanzeigen = st.checkbox(
                "Kleinanzeigen",
                value=_default(defaults, "use_kleinanzeigen", True),
                key=k("use_kleinanzeigen"),
            )

        is_fashion = search_term["category"] in ("Alle Kategorien", "Mode & Kleidung")

        if is_fashion:
            search_term["gender"] = st.selectbox(
                "Gender", gender_options, index=gender_index, key=k("gender")
            )
            search_term["size"] = st.multiselect(
                "Größe", ("XS", "S", "M", "L", "XL", "XXL"),
                default=_default(defaults, "size", []), key=k("size"),
            )
            search_term["condition"] = st.multiselect(
                "Zustand", ("neu", "wie neu", "sehr gut", "gut", "gebraucht"),
                default=_default(defaults, "condition", []), key=k("condition"),
            )
        else:
            search_term["gender"] = ""
            search_term["size"] = []
            search_term["condition"] = []

        sc1, sc2 = st.columns(2)
        search_term["min_price"] = sc1.text_input(
            "Mindestpreis (EUR)",
            value=_default(defaults, "min_price", ""),
            key=k("min_price"),
        )
        search_term["max_price"] = sc2.text_input(
            "Maximalpreis (EUR)",
            value=_default(defaults, "max_price", ""),
            key=k("max_price"),
        )

        search_term["exclude"] = st.text_input(
            "Ausschließen (kommagetrennt, z.B. defekt, Ersatzteile)",
            value=_default(defaults, "exclude", ""),
            key=k("exclude"),
        )

        search_term["required"] = st.text_input(
            "Muss enthalten (kommagetrennt, z.B. 3080, windforce)",
            value=_default(defaults, "required", ""),
            key=k("required"),
        )
        search_term["required_title_only"] = st.checkbox(
            "Muss enthalten: nur im Titel suchen",
            value=_default(defaults, "required_title_only", False),
            key=k("required_title_only"),
        )

        search_term["hide_defect"] = st.checkbox(
            "Defekte Artikel ausblenden",
            value=_default(defaults, "hide_defect", False),
            help=(
                "Blendet Artikel mit 'defekt', 'Bastler', 'Ersatzteil' etc. aus. "
                "Bei eBay wird zusätzlich das strukturierte Zustandsfeld geprüft."
            ),
            key=k("hide_defect"),
        )

        loc1, loc2 = st.columns(2)
        search_term["zip"] = loc1.text_input(
            "PLZ (optional, nur eBay & Kleinanzeigen)",
            value=_default(defaults, "zip", ""),
            key=k("zip"),
        )
        search_term["radius"] = loc2.selectbox(
            "Umkreis (km)", RADIUS_OPTIONS, index=radius_index, key=k("radius")
        )

        if search_term["zip"].strip() and use_vinted:
            st.caption(
                "ℹ️ Der Standortfilter wirkt nicht bei Vinted "
                "(Versand-Marktplatz ohne Standortsuche)."
            )

    return search_term, use_vinted, use_ebay, use_kleinanzeigen
