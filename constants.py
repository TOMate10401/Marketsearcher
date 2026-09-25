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
