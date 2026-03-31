import requests
import os
import sys
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

NID = "64257" # Bolton
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"

# We skip the "get_meta" function entirely to stop the hanging

def run():
    log(f"--- Running Fast-Bolton Guide (No Metadata) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs = {}, []
    
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}...")
        try:
            r = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}", timeout=15)
            day_data = r.json().get('data', {}).get('programs', [])
            
            for chan in day_data:
                cid = chan.get('service_id')
                if cid not in channels:
                    channels[cid] = chan.get('title')
                
                for ev in chan.get('events', []):
                    # Basic data only to ensure it finishes in seconds, not hours
                    progs.append({
                        'cid': cid,
                        'start': datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'),
                        'title': ev.get('main_title')
                    })
        except Exception as e:
            log(f"Error: {e}")

    # Write simple XML
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><tv>')
        for cid, name in channels.items():
            f.write(f'<channel id="{cid}"><display-name>{name}</display-name></channel>')
        for p in progs:
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{p["title"]}</title></programme>')
        f.write('</tv>')
    log("Done! Check your repo for the file.")

if __name__ == "__main__":
    run()
