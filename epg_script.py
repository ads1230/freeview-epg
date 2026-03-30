import requests
import time
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from tqdm import tqdm  # New import

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64257" 
DAYS = 8       
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"
GITHUB_USER = "ads1230"
GITHUB_REPO = "freeview-epg"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

if not os.path.exists(LOGO_DIR):
    os.makedirs(LOGO_DIR)

def get_meta(pid):
    try:
        params = {'nid': NID, 'pid': pid}
        resp = requests.get(f"https://www.freeview.co.uk/api/more-episodes", params=params, timeout=5)
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 'en': d.get('episodeNumber'),
                'desc': d.get('description'), 'sub': d.get('episodeTitle'),
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
        day_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        
        try:
            r = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}", headers=headers, timeout=15)
            day_data = r.json().get('data', {}).get('programs', [])
            
            # Progress Bar for the current day's channels
            pbar = tqdm(day_data, desc=f"Day {day+1} ({day_str})", unit="chan", leave=True, ascii=" #")
            
            for channel_entry in pbar:
                cid = channel_entry.get('service_id')
                if cid not in channels:
                    channels[cid] = {'name': channel_entry.get('title'), 'logo': None} # Simplified for speed

                for event in channel_entry.get('events', []):
                    title = event.get('main_title')
                    pid = event.get('program_id')
                    
                    if pid and pid not in meta_cache:
                        meta_cache[pid] = get_meta(pid)
                        time.sleep(0.04)

                    progs.append({
                        'cid': cid, 
                        's': datetime.strptime(event['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'), 
                        'e': parse_duration_to_stop(event['start_time'], event['duration']),
                        't': title, 'pid': pid
                    })
            pbar.close() # Clean up the bar after the day is done
        except Exception as e:
            log(f"   ! Day Error: {e}")

    log(f"Writing XML...")
    # ... [XML Writing Logic here is the same as previous version] ...
    log("Done!")

if __name__ == "__main__":
    run()
