from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pytz
import requests

BASE_URL = "https://refooty.com"
OUTPUT_FILE = "refooty.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}


def get_ist_time():
    """ভারতীয়/বাংলাদেশী সময় অনুযায়ী আপডেট টাইম বের করা"""
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S IST")


def clean_text(text):
    """ইমোজি ও সিম্বল ফিক্স করা"""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s-]", "", text)
    return cleaned.strip()


def extract_m3u8(html_content):
    """m3u8 স্ট্রিম লিংক বের করা"""
    m3u8_matches = re.findall(r"https?://[^\s'\"]+\.m3u8[^\s'\"]*", html_content)
    if m3u8_matches:
        return m3u8_matches[0]

    soup = BeautifulSoup(html_content, "html.parser")
    source = soup.find("source", {"type": "application/x-mpegURL"})
    if source and source.get("src"):
        return source.get("src")
    return None


def scrape_match_details(session, match_url):
    """একটি ম্যাচের সমস্ত তথ্য নিখুঁতভাবে পার্স করা"""
    try:
        res = session.get(match_url, timeout=12)
        res.encoding = "utf-8"

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        # ১. বেসিক তথ্য
        title_el = soup.find("h1", class_="video-title")
        title = title_el.text.strip() if title_el else "Football Match"

        comp_el = soup.find("a", class_="competition-link")
        competition = comp_el.text.strip() if comp_el else "Unknown Competition"

        date_el = soup.find("span", class_="meta-date")
        match_date = date_el.text.strip() if date_el else ""

        # ২. প্রতিযোগিতা কভার পিকচার (Cover Image)
        competition_cover = ""
        cover_match = re.search(r"(/covers/[a-zA-Z0-9\-_.]+\.webp)", res.text)
        if cover_match:
            competition_cover = urljoin(BASE_URL, cover_match.group(1))

        # ৩. টিমের তথ্য ও লোগো
        home_team = soup.find("div", class_="score-team home-team")
        home_name = "Home Team"
        home_logo = ""
        if home_team:
            hn_el = home_team.find("span", class_="score-team-name")
            if hn_el:
                home_name = hn_el.text.strip()
            hl_img = home_team.find("img")
            if hl_img and hl_img.get("src"):
                home_logo = hl_img["src"]

        away_team = soup.find("div", class_="score-team away-team")
        away_name = "Away Team"
        away_logo = ""
        if away_team:
            an_el = away_team.find("span", class_="score-team-name")
            if an_el:
                away_name = an_el.text.strip()
            al_img = away_team.find("img")
            if al_img and al_img.get("src"):
                away_logo = al_img["src"]

        scores = soup.find_all("span", class_="score-value")
        home_score = scores[0].text.strip() if len(scores) > 0 else "0"
        away_score = scores[1].text.strip() if len(scores) > 1 else "0"

        status_el = soup.find("span", class_="score-label")
        match_status = status_el.text.strip() if status_el else "FT"

        # ৪. ডেসক্রিপশন
        description = ""
        desc_container = soup.find("div", class_="description-container")
        if desc_container:
            raw_text = desc_container.get_text(separator=" ", strip=True)
            raw_text = (
                raw_text.replace("Read more...", "")
                .replace("More", "")
                .strip()
            )
            description = re.sub(r"\s+", " ", raw_text).strip()

        # ৫. থাম্বনেইল লিংক
        thumbnail_url = ""
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            thumbnail_url = og_image["content"]
        else:
            video_el = soup.find("video")
            if video_el and video_el.get("poster"):
                thumbnail_url = video_el["poster"]

        # ৬. স্ট্রিম পার্টস (Streams)
        streams = []
        seen_m3u8 = set()
        all_links = soup.find_all("a", href=True)
        valid_part_buttons = []

        for a in all_links:
            href = a["href"]
            text_lower = a.text.strip().lower()

            if href == "#" or "?play=" in href:
                if any(
                    k in text_lower
                    for k in [
                        "half",
                        "extra time",
                        "caremony",
                        "ceremony",
                        "full match",
                    ]
                ):
                    valid_part_buttons.append(a)

        if valid_part_buttons:
            for btn in valid_part_buttons:
                href = btn["href"]
                part_name = clean_text(btn.text)

                if href == "#" or not href.startswith("?play="):
                    m3u8_link = extract_m3u8(res.text)
                else:
                    full_part_url = match_url + href
                    try:
                        part_res = session.get(full_part_url, timeout=10)
                        part_res.encoding = "utf-8"
                        m3u8_link = (
                            extract_m3u8(part_res.text)
                            if part_res.status_code == 200
                            else None
                        )
                    except Exception:
                        m3u8_link = None

                if m3u8_link and m3u8_link not in seen_m3u8:
                    streams.append({"part": part_name, "m3u8_url": m3u8_link})
                    seen_m3u8.add(m3u8_link)
        else:
            m3u8_link = extract_m3u8(res.text)
            if m3u8_link:
                streams.append({"part": "Full Stream", "m3u8_url": m3u8_link})

        # ৭. স্ট্যাটিস্টিক্স
        stats = {}
        stat_rows = soup.find_all("div", class_="stat-row")
        for row in stat_rows:
            label_el = row.find("span", class_="stat-label")
            home_val_el = row.find("div", class_="stat-value home")
            away_val_el = row.find("div", class_="stat-value away")

            if label_el and home_val_el and away_val_el:
                stat_name = label_el.text.strip().lower().replace(" ", "_")
                stats[stat_name] = {
                    home_name: home_val_el.text.strip(),
                    away_name: away_val_el.text.strip(),
                }

        home_pos = soup.find("span", class_="home-possession")
        away_pos = soup.find("span", class_="away-possession")
        if home_pos and away_pos:
            stats["ball_possession"] = {
                home_name: home_pos.text.strip(),
                away_name: away_pos.text.strip(),
            }

        # ৮. সামারি ইভেন্টস (Events)
        events = []
        events_container = soup.find("div", class_="match-events")
        if events_container:
            event_wrappers = events_container.find_all(
                "div", class_="event-wrapper"
            )
            for wrap in event_wrappers:
                item = wrap.find("div", class_="event-item")
                if item:
                    item_classes = item.get("class", [])
                    actual_team = home_name if "home" in item_classes else away_name

                    time_el = item.find("div", class_="event-time")
                    time_val = time_el.text.strip() if time_el else ""

                    player_el = item.find("span", class_="player-name")
                    player_val = player_el.text.strip() if player_el else ""

                    assist_el = item.find("span", class_="assist-name")
                    assist_val = (
                        assist_el.text.strip()
                        .replace("Assist:", "")
                        .strip()
                        if assist_el
                        else ""
                    )

                    score_el = item.find("span", class_="score-update")
                    score_val = score_el.text.strip() if score_el else ""

                    icon_el = item.find("div", class_="event-icon")
                    icon_val = icon_el.text.strip() if icon_el else ""

                    ev_type = "Event"
                    if "⚽" in icon_val or score_val:
                        ev_type = "Goal"
                    elif "🟨" in icon_val:
                        ev_type = "Yellow Card"
                    elif (
                        "🟥" in icon_val
                        or "•" in icon_val
                        or "second yellow" in player_val.lower()
                    ):
                        ev_type = "Red Card"

                    ev_obj = {
                        "time": time_val,
                        "team": actual_team,
                        "player": player_val,
                        "event_type": ev_type,
                    }
                    if assist_val:
                        ev_obj["assist"] = assist_val
                    if score_val:
                        ev_obj["score_update"] = score_val

                    events.append(ev_obj)

        # ৯. হেড-টু-হেড (H2H Data)
        h2h_data = {
            "summary": {},
            "previous_matches": [],
            "home_team_form": {"team": home_name, "form": [], "recent_matches": []},
            "away_team_form": {"team": away_name, "form": [], "recent_matches": []},
        }

        h2h_container = soup.find("div", class_="match-h2h")
        if h2h_container:
            sum_el = h2h_container.find("div", class_="h2h-summary")
            if sum_el:
                hw = sum_el.find("div", class_="stat-item home")
                dr = sum_el.find("div", class_="stat-item draw")
                aw = sum_el.find("div", class_="stat-item away")
                h2h_data["summary"] = {
                    f"{home_name}_wins": hw.find("span", class_="stat-value").text.strip()
                    if hw and hw.find("span", class_="stat-value")
                    else "0",
                    "draws": dr.find("span", class_="stat-value").text.strip()
                    if dr and dr.find("span", class_="stat-value")
                    else "0",
                    f"{away_name}_wins": aw.find("span", class_="stat-value").text.strip()
                    if aw and aw.find("span", class_="stat-value")
                    else "0",
                }

            h2h_list_tab = h2h_container.find("div", id="h2h-tab-h2h-list")
            if h2h_list_tab:
                for row in h2h_list_tab.find_all("div", class_="match-row"):
                    d_el = row.find("span", class_="date")
                    comp_el = row.find("span", class_="competition")
                    teams_el = row.find("div", class_="match-teams")

                    h2h_data["previous_matches"].append(
                        {
                            "date": d_el.text.strip() if d_el else "",
                            "competition": comp_el.text.strip()
                            if comp_el
                            else "",
                            "teams_and_score": re.sub(
                                r"\s+", " ", teams_el.text
                            ).strip()
                            if teams_el
                            else "",
                        }
                    )

            home_form_tab = h2h_container.find("div", id="h2h-tab-home-form")
            if home_form_tab:
                dots = [
                    d.text.strip()
                    for d in home_form_tab.find_all("span", class_="form-dot")
                ]
                matches = []
                for row in home_form_tab.find_all("div", class_="match-row"):
                    d_el = row.find("span", class_="date")
                    comp_el = row.find("span", class_="competition")
                    teams_el = row.find("div", class_="match-teams")
                    res_el = row.find("div", class_="result-badge")
                    matches.append(
                        {
                            "date": d_el.text.strip() if d_el else "",
                            "competition": comp_el.text.strip()
                            if comp_el
                            else "",
                            "teams_and_score": re.sub(
                                r"\s+", " ", teams_el.text
                            ).strip()
                            if teams_el
                            else "",
                            "result": res_el.text.strip() if res_el else "",
                        }
                    )
                h2h_data["home_team_form"]["form"] = dots
                h2h_data["home_team_form"]["recent_matches"] = matches

            away_form_tab = h2h_container.find("div", id="h2h-tab-away-form")
            if away_form_tab:
                dots = [
                    d.text.strip()
                    for d in away_form_tab.find_all("span", class_="form-dot")
                ]
                matches = []
                for row in away_form_tab.find_all("div", class_="match-row"):
                    d_el = row.find("span", class_="date")
                    comp_el = row.find("span", class_="competition")
                    teams_el = row.find("div", class_="match-teams")
                    res_el = row.find("div", class_="result-badge")
                    matches.append(
                        {
                            "date": d_el.text.strip() if d_el else "",
                            "competition": comp_el.text.strip()
                            if comp_el
                            else "",
                            "teams_and_score": re.sub(
                                r"\s+", " ", teams_el.text
                            ).strip()
                            if teams_el
                            else "",
                            "result": res_el.text.strip() if res_el else "",
                        }
                    )
                h2h_data["away_team_form"]["form"] = dots
                h2h_data["away_team_form"]["recent_matches"] = matches

        return {
            "title": title,
            "competition": competition,
            "competition_cover": competition_cover,
            "date": match_date,
            "thumbnail_url": thumbnail_url,
            "teams": {
                "home_team": {
                    "name": home_name,
                    "logo": home_logo,
                    "score": home_score,
                },
                "away_team": {
                    "name": away_name,
                    "logo": away_logo,
                    "score": away_score,
                },
                "status": match_status,
            },
            "streams": streams,
            "statistics": stats,
            "events_timeline": events,
            "head_to_head": h2h_data,
            "description": description,  # <-- ডেসক্রিপশন একদম শেষে
        }

    except Exception as e:
        print(f"Error scraping {match_url}: {e}")
        return None


