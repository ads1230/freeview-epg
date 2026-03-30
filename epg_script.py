import requests
import time
import re
from datetime import datetime, timedelta

# --- Configuration ---
NID = "64257"
DAYS = 14
OUTPUT = "freeview_rich_14day.xml"

def get_meta(pid):
    """Fetches rich episode info and remote image URLs."""
    try:
        params = {'nid': NID, 'pid': pid}
        resp = requests.get(f"https://www.freeview.co.uk/api/more-episodes", params=params, timeout=5)
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 
                'en': d.get('episodeNumber'),
                'desc': d.get('description'), 
                'sub': d.get('episodeTitle'),
                'img': d.get('imageUrl')
            }
    except:
        pass
    return None

def parse_duration_to_stop(start_str, duration_str):
    """
    Parses ISO 8601 duration (e.g., PT3H30M) and returns XMLTV stop time.
    Uses regex to avoid 'isodate' dependency.
    """
    # Parse the start time: 2026-03-31T05:00:00+0000
    start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
    
    # Extract Hours, Minutes, Seconds using Regex
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+)S', duration_str)
    
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    
    stop_dt = start_dt + timedelta(hours=h, minutes=m, seconds=s)
    return stop_dt.strftime('%Y%m%d%H%M%S %z')

def run():
    # Start from 05:00 today (matches typical Freeview daily start)
    now = datetime.now()
    start_dt = datetime(now.year, now.month, now.day, 5, 0, 0)
    
    channels = {}
    progs = []
    cache = {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    for day in range(DAYS):
        current_dt = start_dt + timedelta(days=day)
        current_ts = int(current_dt.timestamp())
        url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={current_ts}"
        
        print(f"Fetching Day {day+1}/{DAYS}: {current_dt.strftime('%Y-%m-%d')}")
        
        try:
            r = requests.get(url, headers=headers, timeout=15)
            res = r.json()
            day_data = res.get('data', {}).get('programs', [])
            
            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                cname = channel_entry.get('title')
                
                if cid not in channels:
                    channels[cid] = {'name': cname}

                for event in channel_entry.get('events', []):
                    pid = event.get('program_id')
                    start_raw = event.get('start_time') # 2026-03-31T05:00:00+0000
                    dur_raw = event.get('duration')     # PT3H30M
                    
                    # Formatting for XMLTV
                    s_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z")
                    start_xml = s_dt.strftime('%Y%m%d%H%M%S %z')
                    stop_xml = parse_duration_to_stop(start_raw, dur_raw)
                    
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05)

                    progs.append({
                        'cid': cid, 's': start_xml, 'e': stop_xml, 
                        't': event.get('main_title'), 'pid': pid
                    })
        except Exception as e:
            print(f"Error fetching day {day}: {e}")

    # --- Write XMLTV ---
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}">\n')
            f.write(f'    <display-name>{info["name"]}</display-name>\n')
            f.write('  </channel>\n')

        for p in progs:
            m = cache.get(p['pid'])
            f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}">\n')
            f.write(f'    <title>{p["t"].replace("&", "&amp;")}</title>\n')
            if m:
                if m['sub']: f.write(f'    <sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>\n')
                if m['desc']: f.write(f'    <desc>{m["desc"].replace("&", "&amp;")}</desc>\n')
                if m['img']: f.write(f'    <icon src="{m["img"]}" />\n')
                if m['sn'] and m['en']: 
                    f.write(f'    <episode-num system="onscreen">S{m["sn"]} E{m["en"]}</episode-num>\n')
            f.write('  </programme>\n')
        f.write('</tv>')
    print(f"Done! Created {OUTPUT}")

if __name__ == "__main__":
    run()
