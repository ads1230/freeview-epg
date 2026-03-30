import requests
import time
import re
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# --- Configuration ---
NID = "64257"
DAYS = 8
OUTPUT = "freeview_rich_14day.xml"
LOGO_DIR = "logos"

# Create logos directory if it doesn't exist
if not os.path.exists(LOGO_DIR):
    os.makedirs(LOGO_DIR)

def download_icon(url):
    """Downloads an icon if it doesn't exist and returns the local filename."""
    if not url: return None
    
    # Extract filename (e.g., bbc-one.png)
    filename = os.path.basename(urlparse(url).path)
    if not filename: return None
    
    local_path = os.path.join(LOGO_DIR, filename)
    
    # Only download if we don't have it to save time/bandwidth
    if not os.path.exists(local_path):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                print(f"   [Logo] Downloaded: {filename}")
        except:
            return None
    return filename

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
    start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    h, m = (int(hours.group(1)) if hours else 0), (int(minutes.group(1)) if minutes else 0)
    return (start_dt + timedelta(hours=h, minutes=m)).strftime('%Y%m%d%H%M%S %z')

def run():
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs, cache = {}, [], {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        try:
            res = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}", headers=headers, timeout=20).json()
            day_data = res.get('data', {}).get('programs', [])
            
            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                if cid not in channels:
                    # DOWNLOAD CHANNEL LOGO
                    logo_file = download_icon(channel_entry.get('channel', {}).get('image'))
                    channels[cid] = {'name': channel_entry.get('title'), 'logo': logo_file}

                for event in channel_entry.get('events', []):
                    pid = event.get('program_id')
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05)

                    progs.append({
                        'cid': cid, 
                        's': datetime.strptime(event['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'), 
                        'e': parse_duration_to_stop(event['start_time'], event['duration']),
                        't': event.get('main_title'), 'pid': pid
                    })
        except: continue

    # Write XMLTV
    # Change 'YourUsername' and 'YourRepo' to your actual GitHub details
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com/YourUsername/YourRepo/main/logos/"

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}">\n')
            f.write(f'    <display-name>{info["name"]}</display-name>\n')
            if info['logo']:
                f.write(f'    <icon src="{GITHUB_RAW_BASE}{info["logo"]}" />\n')
            f.write('  </channel>\n')

        for p in progs:
            m = cache.get(p['pid'])
            f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}">\n')
            f.write(f'    <title>{p["t"].replace("&", "&amp;")}</title>\n')
            if m:
                if m['sub']: f.write(f'    <sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>\n')
                if m['desc']: f.write(f'    <desc>{m["desc"].replace("&", "&amp;")}</desc>\n')
                if m['img_url']:
                    # Optional: You could also download program posters, but it fills up Git quickly.
                    f.write(f'    <icon src="{m["img_url"]}" />\n')
            f.write('  </programme>\n')
        f.write('</tv>')

if __name__ == "__main__":
    run()
