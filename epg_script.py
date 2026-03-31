import requests
import os
import sys
import re
from datetime import datetime, timedelta, timezone

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

def make_safe_filename(name):
    """Converts 'BBC ONE N West!' to 'bbc_one_n_west.png'"""
    if not name: return "unknown.png"
    # Convert to lowercase, replace spaces with underscores, remove non-alphanumeric
    safe = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))
    return f"{safe}.png"

def download_icon(url, channel_name, session):
    if not url: return None
    
    # Ensure high-res quality
    base_url = url.split('?')[0]
    full_url = f"{base_url}?w=800"
    
    # Use the human-readable channel name
    filename = make_safe_filename(channel_name)
    local_path = os.path.join(LOGO_DIR, filename)
    
    # If we already have the readable logo, don't download it again
    if not os.path.exists(local_path):
        try:
            r = session.get(full_url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SAVED] {filename}")
                return filename
        except:
            return None
    return filename

def get_logo_map(session):
    """Fetches the official logos directly from the LIVE Freeview API."""
    logo_map = {}
    try:
        log(f"Fetching master logo list from Live API (NID: 64257)...")
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        
        if r.status_code == 200:
            services_data = r.json().get('data', {}).get('services', [])
            
            for s in services_data:
                sid = str(s.get('service_id'))
                img_url = s.get('service_image') or s.get('images', {}).get('default')
                if img_url:
                    logo_map[sid] = img_url
            
            log(f"Successfully mapped {len(logo_map)} Station Logos from the Live API.")
    except Exception as e:
        log(f"Live logo map fetch error: {e}")
    return logo_map

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running North West Guide (NID: {NID}) ---")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie': f'fv_location={NID}; userNid={NID}'
    })
    
    master_logos = get_logo_map(session)

    channels, progs = {}, []
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

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
                chan_name = chan.get('title', 'Unknown')
                
                if cid not in channels:
                    logo_url = master_logos.get(cid)
                    # Pass the channel name to the download function
                    logo_file = download_icon(logo_url, chan_name, session) if logo_url else None
                    
                    channels[cid] = {
                        'name': chan_name,
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

    log(f"Writing XML with {len(channels)} channels...")
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
