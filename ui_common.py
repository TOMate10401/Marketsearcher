import hashlib
from io import BytesIO

import requests
import streamlit as st

from constants import HEADERS


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_image_bytes(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except requests.RequestException:
        pass
    return None


def load_image_bytes(url):
    if not url:
        return None
    data = _fetch_image_bytes(url)
    return BytesIO(data) if data else None


def fav_button_key(key):
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def render_title_link(title, link, star=False):
    title = (title or "").strip() or "(ohne Titel)"
    safe_title = title.replace("[", "(").replace("]", ")")
    title_str = f"{'\u2b50 ' if star else ''}{safe_title}"
    if link:
        st.markdown(f"**[{title_str}]({link})**")
    else:
        st.markdown(f"**{title_str}**")
