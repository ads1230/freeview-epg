import requests
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64377" # The NID that successfully gave us North West data
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"

# Automatically capture GitHub Info for the XML Icon URLs
GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

def get_logo_map(session):
    """Fetch all logos from the channel-list API once at the start."""
    logo_map = {}
    try:
        log(f"Fetching master logo list from Channel-List API...")
        # Using the specific NID 64257 as requested for the logo source
        url = "https://www.freeview.co.uk/api/channel-list?nid=64257"
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            channels_data = r.json().get('data', {}).get('channels', [])
            for c in channels_data:
                sid = str(c.get('service_id'))
                img_url = c.get('image_url')
                if img_url:
                    # Append the width parameter for high-res images
                    logo_map[sid] = f"{img_url}?w=800"
    except Exception as e:
        log(f"Warning: Could not fetch logo list: {e}")
    return logo_map

def download_icon(url, session):
    if not url: return None
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    if not filename.endswith('.png'): filename += ".png"
    
    local_path = os.path.join(LOGO_DIR, filename)
    
    if not os.path.exists(local_path):
        try:
            # We add the ?w=800 here to get the high-res version
            r = session.get(f"{url}?w=800", timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SUCCESS] Saved logo: {filename}")
                return filename
            else:
                log(f"   [FAILED] HTTP {r.status_code} for {filename}")
        except Exception as e:
            log(f"   [ERROR] Could not save {filename}: {e}")
            return None
    return filename

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running Bolton/NW Guide (NID: {NID}) ---")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    # 1. Get the Logo Map first
    master_logos = get_logo_map(session)
    
    channels, progs = {}, []
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # 2. Fetch the Schedule
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Schedule Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = session.get(url, timeout=15)
            if r.status_code != 200: continue

            day_data = r.json().get('data', {}).get('programs', [])
            for chan in day_data:
                cid = str(chan.get('service_id'))
                if cid not in channels:
                    # Look up logo from our master map
                    logo_url = master_logos.get(cid)
                    logo_file = download_icon(logo_url, session) if logo_url else None
                    
                    channels[cid] = {
                        'name': chan.get('title'),
                        'logo': logo_file
                    }
                
                for ev in chan.get('events', []):
                    progs.append({
                        'cid': cid,
                        'start': datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'),
                        'title': ev.get('main_title')
                    })
        except Exception as e:
            log(f"Error: {e}")

    # 3. Write XML
    log(f"Writing XML with {len(channels)} channels and high-res icons...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>')
        for cid, info in channels.items():
            f.write(f'<channel id="{cid}"><display-name>{info["name"].replace("&", "&amp;")}</display-name>')
            if info['logo']:
                f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
            f.write('</channel>')
            
        for p in progs:
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{p["title"].replace("&", "&amp;")}</title></programme>')
        f.write('</tv>')
    log("Process Complete.")

if __name__ == "__main__":
    run()