def get_all_sitemap_video_links():
    """সাইটম্যাপ থেকে সর্বমোট ৪,৩৫৩+ টি ম্যাচের সোর্স লিংক সংগ্রহ করে"""
    print("[-] সাইটম্যাপ থেকে সকল ভিডিও লিংক স্ক্যান করা হচ্ছে...")
    session = requests.Session()
    session.headers.update(HEADERS)

    sitemap_index_url = urljoin(BASE_URL, "/sitemap-index.xml")
    video_links = set()

    try:
        res = session.get(sitemap_index_url, timeout=15)
        res.encoding = "utf-8"
        if res.status_code == 200:
            sitemap_urls = re.findall(
                r"<loc>(https?://[^\s<]+)</loc>", res.text
            )

            def parse_sm(sm_url):
                found = set()
                try:
                    s_session = requests.Session()
                    s_session.headers.update(HEADERS)
                    sm_res = s_session.get(sm_url, timeout=15)
                    if sm_res.status_code == 200:
                        matches = re.findall(
                            r"<loc>(https?://[^\s<]+/video/[^\s<]+)</loc>",
                            sm_res.text,
                        )
                        for m in matches:
                            found.add(m)
                except Exception:
                    pass
                return found

            with ThreadPoolExecutor(max_workers=20) as executor:
                results = executor.map(parse_sm, sitemap_urls)

            for match_set in results:
                video_links.update(match_set)

    except Exception as e:
        print(f"[!] সাইটম্যাপ স্ক্যানিং সমস্যা: {e}")

    return list(video_links)


