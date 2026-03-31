import requests
import os
import sys
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
BOLTON_NID = "64257"  # Explicitly North West / Winter Hill
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"

def run():
    if not os.path.exists("logos"):
        os.makedirs("logos")

    log(f"--- Forcing Bolton/NW Guide (NID: {BOLTON_NID}) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs = {}, []
    session = requests.Session()
    # Adding a more specific header often helps the API accept the NID parameter
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebkit/537.36',
        'Referer': 'https://www.freeview.co.uk/tv-guide'
    })

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
            # We use the 'params' argument here which is more reliable for NID overrides
            payload = {'nid': BOLTON_NID, 'start': ts}
            r = session.get("https://www.freeview.co.uk/api/tv-guide", params=payload, timeout=15)
            
            if r.status_code != 200:
                log(f"Error: HTTP {r.status_code}")
                continue

            day_data = r.json().get('data', {}).get('programs', [])
            
            for chan in day_data:
                cid = chan.get('service_id')
                # Check for regional naming to confirm success
                cname = chan.get('title')
                
                if cid not in channels:
                    channels[cid] = cname
                
                for ev in chan.get('events', []):
                    progs.append({
                        'cid': cid,
                        'start': datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'),
                        'title': ev.get('main_title')
                    })
        except Exception as e:
            log(f"Error: {e}")

    log(f"Writing {len(progs)} programs. Checking first channel: {list(channels.values())[0] if channels else 'None'}")
    
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>')
        for cid, name in channels.items():
            f.write(f'<channel id="{cid}"><display-name>{name.replace("&", "&amp;")}</display-name></channel>')
        for p in progs:
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{p["title"].replace("&", "&amp;")}</title></programme>')
        f.write('</tv>')
    log("Done.")

if __name__ == "__main__":
    run()
