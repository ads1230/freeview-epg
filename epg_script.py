import requests
import time
from datetime import datetime, timedelta
import isodate # You may need to: pip install isodate

# --- Configuration ---
NID = "64257"
DAYS = 14
OUTPUT = "freeview_24h_14day.xml"

def get_meta(pid):
    """Fetches rich episode info (remains the same as previous)"""
    try:
        r = requests.get(f"https://www.freeview.co.uk/api/more-episodes?nid={NID}&pid={pid}", timeout=5)
        if r.status_code == 200:
            d = r.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 'en': d.get('episodeNumber'),
                'desc': d.get('description'), 'sub': d.get('episodeTitle'),
                'img': d.get('imageUrl')
            }
    except: pass
    return None

def parse_duration(start_str, duration_iso):
    """Converts ISO8601 duration (PT3H30M) to a stop timestamp."""
    start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
    duration = isodate.parse_duration(duration_iso)
    stop_dt = start_dt + duration
    return stop_dt.strftime('%Y%m%d%H%M%S %z')

def run():
    # Set the start to 05:00:00 today (matching the sample file's typical start)
    now = datetime.now()
    start_dt = datetime(now.year, now.month, now.day, 5, 0, 0)
    
    channels = {}
    progs = []
    cache = {}

    headers = {'User-Agent': 'Mozilla/5.0'}

    for day in range(DAYS):
        current_ts = int((start_dt + timedelta(days=day)).timestamp())
        url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={current_ts}"
        print(f"Fetching 24h block for: {datetime.fromtimestamp(current_ts)}")
        
        try:
            res = requests.get(url, headers=headers, timeout=15).json()
            # The structure from your file: data -> programs -> [service_id, title, events]
            day_data = res.get('data', {}).get('programs', [])
            
            for channel_entry in day_data:
                cid = channel_entry.get('service_id')
                cname = channel_entry.get('title')
                
                if cid not in channels:
                    channels[cid] = {'name': cname}

                for event in channel_entry.get('events', []):
                    pid = event.get('program_id')
                    start_raw = event.get('start_time')
                    duration_raw = event.get('duration')
                    
                    # Convert timestamps for XMLTV
                    start_xml = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z')
                    stop_xml = parse_duration(start_raw, duration_raw)
                    
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05)

                    progs.append({
                        'cid': cid, 
                        's': start_xml, 
                        'e': stop_xml, 
                        't': event.get('main_title'), 
                        'pid': pid
                    })
        except Exception as e:
            print(f"Error on day {day}: {e}")

    # --- Write XML ---
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

if __name__ == "__main__":
    run()
