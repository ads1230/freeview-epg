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
    
    # Append width for high-res
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
                log(f"   [SUCCESS] Downloaded: {filename}")
                return filename
        except:
            return None
    return filename

def find_logo_in_json(obj):
    """Recursively searches the JSON for a logo URL."""
    # Common keys used by Freeview/Everyone TV for logos
    keys_to_check = ['default', 'image_url', 'url', 'image']
    
    if isinstance(obj, dict):
        # Check if this dict has a 'logo' or 'image_assets' key
        for k, v in obj.items():
            if k in ['logo', 'image_assets', 'image']:
                # If we found a logo object, look for the 'default' or URL inside it
                if isinstance(v, dict):
                    for sub_k in keys_to_check:
                        if v.get(sub_k): return v.get(sub_k)
                elif isinstance(v, str) and v.startswith('http'):
                    return v
            
            # Keep digging deeper
            res = find_logo_in_json(v)
            if res: return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_logo_in_json(item)
            if res: return res
    return None

def get_logo_map(session):
    logo_map = {}
    try:
        log(f"Fetching master logo list (NID: 64257)...")
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', {})
            channels_list = data.get('channels', [])
            
            for c in channels_list:
                sid = str(c.get('service_id'))
                # Use our deep search function to find the URL
                img_url = find_logo_in_json(c)
                if img_url:
                    logo_map[sid] = img_url
            
            log(f"Master List mapped {len(logo_map)} logos.")
            if len(logo_map) == 0 and len(channels_list) > 0:
                log(f"DEBUG: First channel structure: {channels_list[0]}")
    except Exception as e:
        log(f"Logo map fetch error: {e}")
    return logo_map

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running North West Guide (NID: {NID}) ---")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
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
                if cid not in channels:
                    logo_url = master_logos.get(cid) or find_logo_in_json(chan)
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
