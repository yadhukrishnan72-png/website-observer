"""Fetch a page. Never raises: returns (status, html, error)."""
import requests

HEADERS = {"User-Agent": "DailyWebsiteObserver/0.1 (pilot; ABM trigger research)"}


def fetch(url, timeout=10, retries=1):
    last_error = None
    for _ in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.status_code, resp.text, None
            last_error = f"HTTP {resp.status_code}"
            status = resp.status_code
        except requests.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            status = None
    return status, None, last_error