def main():
    print(
        f"\n[!] ReFooty অল-ম্যাচ অটোমেশন প্রসেস শুরু: {get_ist_time()}"
    )

    # ১. আগের জেসন ফাইল থাকলে তা লোড করা (যাতে ডুপ্লিকেট আবার স্ক্যান না করতে হয়)
    existing_data = []
    scraped_titles = set()

    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old_json = json.load(f)
                existing_data = old_json.get("matches", [])
                for item in existing_data:
                    scraped_titles.add(item.get("title"))
            print(
                f"[+] পূর্ববর্তী সেভ করা {len(existing_data)} টি ম্যাচ লোড করা হয়েছে।"
            )
        except Exception as e:
            print(f"[!] পুরোনো ফাইল পড়তে সমস্যা: {e}")

    # ২. সাইটম্যাপ থেকে সকল ভিডিও লিংক তুলে আনা
    all_links = get_all_sitemap_video_links()
    print(f"[+] সাইটম্যাপে মোট {len(all_links)} টি ম্যাচের লিংক পাওয়া গেছে।")

    # ৩. শুধুমাত্র যেগুলোর স্ক্যান বাকি আছে সেগুলো ফিল্টার করা
    # (ফাস্ট মোডে প্রথমবার সব স্ক্যান হবে, পরবর্তী রানে শুধু নতুনগুলো)
    new_matches_data = []

    def task(link):
        thread_session = requests.Session()
        thread_session.headers.update(HEADERS)
        return scrape_match_details(thread_session, link)

    print(f"[-] মাল্টি-থ্রেডিং মোডে ফাস্ট প্রসেসিং চলছে...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(task, all_links)

    for data in results:
        if data and data.get("title") not in scraped_titles:
            new_matches_data.append(data)
            scraped_titles.add(data.get("title"))

    # ৪. নতুন এবং পুরোনো ডাটা মার্জ করা
    all_final_matches = new_matches_data + existing_data

    # ৫. ফাইনাল জেসন আউটপুট তৈরি
    final_package = {
        "Owner": "Ivan-FluX",
        "Telegram": "https://t.me/iVan_flux",
        "App_name": "ReFooty All Matches Auto Scraper",
        "Last_update": get_ist_time(),
        "Total_Matches": len(all_final_matches),
        "matches": all_final_matches,
    }

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(final_package, f, indent=4, ensure_ascii=False)
        print(
            f"[SUCCESS] সফলতা সহকারে {OUTPUT_FILE} তৈরি হয়েছে! মোট ম্যাচ: {len(all_final_matches)}"
        )
    except Exception as e:
        print(f"[ERROR] জেসন সেভ ব্যর্থ: {e}")


if __name__ == "__main__":
    main()
