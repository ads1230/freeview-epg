import requests
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64377" 
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"

GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

def download_icon(url, session):
    if not url: return None
    # Ensure the URL includes the width parameter
    full_url = f"{url}&w=800" if "?" in url else f"{url}?w=800"
    
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    if not filename.endswith('.png'): filename += ".png"
    
    local_path = os.path.join(LOGO_DIR, filename)
    
    if not os.path.exists(local_path):
        try:
            r = session.get(full_url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SUCCESS] Downloaded: {filename}")
                return filename
        except:
            return None
    return filename

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running North West Guide with Logo Debugging ---")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    # 1. Fetch logos from the master channel-list
    logo_map = {}
    try:
        # We try the 64257 NID for the logo list specifically as it's the most complete
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        if r.status_code == 200:
            channels_data = r.json().get('data', {}).get('channels', [])
            log(f"Master List found {len(channels_data)} potential logos.")
            for c in channels_data:
                sid = str(c.get('service_id'))
                if c.get('image_url'):
                    logo_map[sid] = c.get('image_url')
    except Exception as e:
        log(f"Logo map fetch error: {e}")

    channels, progs = {}, []
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # 2. Fetch Schedule
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = session.get(url, timeout=15)
            if r.status_code != 200: continue

            day_data = r.json().get('data', {}).get('programs', [])
            for chan in day_data:
                cid = str(chan.get('service_id'))
                if cid not in channels:
                    # Attempt 1: Get from our Master Logo Map
                    logo_url = logo_map.get(cid)
                    
                    # Attempt 2: Get from the TV Guide entry itself if Master Map failed
                    if not logo_url:
                        logo_url = chan.get('channel', {}).get('image')
                    
                    logo_file = download_icon(logo_url, session) if logo_url else None
                    
                    if not logo_file:
                        log(f"   [Notice] No logo found for {chan.get('title')} (ID: {cid})")

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
    log(f"Writing XML with {len(channels)} channels...")
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
