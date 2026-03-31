import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from tqdm import tqdm

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64257"  # Bolton / North West
DAYS = 8       
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"

GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'Unknown/Repo')
GITHUB_TOKEN = os.getenv('EPG_TOKEN_ENV') 

if '/' in GITHUB_REPO_FULL:
    GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/')
else:
    GITHUB_USER, GITHUB_REPO = "Unknown", "Unknown"

if GITHUB_TOKEN:
    GITHUB_RAW_BASE = f"https://{GITHUB_TOKEN}@raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"
else:
    GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

if not os.path.exists(LOGO_DIR):
    os.makedirs(LOGO_DIR)

# --- Setup Robust Session ---
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0'})

def download_icon(url):
    if not url: return None
    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(LOGO_DIR, filename)
    if not os.path.exists(local_path):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
            else:
                log(f"   [Icon Error] HTTP {r.status_code} for {url}")
        except Exception as e:
            log(f"   [Icon Exception] {str(e)}")
            return None
    return filename

def get_meta(pid, title):
    """Fetches episode details and prints errors if they occur."""
    try:
        params = {'nid': NID, 'pid': pid}
        resp = session.get(f"https://www.freeview.co.uk/api/more-episodes", params=params, timeout=10)
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 
                'en': d.get('episodeNumber'),
                'desc': d.get('description'), 
                'sub': d.get('episodeTitle'),
                'img_url': d.get('imageUrl')
            }
        else:
            # This will tell us if we are being rate-limited (429) or forbidden (403)
            log(f"   [Meta Error] HTTP {resp.status_code} for '{title}' (PID: {pid})")
    except Exception as e:
        log(f"   [Meta Exception] {str(e)} for '{title}'")
    return None

def parse_duration_to_stop(start_str, duration_str):
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
        h = int(re.search(r'(\d+)H', duration_str).group(1)) if 'H' in duration_str else 0
        m = int(re.search(r'(\d+)M', duration_str).group(1)) if 'M' in duration_str else 0
        return (start_dt + timedelta(hours=h, minutes=m)).strftime('%Y%m%d%H%M%S %z')
    except: return None

def run():
    log(f"--- Starting Detailed Freeview Scraper (Bolton NID: {NID}) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs, meta_cache = {}, [], {}
    meta_success = 0
    meta_fail = 0

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        day_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        
        try:
            r = session.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}", timeout=20)
            if r.status_code != 200:
                log(f"CRITICAL: Guide API returned HTTP {r.status_code} for {day_str}")
                continue

            day_data = r.json().get('data', {}).get('programs', [])
            pbar = tqdm(day_data, desc=f"Day {day+1} ({day_str})", unit="chan", ascii=" #", mininterval=5.0)
            
            for channel_entry in pbar:
                cid = channel_entry.get('service_id')
                if cid not in channels:
                    logo = download_icon(channel_entry.get('channel', {}).get('image'))
                    channels[cid] = {'name': channel_entry.get('title'), 'logo': logo}

                for event in channel_entry.get('events', []):
                    title = event.get('main_title')
                    pid = event.get('program_id')
                    
                    if pid and pid not in meta_cache:
                        m_data = get_meta(pid, title)
                        if m_data:
                            meta_cache[pid] = m_data
                            meta_success += 1
                        else:
                            meta_fail += 1
                        time.sleep(0.06) # Slightly increased delay for safety

                    progs.append({
                        'cid': cid, 
                        's': datetime.strptime(event['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'), 
                        'e': parse_duration_to_stop(event['start_time'], event['duration']),
                        't': title, 
                        'pid': pid
                    })
            pbar.close()
        except Exception as e:
            log(f"   ! Day Error: {str(e)}")

    log(f"Metadata Stats: {meta_success} Succeeded, {meta_fail} Failed")
    log(f"Writing XML...")
    
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for cid, info in channels.items():
            name = info['name'].replace("&", "&amp;").replace("<", "&lt;")
            f.write(f'  <channel id="{cid}"><display-name>{name}</display-name>')
            if info['logo']: f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
            f.write('</channel>\n')

        for p in progs:
            m = meta_cache.get(p['pid'])
            t = p['t'].replace("&", "&amp;").replace("<", "&lt;")
            f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}"><title>{t}</title>')
            if m:
                if m.get('sub'): f.write(f'<sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>')
                if m.get('desc'): f.write(f'<desc>{m["desc"].replace("&", "&amp;")}</desc>')
                if m.get('img_url'): f.write(f'<icon src="{m["img_url"]}" />')
                if m.get('sn') and m.get('en'): f.write(f'<episode-num system="onscreen">S{m["sn"]} E{m["en"]}</episode-num>')
            f.write('</programme>\n')
        f.write('</tv>')
    log("Process Complete.")

if __name__ == "__main__":
    run()
