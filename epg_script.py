import requests
import time
import re
from datetime import datetime, timedelta, timezone

# --- Configuration ---
NID = "64257"
DAYS = 8  # Adjusted to 8 based on testing
OUTPUT = "freeview_rich_14day.xml"

def get_meta(pid):
    """Fetches rich episode metadata from the more-episodes endpoint."""
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
    """Parses ISO 8601 duration (PT3H30M) into a stop time string."""
    start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    stop_dt = start_dt + timedelta(hours=h, minutes=m)
    return stop_dt.strftime('%Y%m%d%H%M%S %z')

def run():
    now_utc = datetime.now(timezone.utc)
    # Anchor to Midnight UTC to match the 24h block structure
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels = {}
    progs = []
    cache = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitHub-Action-EPG'}

    for day in range(DAYS):
        target_dt = start_of_today + timedelta(days=day)
        current_ts = int(target_dt.timestamp())
        url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={current_ts}"
        
        print(f"Fetching Day {day+1}/{DAYS}: {target_dt.strftime('%Y-%m-%d')}")
        
        try:
            r = requests.get(url, headers=headers, timeout=20)
            res = r.json()
            day_data = res.get('data', {}).get('programs', [])
            
            if not day_data:
                print(f"   ! No data returned for this day.")
                continue

            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                cname = channel_entry.get('title')
                
                if cid not in channels:
                    channels[cid] = {'name': cname}

                for event in channel_entry.get('events', []):
                    pid = event.get('program_id')
                    start_raw = event.get('start_time')
                    dur_raw = event.get('duration')
                    
                    # Convert timestamps for XMLTV
                    s_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z")
                    start_xml = s_dt.strftime('%Y%m%d%H%M%S %z')
                    stop_xml = parse_duration_to_stop(start_raw, dur_raw)
                    
                    # Check cache for rich info
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05) # Throttle to prevent API lockout

                    progs.append({
                        'cid': cid, 's': start_xml, 'e': stop_xml, 
                        't': event.get('main_title'), 'pid': pid
                    })
        except Exception as e:
            print(f"   ! Error: {e}")

    if not progs:
        print("Error: No programs collected. Script will not write empty file.")
        return

    # --- Write XMLTV ---
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        f.write('<tv generator-info-name="Freeview-Action-Scraper">\n')
        
        # Write Channel info
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}">\n')
            f.write(f'    <display-name>{info["name"]}</display-name>\n')
            f.write('  </channel>\n')

        # Write Programme info
        for p in progs:
            m = cache.get(p['pid'])
            f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}">\n')
            f.write(f'    <title>{p["t"].replace("&", "&amp;").replace("<", "&lt;")}</title>\n')
            
            if m:
                if m.get('sub'): f.write(f'    <sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>\n')
                if m.get('desc'): f.write(f'    <desc>{m["desc"].replace("&", "&amp;")}</desc>\n')
                if m.get('img'): f.write(f'    <icon src="{m["img"]}" />\n')
                if m.get('sn') and m.get('en'): 
                    f.write(f'    <episode-num system="onscreen">S{m["sn"]} E{m["en"]}</episode-num>\n')
            f.write('  </programme>\n')
        f.write('</tv>')
    print(f"Successfully generated {OUTPUT} with {len(progs)} entries.")

if __name__ == "__main__":
    run()
