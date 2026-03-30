import requests
import time
import re
from datetime import datetime, timedelta, timezone

# --- Configuration ---
NID = "64257"
DAYS = 7  # Start with 7 days to ensure success, then increase to 14 if needed
OUTPUT = "freeview_rich_14day.xml"

def get_meta(pid):
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
    # Parse: 2026-03-31T05:00:00+0000
    start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    s = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    stop_dt = start_dt + timedelta(hours=s, minutes=m)
    return stop_dt.strftime('%Y%m%d%H%M%S %z')

def run():
    # Use UTC for GitHub Actions compatibility
    now_utc = datetime.now(timezone.utc)
    # The API likes the start of the day (Midnight)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels = {}
    progs = []
    cache = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for day in range(DAYS):
        # Calculate the timestamp for Midnight of each day
        target_dt = start_of_today + timedelta(days=day)
        current_ts = int(target_dt.timestamp())
        
        url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={current_ts}"
        print(f"Attempting Day {day}: {target_dt.strftime('%Y-%m-%d')} (TS: {current_ts})")
        
        try:
            r = requests.get(url, headers=headers, timeout=20)
            res = r.json()
            
            # Navigate the specific JSON structure from your file
            day_data = res.get('data', {}).get('programs', [])
            
            if not day_data:
                print(f"   ! No programs returned for this date.")
                continue

            print(f"   + Found {len(day_data)} channels.")

            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                cname = channel_entry.get('title')
                
                if cid not in channels:
                    channels[cid] = {'name': cname}

                events = channel_entry.get('events', [])
                for event in events:
                    pid = event.get('program_id')
                    start_raw = event.get('start_time')
                    dur_raw = event.get('duration')
                    
                    # Convert to XMLTV format
                    s_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z")
                    start_xml = s_dt.strftime('%Y%m%d%H%M%S %z')
                    stop_xml = parse_duration_to_stop(start_raw, dur_raw)
                    
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.02) # Fast but safe

                    progs.append({
                        'cid': cid, 's': start_xml, 'e': stop_xml, 
                        't': event.get('main_title'), 'pid': pid
                    })
        except Exception as e:
            print(f"   ! Request failed: {e}")

    if not progs:
        print("CRITICAL: No programs were collected. XML will be empty.")
        return

    # --- Write XMLTV ---
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        f.write('<tv generator-info-name="Freeview-Github-Action">\n')
        
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}">\n')
            f.write(f'    <display-name>{info["name"]}</display-name>\n')
            f.write('  </channel>\n')

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
    print(f"Successfully created {OUTPUT} with {len(progs)} entries.")

if __name__ == "__main__":
    run()
