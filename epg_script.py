import requests
import os
import sys
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64377" 
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"

GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

def make_safe_filename(name):
    if not name: return "unknown.png"
    safe = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))
    return f"{safe}.png"

def download_icon(url, channel_name, session):
    if not url: return None
    base_url = url.split('?')[0]
    full_url = f"{base_url}?w=800"
    
    filename = make_safe_filename(channel_name)
    local_path = os.path.join(LOGO_DIR, filename)
    
    if not os.path.exists(local_path):
        try:
            r = session.get(full_url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SAVED] {filename}")
                return filename
        except:
            return None
    return filename

def get_logo_map(session):
    logo_map = {}
    try:
        log(f"Fetching master logo list from Live API (NID: 64257)...")
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        if r.status_code == 200:
            services_data = r.json().get('data', {}).get('services', [])
            for s in services_data:
                sid = str(s.get('service_id'))
                img_url = s.get('service_image') or s.get('images', {}).get('default')
                if img_url:
                    logo_map[sid] = img_url
            log(f"Successfully mapped {len(logo_map)} Station Logos.")
    except Exception as e:
        log(f"Logo map error: {e}")
    return logo_map

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running North West Guide (NID: {NID}) ---")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie': f'fv_location={NID}; userNid={NID}'
    })
    
    master_logos = get_logo_map(session)

    channels, progs = {}, []
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Fetching Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = session.get(url, timeout=15)
            if r.status_code != 200: continue

            day_data = r.json().get('data', {}).get('programs', [])
            for chan in day_data:
                cid = str(chan.get('service_id'))
                chan_name = chan.get('title', 'Unknown')
                
                if cid not in channels:
                    logo_url = master_logos.get(cid)
                    logo_file = download_icon(logo_url, chan_name, session) if logo_url else None
                    channels[cid] = {'name': chan_name, 'logo': logo_file}
                
                for ev in chan.get('events', []):
                    try:
                        # Grab both start AND end times so Jellyfin can draw the grid blocks
                        start_dt = datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z")
                        
                        if 'end_time' in ev:
                            end_dt = datetime.strptime(ev['end_time'], "%Y-%m-%dT%H:%M:%S%z")
                        else:
                            end_dt = start_dt + timedelta(minutes=30) # Safe fallback

                        progs.append({
                            'cid': cid,
                            'start': start_dt.strftime('%Y%m%d%H%M%S %z'),
                            'stop': end_dt.strftime('%Y%m%d%H%M%S %z'),
                            'title': ev.get('main_title', 'Unknown'),
                            'desc': ev.get('synopsis', '')
                        })
                    except Exception as e:
                        pass # Skip broken dates safely
        except Exception as e:
            log(f"Error: {e}")

    log(f"Writing XML with {len(channels)} channels and {len(progs)} shows...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>\n')
        
        for cid, info in channels.items():
            clean_name = info['name'].replace("&", "&amp;").replace("<", "&lt;")
            f.write(f'<channel id="{cid}"><display-name>{clean_name}</display-name>')
            if info['logo']:
                f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
            f.write('</channel>\n')
            
        for p in progs:
            clean_title = p['title'].replace("&", "&amp;").replace("<", "&lt;")
            clean_desc = p['desc'].replace("&", "&amp;").replace("<", "&lt;")
            f.write(f'<programme start="{p["start"]}" stop="{p["stop"]}" channel="{p["cid"]}">')
            f.write(f'<title>{clean_title}</title>')
            if clean_desc:
                f.write(f'<desc>{clean_desc}</desc>')
            f.write('</programme>\n')
            
        f.write('</tv>')
    log("Process Complete.")

if __name__ == "__main__":
    run()
