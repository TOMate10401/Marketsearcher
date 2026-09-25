import requests

from constants import HEADERS


def get(url):
    return requests.get(url, headers=HEADERS, timeout=20)
