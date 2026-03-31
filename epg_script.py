import requests
import os
import sys
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64257"  # BOLTON / NORTH WEST
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"

def run():
    # FIX: Create logos folder so GitHub Action doesn't error out
    if not os.path.exists("logos"):
        os.makedirs("logos")
        log("Created empty logos directory to satisfy GitHub Action.")

    log(f"--- Running Fast-Bolton Guide (NID: {NID}) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs = {}, []
    
    # Using a session can help force the NID parameters correctly
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
            # We put the NID directly in the URL to ensure the API doesn't default to London
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = session.get(url, timeout=15)
            
            if r.status_code != 200:
                log(f"Error: Received HTTP {r.status_code}")
                continue

            day_data = r.json().get('data', {}).get('programs', [])
            
            for chan in day_data:
                cid = chan.get('service_id')
                if cid not in channels:
                    channels[cid] = chan.get('title')
                
                for ev in chan.get('events', []):
                    progs.append({
                        'cid': cid,
                        'start': datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'),
                        'title': ev.get('main_title')
                    })
        except Exception as e:
            log(f"Error on day {day}: {e}")

    # Write XML
    log(f"Writing {len(progs)} programs to {OUTPUT}...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>')
        for cid, name in channels.items():
            clean_name = name.replace("&", "&amp;")
            f.write(f'<channel id="{cid}"><display-name>{clean_name}</display-name></channel>')
        for p in progs:
            clean_title = p['title'].replace("&", "&amp;")
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{clean_title}</title></programme>')
        f.write('</tv>')
    log("Process finished successfully.")

if __name__ == "__main__":
    run()
