from datetime import datetime
import json
import re
import pytz
import requests

FIREBASE_URL = "https://fusion-sports-2c3d2-default-rtdb.firebaseio.com/"
FIREBASE_SECRET = "uogZkbCFyw8CHBurNCZWUeakOOshWKbHf2XlxWKR"


def parse_date_safe(date_str):
    if not date_str:
        return datetime(1970, 1, 1)
    clean_d = date_str.strip()
    formats = [
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_d, fmt)
        except ValueError:
            pass
    return datetime(1970, 1, 1)


def sanitize_firebase_key(text):
    if not text:
        return "match"
    text = text.lower().strip()
    text = re.sub(r"[\.#\$\[\]/\\]", "", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def sort_and_update_firebase():
    endpoint = f"{FIREBASE_URL.rstrip('/')}/Highlights/matches.json?auth={FIREBASE_SECRET}"

    try:
        res = requests.get(endpoint, timeout=30)
        res.encoding = "utf-8"

        if res.status_code != 200:
            return

        raw_data = res.json()
        if not raw_data:
            return

        matches_list = list(raw_data.values())

        matches_list.sort(
            key=lambda m: parse_date_safe(m.get("date", "")), reverse=True
        )

        ordered_payload = {}
        for idx, m in enumerate(matches_list, 1):
            title = m.get("title", "match")
            safe_slug = sanitize_firebase_key(title)
            order_key = f"{idx:04d}_{safe_slug}"
            ordered_payload[order_key] = m

        items = list(ordered_payload.items())
        batch_size = 200
        total_batches = (len(items) + batch_size - 1) // batch_size

        requests.delete(endpoint, timeout=30)

        for i in range(total_batches):
            batch_dict = dict(items[i * batch_size : (i + 1) * batch_size])
            patch_endpoint = f"{FIREBASE_URL.rstrip('/')}/Highlights/matches.json?auth={FIREBASE_SECRET}"
            requests.patch(
                patch_endpoint,
                data=json.dumps(batch_dict, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
                timeout=35,
            )

    except Exception:
        pass


if __name__ == "__main__":
    sort_and_update_firebase()
