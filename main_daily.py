from datetime import datetime
import json
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pytz
import requests

BASE_URL = "https://refooty.com"
OUTPUT_FILE = "latest_daily.json"
STATE_FILE = "last_seen.json"

GITHUB_USER = "api00007"
GITHUB_REPO = "Refooty"
GITHUB_EMAIL = "sptv5204@gmail.com"
GITHUB_TOKEN = os.environ.get(
    "PAT_TOKEN", "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"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}


def get_ist_time():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%I:%M:%S %p %d-%m-%Y")


def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s-]", "", text)
    return cleaned.strip()


def extract_m3u8(html_content):
    m3u8_matches = re.findall(
        r"https?://[^\s'\"]+\.m3u8[^\s'\"]*", html_content
    )
    if m3u8_matches:
        return m3u8_matches[0]

    soup = BeautifulSoup(html_content, "html.parser")
    source = soup.find("source", {"type": "application/x-mpegURL"})
    if source and source.get("src"):
        return source.get("src")
    return None


def extract_teams_from_title(title):
    if not title:
        return None, None
    clean_t = re.sub(
        r"\b(full match|highlights|goals|watch)\b",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    parts = re.split(r"\s+(?:vs|v|-|–|—)\s+", clean_t, flags=re.IGNORECASE)
    if len(parts) >= 2:
        t1 = parts[0].strip()
        t2 = parts[1].strip()
        if t1 and t2:
            return t1, t2
    return None, None


def scrape_match_details(session, match_url):
    try:
        res = session.get(match_url, timeout=12)
        res.encoding = "utf-8"

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        title_el = soup.find("h1", class_="video-title")
        title = title_el.text.strip() if title_el else "Football Match"

        comp_el = soup.find("a", class_="competition-link")
        competition = (
            comp_el.text.strip() if comp_el else "Unknown Competition"
        )

        date_el = soup.find("span", class_="meta-date")
        match_date = date_el.text.strip() if date_el else ""

        competition_cover = ""
        cover_match = re.search(
            r"(/covers/[a-zA-Z0-9\-_.]+\.webp)", res.text
        )
        if cover_match:
            competition_cover = urljoin(BASE_URL, cover_match.group(1))

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

        events_info = {
            "away_team": {
                "logo": away_logo,
                "name": away_name,
                "score": away_score,
            },
            "home_team": {
                "logo": home_logo,
                "name": home_name,
                "score": home_score,
            },
            "status": match_status,
        }

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

        thumbnail_url = ""
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            thumbnail_url = og_image["content"]
        else:
            video_el = soup.find("video")
            if video_el and video_el.get("poster"):
                thumbnail_url = video_el["poster"]

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
                    actual_team = (
                        home_name if "home" in item_classes else away_name
                    )

                    time_el = item.find("div", class_="event-time")
                    time_val = time_el.text.strip() if time_el else ""

                    player_el = item.find("span", class_="player-name")
                    player_val = (
                        player_el.text.strip() if player_el else ""
                    )

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

        h2h_data = {
            "summary": {},
            "previous_matches": [],
            "home_team_form": {
                "team": home_name,
                "form": [],
                "recent_matches": [],
            },
            "away_team_form": {
                "team": away_name,
                "form": [],
                "recent_matches": [],
            },
        }

        h2h_container = soup.find("div", class_="match-h2h")
        if h2h_container:
            sum_el = h2h_container.find("div", class_="h2h-summary")
            if sum_el:
                hw = sum_el.find("div", class_="stat-item home")
                dr = sum_el.find("div", class_="stat-item draw")
                aw = sum_el.find("div", class_="stat-item away")
                h2h_data["summary"] = {
                    f"{home_name}_wins": hw.find(
                        "span", class_="stat-value"
                    ).text.strip()
                    if hw and hw.find("span", class_="stat-value")
                    else "0",
                    "draws": dr.find("span", class_="stat-value").text.strip()
                    if dr and dr.find("span", class_="stat-value")
                    else "0",
                    f"{away_name}_wins": aw.find(
                        "span", class_="stat-value"
                    ).text.strip()
                    if aw and aw.find("span", class_="stat-value")
                    else "0",
                }

            h2h_list_tab = h2h_container.find("div", id="h2h-tab-h2h-list")
            if h2h_list_tab:
                for row in h2h_list_tab.find_all("div", class_="match-row"):
                    d_el = row.find("span", class_="date")
                    comp_el = row.find("span", class_="competition")
                    teams_el = row.find("div", class_="match-teams")

                    h2h_data["previous_matches"].append({
                        "date": d_el.text.strip() if d_el else "",
                        "competition": comp_el.text.strip()
                        if comp_el
                        else "",
                        "teams_and_score": re.sub(
                            r"\s+", " ", teams_el.text
                        ).strip()
                        if teams_el
                        else "",
                    })

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
                    matches.append({
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
                    })
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
                    matches.append({
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
                    })
                h2h_data["away_team_form"]["form"] = dots
                h2h_data["away_team_form"]["recent_matches"] = matches

        return {
            "title": title,
            "thumbnail_url": thumbnail_url,
            "competition": competition,
            "competition_cover": competition_cover,
            "date": match_date,
            "events_info": events_info,
            "streams": streams,
            "events_timeline": events,
            "head_to_head": h2h_data,
            "statistics": stats,
            "description": description,
        }

    except Exception:
        return None


def load_last_seen_slug():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f)
                return st.get("last_slug", "")
        except Exception:
            pass
    return ""


def save_last_seen_slug(slug):
    if slug:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_slug": slug}, f, indent=2)


def fetch_new_matches_only(session):
    last_slug = load_last_seen_slug()
    api_url = f"{BASE_URL}/api/videos/latest.json?page=1&per_page=25&locale=en"
    new_match_urls = []

    try:
        res = session.get(api_url, timeout=15)
        res.encoding = "utf-8"

        if res.status_code != 200:
            return []

        data = res.json()
        videos = data.get("videos", [])

        for item in videos:
            slug = item.get("slug")
            if not slug:
                continue

            if slug == last_slug:
                break

            full_url = f"{BASE_URL}/video/{slug}"
            new_match_urls.append((slug, full_url))

    except Exception:
        pass

    return new_match_urls


def push_to_github():
    remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    try:
        os.system(f'git config --global user.email "{GITHUB_EMAIL}"')
        os.system(f'git config --global user.name "{GITHUB_USER}"')
        os.system(f"git remote set-url origin {remote_url}")

        os.system("git add .")
        os.system(
            f'git commit -m "Incremental Daily Update: {get_ist_time()}"'
        )
        os.system("git push origin main")
    except Exception:
        pass


def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    new_items = fetch_new_matches_only(session)
    if not new_items:
        return

    latest_top_slug = new_items[0][0]

    scraped_matches = []
    for slug, url in new_items:
        data = scrape_match_details(session, url)
        if data:
            scraped_matches.append(data)

    if scrap
