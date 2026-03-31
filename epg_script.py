import requests
import os
import sys
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
# Updated to your requested NID
NID = "64377" 
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"

def run():
    # Ensure the folder exists for the GitHub Action 'git add' command
    if not os.path.exists("logos"):
        os.makedirs("logos")

    log(f"--- Running Fast-Fetch Guide (NID: {NID}) ---")
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    
    channels, progs = {}, []
    session = requests.Session()
    
    # Simulate a regional user session to ensure the API respects the NID
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.freeview.co.uk/tv-guide',
        'Cookie': f'fv_location={NID}; userNid={NID}'
    })

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
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

    if channels:
        log(f"Region Check: First channel is '{list(channels.values())[0]}'")

    # Write XML
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>')
        for cid, name in channels.items():
            f.write(f'<channel id="{cid}"><display-name>{name.replace("&", "&amp;")}</display-name></channel>')
        for p in progs:
            f.write(f'<programme start="{p["start"]}" channel="{p["cid"]}"><title>{p["title"].replace("&", "&amp;")}</title></programme>')
        f.write('</tv>')
    log("Process finished successfully.")

if __name__ == "__main__":
    run()
