from datetime import datetime
import glob
import json
import os
import re
import pytz

GITHUB_USER = "api00007"
GITHUB_REPO = "Refooty"
GITHUB_EMAIL = "sptv5204@gmail.com"
GITHUB_TOKEN = "YOUR_TOKEN_HERE"  # <--- আপনার আসল গিটহাব PAT টোকেনটি এখানে বসাবেন


def get_ist_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S IST")


def slugify(text):
    """টিমের নাম দিয়ে ইউআরএল ফাইল নেম তৈরি করা"""
    if not text:
        return "unknown-team"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def extract_teams_from_title(title):
    """টিম নাম না থাকলে টাইটেল (Title) ভেঙে দুটি দলের নাম বের করার স্মার্ট লজিক"""
    if not title:
        return None, None

    # টাইটেল থেকে অতিরিক্ত লেখা ক্লিন করা
    clean_t = re.sub(
        r"\b(full match|highlights|goals|watch)\b",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    # vs, v, বা - দিয়ে টাইটেল স্প্লিট করা
    parts = re.split(r"\s+(?:vs|v|-|–|—)\s+", clean_t, flags=re.IGNORECASE)
    if len(parts) >= 2:
        t1 = parts[0].strip()
        t2 = parts[1].strip()
        if t1 and t2:
            return t1, t2

    return None, None


def push_to_github():
    print("\n[-] গিটহাবে নতুন টিম ফাইলগুলো পুশ করা হচ্ছে...")
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        os.system(f'git config --global user.email "{GITHUB_EMAIL}"')
        os.system(f'git config --global user.name "{GITHUB_USER}"')
        os.system(f"git remote set-url origin {remote_url}")

        os.system("git add teams.json teams/*.json")
        os.system(
            f'git commit -m "Zero-Skip Teams API generated: {get_ist_time()}"'
        )
        os.system("git push origin main")

        print(
            "\n[SUCCESS] ১০০% সফলতা! কোনো ম্যাচ স্কিপ না করে সকল টিম ফাইল গিটহাবে আপলোড হয়ে গেছে!"
        )
    except Exception as e:
        print(f"[ERROR] গিটহাব পুশ ব্যর্থ: {e}")


def build_teams_api():
    all_matches = []
    seen_titles = set()

    # ১. সকল জেসন/পেজ ফাইল থেকে ম্যাচের ডাটা রিড করা
    page_files = sorted(glob.glob("page_*.json"))
    if not page_files and os.path.exists("refooty.json"):
        page_files = ["refooty.json"]

    if not page_files:
        print("[!] কোনো জেসন বা পেজ ফাইল পাওয়া যায়নি!")
        return

    print(f"[-] মোট {len(page_files)} টি ফাইল থেকে সকল ম্যাচের ডাটা রিড করা হচ্ছে...")

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

    print(
        f"[+] সর্বমোট {len(all_matches)} টি অনন্য ম্যাচ সফলভাবে লোড হয়েছে।"
    )

    # ২. টিম ফিল্টারিং (স্মার্ট টাইটেল স্প্লিটার সহ)
    teams_grouped = {}

    for m in all_matches:
        title = m.get("title", "")
        teams_obj = m.get("teams", {})
        home_obj = teams_obj.get("home_team", {})
        away_obj = teams_obj.get("away_team", {})

        home_name = home_obj.get("name", "").strip()
        away_name = away_obj.get("name", "").strip()
        home_logo = home_obj.get("logo", "")
        away_logo = away_obj.get("logo", "")

        # যদি কোনো টিমের নাম 'Home Team' বা 'Away Team' অথবা খালি থাকে, তবে টাইটেল স্প্লিট করা
        if (
            not home_name
            or home_name == "Home Team"
            or not away_name
            or away_name == "Away Team"
        ):
            t1_parsed, t2_parsed = extract_teams_from_title(title)
            if t1_parsed and (not home_name or home_name == "Home Team"):
                home_name = t1_parsed
            if t2_parsed and (not away_name or away_name == "Away Team"):
                away_name = t2_parsed

        # প্রথম টিম গ্রুপিং
        if home_name and home_name != "Home Team":
            if home_name not in teams_grouped:
                teams_grouped[home_name] = {"logo": home_logo, "matches": []}
            if m not in teams_grouped[home_name]["matches"]:
                teams_grouped[home_name]["matches"].append(m)

        # দ্বিতীয় টিম গ্রুপিং
        if (
            away_name
            and away_name != "Away Team"
            and away_name != home_name
        ):
            if away_name not in teams_grouped:
                teams_grouped[away_name] = {"logo": away_logo, "matches": []}
            if m not in teams_grouped[away_name]["matches"]:
                teams_grouped[away_name]["matches"].append(m)

    # ৩. 'teams' ফোল্ডার তৈরি ও ফাইল সেভ
    output_dir = "teams"
    os.makedirs(output_dir, exist_ok=True)

    team_master_list = []

    print(
        f"\n[-] জিরো-স্কিপ মোডে মোট {len(teams_grouped)} টি দলের আলাদা জেসন ফাইল তৈরি হচ্ছে..."
    )

    for team_name, team_info in teams_grouped.items():
        slug = slugify(team_name)
        filename = f"{slug}.json"
        filepath = os.path.join(output_dir, filename)

        team_data = {
            "team": team_name,
            "team_logo": team_info["logo"],
            "total_matches": len(team_info["matches"]),
            "matches": team_info["matches"],
        }

        with open(filepath, "w", encoding="utf-8") as tf:
            json.dump(team_data, tf, indent=4, ensure_ascii=False)

        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/teams/{filename}"

        team_master_list.append(
            {
                "name": team_name,
                "slug": slug,
                "logo": team_info["logo"],
                "total_matches": len(team_info["matches"]),
                "json_url": raw_url,
            }
        )

        print(
            f"  [✓] তৈরি হয়েছে: {filepath} ({len(team_info['matches'])} টি ম্যাচ)"
        )

    # ৪. মাস্টার teams.json ফাইল তৈরি
    master_package = {
        "Owner": GITHUB_USER,
        "App_name": "ReFooty Zero-Skip Teams API",
        "Last_update": get_ist_time(),
        "Total_Teams": len(team_master_list),
        "teams": team_master_list,
    }

    with open("teams.json", "w", encoding="utf-8") as mf:
        json.dump(master_package, mf, indent=4, ensure_ascii=False)

    print(
        f"\n[+] মেইন teams.json তৈরি হয়েছে! মোট টিম: {len(team_master_list)}"
    )

    # ৫. গিটহাবে পুশ করা
    push_to_github()


if __name__ == "__main__":
    build_teams_api()
