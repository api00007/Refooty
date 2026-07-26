from datetime import datetime
import glob
import json
import os
import re
import pytz
import requests

# ফায়ারবেস কনফিগারেশন
FIREBASE_URL = "https://fusion-sports-2c3d2-default-rtdb.firebaseio.com/"
FIREBASE_SECRET = "uogZkbCFyw8CHBurNCZWUeakOOshWKbHf2XlxWKR"


def clean_firebase_key(text):
    """ফায়ারবেসের জন্য নিষিদ্ধ সকল কি-চিহ্ন সম্পূর্ণ ফিল্টার করার ফাংশন"""
    if not text:
        return "clean_key"
    safe = str(text)
    safe = re.sub(r"[\.#\$\[\]/\\]", "", safe)
    return safe.strip()


def sanitize_deep_json(obj):
    """জেসনের প্রতিটি সাব-লেভেলের চাবি (Key) থেকে ডট ও নিষিদ্ধ চিহ্ন মুছে দেওয়ার ডিপ ক্লিনিং"""
    if isinstance(obj, dict):
        cleaned_dict = {}
        for k, v in obj.items():
            safe_k = clean_firebase_key(k)
            if not safe_k:
                safe_k = "key"
            cleaned_dict[safe_k] = sanitize_deep_json(v)
        return cleaned_dict
    elif isinstance(obj, list):
        return [sanitize_deep_json(item) for item in obj]
    else:
        return obj


def upload_matches_to_firebase():
    all_matches = []
    seen_titles = set()

    # ১. সকল পেজ ফাইল বা refooty.json থেকে ডাটা লোড
    page_files = sorted(glob.glob("page_*.json"))
    if not page_files and os.path.exists("refooty.json"):
        page_files = ["refooty.json"]

    if not page_files:
        print("[!] কোনো জেসন বা পেজ ফাইল পাওয়া যায়নি!")
        return

    print(f"[-] মোট {len(page_files)} টি ফাইল থেকে ডাটা রিড করা হচ্ছে...")

    for pf in page_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                content = json.load(f)
                matches = content.get("matches", [])
                if not matches and "latest_matches" in content:
                    matches = content.get("latest_matches", [])

                for m in matches:
                    t = m.get("title")
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        all_matches.append(m)
        except Exception as e:
            print(f"[!] {pf} ফাইল পড়তে সমস্যা: {e}")

    total_count = len(all_matches)
    print(f"[+] সর্বমোট {total_count} টি ম্যাচ ডাটাবেজ প্রসেসিংয়ের জন্য প্রস্তুত।")

    if total_count == 0:
        print("[!] কোনো ম্যাচ পাওয়া যায়নি। আপলোড বাতিল।")
        return

    # ২. ডিপ ফিল্টারিং (জেসনের ভেতর-বাহিরের সব কি ডট ও নিষিদ্ধ চিহ্ন মুক্ত করা)
    print(
        "\n[-] জেসনের ভিতরের ও বাইরের সকল চাবি (Nested Keys) ডট-মুক্ত করা হচ্ছে..."
    )
    firebase_payload = {}

    for m in all_matches:
        title = m.get("title", "")
        match_slug = clean_firebase_key(
            re.sub(r"[\s_-]+", "-", title.lower().strip())
        )

        # পুরো ম্যাচ অবজেক্টের প্রতিটি ডিপ কি ফিল্টার করা
        safe_match_obj = sanitize_deep_json(m)

        if match_slug:
            firebase_payload[match_slug] = safe_match_obj

    print(
        f"[+] সর্বমোট {len(firebase_payload)} টি ম্যাচ ফায়ারবেসের জন্য ১০০% ক্লিন হয়েছে।"
    )

    # ৩. ফায়ারবেসে PATCH আপলোড (SPORTS ও sports_live সম্পূর্ণ নিরাপদ)
    target_endpoint = f"{FIREBASE_URL.rstrip('/')}/Highlights/matches.json?auth={FIREBASE_SECRET}"

    items = list(firebase_payload.items())
    batch_size = 200
    total_batches = (len(items) + batch_size - 1) // batch_size

    print(
        f"\n[-] মোট {total_batches} টি ব্যাচে ফায়ারবেসে আপলোড শুরু হচ্ছে (Batch Size: 200)...\n"
    )

    success_count = 0
    failed_count = 0

    for i in range(total_batches):
        batch_dict = dict(items[i * batch_size : (i + 1) * batch_size])
        try:
            res = requests.patch(
                target_endpoint,
                data=json.dumps(batch_dict, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
                timeout=35,
            )

            if res.status_code == 200:
                success_count += len(batch_dict)
                print(
                    f"  [✓] ব্যাচ {i+1}/{total_batches} আপলোড সফল (প্রসেস হয়েছে {len(batch_dict)} টি ম্যাচ)"
                )
            else:
                failed_count += len(batch_dict)
                print(
                    f"  [!] ব্যাচ {i+1} ফেল মারলো, রেসপন্স কোড: {res.status_code}"
                )

        except Exception as err:
            failed_count += len(batch_dict)
            print(f"  [!] ব্যাচ {i+1} এ নেটওয়ার্ক এরর: {err}")

    print("\n==========================================")
    print(
        f" [SUMMARY] আপলোড সম্পন্ন! সফলভাবে সেভ হয়েছে: {success_count} টি ম্যাচ | ব্যর্থ: {failed_count} টি"
    )
    print("==========================================")


if __name__ == "__main__":
    upload_matches_to_firebase()
