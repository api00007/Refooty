from datetime import datetime
import json
import os
import pytz

INPUT_FILE = "refooty.json"

GITHUB_USER = "api00007"
GITHUB_REPO = "Refooty"
GITHUB_EMAIL = "sptv5204@gmail.com"
GITHUB_TOKEN = "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"  # <--- আপনার অরিজিনাল গিটহাব PAT টোকেনটি এখানে বসাবেন


def get_ist_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S IST")


def push_all_to_github():
    print("\n[-] গিটহাবে নতুন পেজ ফাইলগুলো পুশ করা হচ্ছে...")
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        os.system(f'git config --global user.email "{GITHUB_EMAIL}"')
        os.system(f'git config --global user.name "{GITHUB_USER}"')
        os.system(f"git remote set-url origin {remote_url}")

        # সকল পেজ ফাইল এবং মেইন ফাইল যুক্ত করা
        os.system("git add page_*.json refooty.json")
        os.system(
            f'git commit -m "Page system updated (100 matches/page): {get_ist_time()}"'
        )
        os.system("git push origin main")

        print("\n[SUCCESS] ১০০% সফলতা! সকল পেজ ফাইল গিটহাবে পুশ হয়ে গেছে!")
    except Exception as e:
        print(f"[ERROR] পুশ ব্যর্থ: {e}")


def split_matches_into_pages():
    if not os.path.exists(INPUT_FILE):
        print(f"[!] {INPUT_FILE} ফাইলটি পাওয়া যায়নি!")
        return

    print(f"[-] {INPUT_FILE} ফাইল রিড করা হচ্ছে...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_matches = data.get("matches", [])
    total_matches = len(all_matches)

    if total_matches == 0:
        print("[!] ফাইলে কোনো ম্যাচের ডাটা নেই!")
        return

    print(f"[+] মোট {total_matches} টি ম্যাচ পাওয়া গেছে।")
    print("[-] প্রতি ফাইলে ১০০টি করে ম্যাচ ভাগ করা হচ্ছে...")

    chunk_size = 100
    page_files_list = []
    total_pages = (total_matches + chunk_size - 1) // chunk_size

    # ১০০টি করে ম্যাচ ভাগ করে page_X.json ফাইল তৈরি
    for page_num in range(1, total_pages + 1):
        start_idx = (page_num - 1) * chunk_size
        end_idx = start_idx + chunk_size
        matches_chunk = all_matches[start_idx:end_idx]

        page_filename = f"page_{page_num}.json"

        page_package = {
            "page": page_num,
            "total_pages": total_pages,
            "matches_in_this_page": len(matches_chunk),
            "matches": matches_chunk,
        }

        with open(page_filename, "w", encoding="utf-8") as pf:
            json.dump(page_package, pf, indent=4, ensure_ascii=False)

        page_files_list.append(page_filename)
        print(f"  [✓] তৈরি হয়েছে: {page_filename} ({len(matches_chunk)} টি ম্যাচ)")

    # মেইন refooty.json আপডেট করা (এতে পেজগুলোর লিঙ্ক এবং নতুন ১০০টি ম্যাচ থাকবে)
    main_package = {
        "Owner": GITHUB_USER,
        "Telegram": "https://t.me/iVan_flux",
        "App_name": "ReFooty Paginated Auto API",
        "Last_update": get_ist_time(),
        "Total_Matches": total_matches,
        "Total_Pages": total_pages,
        "Page_Size": chunk_size,
        "Page_Links": [
            f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{p}"
            for p in page_files_list
        ],
        "latest_matches": all_matches[:100],  # সাম্প্রতিক ১০০টি ম্যাচ
    }

    with open(INPUT_FILE, "w", encoding="utf-8") as mf:
        json.dump(main_package, mf, indent=4, ensure_ascii=False)

    print(f"\n[+] মেইন {INPUT_FILE} আপডেট করা হয়েছে।")

    # গিটহাবে পুশ করা
    push_all_to_github()


if __name__ == "__main__":
    split_matches_into_pages()
