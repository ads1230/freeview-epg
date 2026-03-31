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
    # Append ?w=800 to ensure we get the high-res station logo, not a tiny icon
    full_url = f"{url}?w=800" if "?" not in url else f"{url}&w=800"
    
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    if not filename: return None
    if "." not in filename: filename += ".png"
    
    local_path = os.path.join(LOGO_DIR, filename)
    
    if not os.path.exists(local_path):
        try:
            r = session.get(full_url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SAVED] Official Logo: {filename}")
                return filename
        except:
            return None
    return filename

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running North West Logo Recovery (NID: {NID}) ---")
    session = requests.Session()
    # Adding a realistic User-Agent and Cookie to force the API to yield the channel list
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': f'fv_location={NID}; userNid={NID}'
    })
    
    # 1. Fetching the logo map with improved error checking
    logo_map = {}
    try:
        log(f"Requesting master channel list for NID 64257...")
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        data = r.json()
        
        # Freeview API structure can vary: check 'data' or 'channels' directly
        channels_raw = data.get('data', {}).get('channels', []) or data.get('channels', [])
        
        for c in channels_raw:
            sid = str(c.get('service_id'))
            # We look for the logo in the 'image_assets' -> 'logo' -> 'default' path
            # This path is EXCLUSIVE to the station brand, preventing 'show' thumbnails
            img = c.get('image_assets', {}).get('logo', {}).get('default')
            if img:
                logo_map[sid] = img
        
        log(f"Successfully verified {len(logo_map)} Station Logos.")
    except Exception as e:
        log(f"Critical error mapping logos: {e}")

    channels, progs = {}, []
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # 2. Fetching Schedule
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = session.get(url, timeout=15)
            day_data = r.json().get('data', {}).get('programs', [])
            
            for chan in day_data:
                cid = str(chan.get('service_id'))
                if cid not in channels:
                    logo_url = logo_map.get(cid)
                    logo_file = download_icon(logo_url, session)
                    
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
            log(f"Error on day {day}: {e}")

    # 3. Writing XMLTV
    log(f"Writing {OUTPUT} with {len(channels)} channels...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>')
        for cid, info in channels.items():
            clean_name = info['name'].replace("&", "&amp;")
            f.write(f'<channel id="{cid}"><display-name>{clean_name}</display-name>')
            if info['logo']:
                f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
            f.write('</channel>')
        for p in progs:
            clean_title = p['title'].replace("&", "&amp;")
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{clean_title}</title></programme>')
        f.write('</tv>')
    log("Process Complete.")

if __name__ == "__main__":
    run()
