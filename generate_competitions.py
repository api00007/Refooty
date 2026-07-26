from datetime import datetime
import glob
import json
import os
import re
import pytz

GITHUB_USER = "api00007"
GITHUB_REPO = "Refooty"
GITHUB_EMAIL = "sptv5204@gmail.com"
GITHUB_TOKEN = "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"  # <--- আপনার আসল গিটহাব PAT টোকেনটি বসাবেন


def get_ist_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S IST")


def slugify(text):
    """লিগের নাম দিয়ে ইউআরএল ফ্রেন্ডলি ফাইল নেম তৈরি করা"""
    if not text:
        return "unknown-competition"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def push_to_github():
    print("\n[-] গিটহাবে কম্পিটিশন ফাইলগুলো পুশ করা হচ্ছে...")
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        os.system(f'git config --global user.email "{GITHUB_EMAIL}"')
        os.system(f'git config --global user.name "{GITHUB_USER}"')
        os.system(f"git remote set-url origin {remote_url}")

        os.system("git add competitions.json competitions/*.json")
        os.system(
            f'git commit -m "Competitions API generated: {get_ist_time()}"'
        )
        os.system("git push origin main")

        print("\n[SUCCESS] ১০০% সফলতা! সকল কম্পিটিশন ফাইল গিটহাবে আপলোড হয়ে গেছে!")
    except Exception as e:
        print(f"[ERROR] পুশ ব্যর্থ: {e}")


def build_competitions_api():
    all_matches = []
    seen_titles = set()

    # ১. সকল page_*.json ফাইল থেকে সব ম্যাচের ডাটা একসাথে করা
    page_files = sorted(glob.glob("page_*.json"))

    if not page_files and os.path.exists("refooty.json"):
        page_files = ["refooty.json"]

        if not page_files:
            print("[!] কোনো পেজ বা জেসন ফাইল পাওয়া যায়নি!")
            return

    print(f"[-] মোট {len(page_files)} টি পেজ ফাইল থেকে ম্যাচের ডাটা রিড করা হচ্ছে...")

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

    print(f"[+] সর্বমোট {len(all_matches)} টি অনন্য ম্যাচ একত্রিত হয়েছে।")

    # ২. কম্পিটিশন/লিগ অনুযায়ী ফিল্টার করা
    comp_grouped = {}
    for m in all_matches:
        comp_name = m.get("competition", "Other Leagues").strip()
        if not comp_name:
            comp_name = "Other Leagues"

        if comp_name not in comp_grouped:
            comp_grouped[comp_name] = {
                "cover": m.get("competition_cover", ""),
                "matches": [],
            }

        comp_grouped[comp_name]["matches"].append(m)

    # ৩. 'competitions' ফোল্ডার তৈরি করা
    output_dir = "competitions"
    os.makedirs(output_dir, exist_ok=True)

    comp_master_list = []

    print(f"\n[-] মোট {len(comp_grouped)} টি লিগের আলাদা জেসন ফাইল তৈরি হচ্ছে...")

    for comp_name, comp_info in comp_grouped.items():
        slug = slugify(comp_name)
        filename = f"{slug}.json"
        filepath = os.path.join(output_dir, filename)

        # প্রতিটি লিগের জেসন প্যাকেজ (হুবহু আগের কাস্টম স্ট্রাকচার অটুট থাকবে)
        comp_data = {
            "competition": comp_name,
            "competition_cover": comp_info["cover"],
            "total_matches": len(comp_info["matches"]),
            "matches": comp_info["matches"],
        }

        with open(filepath, "w", encoding="utf-8") as cf:
            json.dump(comp_data, cf, indent=4, ensure_ascii=False)

        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/competitions/{filename}"

        comp_master_list.append(
            {
                "name": comp_name,
                "slug": slug,
                "cover_image": comp_info["cover"],
                "total_matches": len(comp_info["matches"]),
                "json_url": raw_url,
            }
        )

        print(f"  [✓] তৈরি হয়েছে: {filepath} ({len(comp_info['matches'])} টি ম্যাচ)")

    # ৪. মাস্টার competitions.json ফাইল তৈরি
    master_package = {
        "Owner": GITHUB_USER,
        "App_name": "ReFooty Competitions Master API",
        "Last_update": get_ist_time(),
        "Total_Competitions": len(comp_master_list),
        "competitions": comp_master_list,
    }

    with open("competitions.json", "w", encoding="utf-8") as mf:
        json.dump(master_package, mf, indent=4, ensure_ascii=False)

    print(f"\n[+] মেইন competitions.json তৈরি হয়েছে! মোট লিগ: {len(comp_master_list)}")

    # ৫. গিটহাবে পুশ
    push_to_github()


if __name__ == "__main__":
    build_competitions_api()
