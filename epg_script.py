import requests
import time
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# Force output to show in GitHub logs immediately
def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64257"  # Your Freeview Region (Bolton/North West)
DAYS = 8       
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"

# Update these for your private repository
GITHUB_USER = "YourUsername"
GITHUB_REPO = "YourRepo"
GITHUB_TOKEN = "ghp_YourTokenHere" # Optional: Only if you want icons to work in a private repo

if GITHUB_TOKEN:
    GITHUB_RAW_BASE = f"https://{GITHUB_TOKEN}@raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"
else:
    GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

if not os.path.exists(LOGO_DIR):
    os.makedirs(LOGO_DIR)

def download_icon(url):
    if not url: return None
    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(LOGO_DIR, filename)
    if not os.path.exists(local_path):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [Logo] Saved: {filename}")
        except: return None
    return filename

def get_meta(pid):
    try:
        params = {'nid': NID, 'pid': pid}
        # Note the domain is freeview.co.uk
        resp = requests.get(f"https://www.freeview.co.uk/api/more-episodes", params=params, timeout=5)
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 
                'en': d.get('episodeNumber'),
                'desc': d.get('description'), 
                'sub': d.get('episodeTitle'),
                'img_url': d.get('imageUrl')
            }
    except: pass
    return None

def parse_duration_to_stop(start_str, duration_str):
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
        h = int(re.search(r'(\d+)H', duration_str).group(1)) if 'H' in duration_str else 0
        m = int(re.search(r'(\d+)M', duration_str).group(1)) if 'M' in duration_str else 0
        return (start_dt + timedelta(hours=h, minutes=m)).strftime('%Y%m%d%H%M%S %z')
    except: return None

def run():
    log("--- Starting Freeview EPG Scraper (Bolton) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs, meta_cache = {}, [], {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Processing Day {day+1}/{DAYS}: {datetime.fromtimestamp(ts).strftime('%Y-%m-%d')}")
        
        try:
            # Note the domain is freeview.co.uk
            r = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}", headers=headers, timeout=15)
            day_data = r.json().get('data', {}).get('programs', [])
            
            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                if cid not in channels:
                    logo = download_icon(channel_entry.get('channel', {}).get('image'))
                    channels[cid] = {'name': channel_entry.get('title'), 'logo': logo}

                for event in channel_entry.get('events', []):
                    title = event.get('main_title')
                    pid = event.get('program_id')
                    
                    # Cache logic to avoid duplicate API calls
                    if pid and pid not in meta_cache:
                        log(f"      > Metadata: {title}")
                        meta_cache[pid] = get_meta(pid)
                        time.sleep(0.04)

                    progs.append({
                        'cid': cid, 
                        's': datetime.strptime(event['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'), 
                        'e': parse_duration_to_stop(event['start_time'], event['duration']),
                        't': title, 
                        'pid': pid
                    })
        except Exception as e:
            log(f"   ! Day Error: {e}")

    log(f"Writing XML with {len(progs)} entries...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}"><display-name>{info["name"]}</display-name>')
            if info['logo']: f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
            f.write('</channel>\n')

        for p in progs:
            m = meta_cache.get(p['pid'])
            f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}"><title>{p["t"].replace("&", "&amp;")}</title>')
            if m:
                if m.get('sub'): f.write(f'<sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>')
                if m.get('desc'): f.write(f'<desc>{m["desc"].replace("&", "&amp;")}</desc>')
                if m.get('img_url'): f.write(f'<icon src="{m["img_url"]}" />')
                if m.get('sn') and m.get('en'): f.write(f'<episode-num system="onscreen">S{m["sn"]} E{m["en"]}</episode-num>')
            f.write('</programme>\n')
        f.write('</tv>')
    log("Done!")

if __name__ == "__main__":
    run()
