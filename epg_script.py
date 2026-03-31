import requests
import os
import sys
import re
import html
import urllib.parse
import json
import concurrent.futures
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64377" 
DAYS = 8
OUTPUT = "freeview_rich_8day.xml"
LOGO_DIR = "logos"
CACHE_FILE = "crid_cache.json"

GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
COOKIES = {f'fv_location': NID, 'userNid': NID}

def make_safe_filename(name):
    if not name: return "unknown.png"
    safe = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))
    return f"{safe}.png"

def download_icon(url, channel_name):
    if not url: return None
    base_url = url.split('?')[0]
    full_url = f"{base_url}?w=800"
    
    filename = make_safe_filename(channel_name)
    local_path = os.path.join(LOGO_DIR, filename)
    
    if not os.path.exists(local_path):
        try:
            r = requests.get(full_url, headers=HEADERS, cookies=COOKIES, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SAVED] {filename}")
                return filename
        except:
            return None
    return filename

def get_logo_map():
    logo_map_id, logo_map_name = {}, {}
    try:
        log(f"Fetching master logo list from Live API (National List: 64257)...")
        r = requests.get("https://www.freeview.co.uk/api/channel-list?nid=64257", headers=HEADERS, cookies=COOKIES, timeout=15)
        if r.status_code == 200:
            services_data = r.json().get('data', {}).get('services', [])
            for s in services_data:
                sid = str(s.get('service_id'))
                title = s.get('title', '').lower()
                family = s.get('family_alias', '').lower()
                img_url = s.get('service_image') or s.get('images', {}).get('default')
                
                if img_url:
                    logo_map_id[sid] = img_url
                    if family: logo_map_name[family] = img_url
                    if title: logo_map_name[title] = img_url
                        
            if 'itv1' in logo_map_name:
                logo_map_name['itv'] = logo_map_name['itv1']
                logo_map_name['itv hd'] = logo_map_name['itv1']
            
            log(f"Successfully mapped Station Logos.")
    except Exception as e:
        log(f"Logo map error: {e}")
    return logo_map_id, logo_map_name

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)
    except Exception as e:
        log(f"Cache save error: {e}")

# --- THE MULTITHREADING WORKER WITH ERROR HANDLING ---
def fetch_deep_info(crid, prog_url):
    try:
        r = requests.get(prog_url, headers=HEADERS, cookies=COOKIES, timeout=10)
        if r.status_code == 200:
            p_data = r.json().get('data', {}).get('programs', [])
            if p_data:
                p_info = p_data[0]
                subtitle = p_info.get('secondary_title', '')
                synopses = p_info.get('synopsis', {})
                desc = synopses.get('medium', '') or synopses.get('short', '')
                return crid, subtitle, desc, None # None = No Error
            else:
                return crid, "", "", "Empty Data Returned"
        else:
            return crid, "", "", f"HTTP {r.status_code}"
    except Exception as e:
        return crid, "", "", str(e)

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running TURBO Freeview Guide (NID: {NID}) ---")
    
    master_logos_id, master_logos_name = get_logo_map()
    channels, progs = {}, []
    crid_cache = load_cache()
    missing_crids = {} 
    unique_crids_in_schedule = set() # To track total shows
    
    log(f"Loaded {len(crid_cache)} remembered shows from cache.")
    
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # --- PASS 1: Build the Schedule & Shopping List ---
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Parsing Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=15)
            if r.status_code != 200:
                log(f"   [WARNING] Skipped Day {day+1}. HTTP Status: {r.status_code}")
                continue

            day_data = r.json().get('data', {}).get('programs', [])
            for chan in day_data:
                cid = str(chan.get('service_id'))
                chan_name = chan.get('title', 'Unknown')
                
                if cid not in channels:
                    logo_url = master_logos_id.get(cid)
                    if not logo_url:
                        clean_name = chan_name.lower()
                        if clean_name in master_logos_name:
                            logo_url = master_logos_name[clean_name]
                        else:
                            for fam_name in sorted(master_logos_name.keys(), key=len, reverse=True):
                                if fam_name and fam_name in clean_name:
                                    logo_url = master_logos_name[fam_name]
                                    break
                    logo_file = download_icon(logo_url, chan_name) if logo_url else None
                    channels[cid] = {'name': chan_name, 'logo': logo_file}
                
                for ev in chan.get('events', []):
                    try:
                        start_raw = ev.get('start_time', '')
                        start_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z")
                        end_dt = datetime.strptime(ev['end_time'], "%Y-%m-%dT%H:%M:%S%z") if 'end_time' in ev else start_dt + timedelta(minutes=30)
                        
                        crid = ev.get('program_id')
                        
                        if crid:
                            unique_crids_in_schedule.add(crid)
                            if crid not in crid_cache and crid not in missing_crids:
                                safe_crid = urllib.parse.quote(crid, safe='')
                                safe_start = urllib.parse.quote(start_raw, safe='')
                                missing_crids[crid] = f"https://www.freeview.co.uk/api/program?sid={cid}&nid=64257&pid={safe_crid}&start_time={safe_start}"

                        progs.append({
                            'cid': cid,
                            'start': start_dt.strftime('%Y%m%d%H%M%S %z'),
                            'stop': end_dt.strftime('%Y%m%d%H%M%S %z'),
                            'title': ev.get('main_title', 'Unknown'),
                            'crid': crid
                        })
                    except Exception:
                        pass
        except Exception as e:
            log(f"Error: {e}")

    # --- PASS 2: Multithreaded Downloading with Progress Bar ---
    total_missing = len(missing_crids)
    if total_missing > 0:
        log("\n--- DEEP INFO FETCHING ---")
        log(f"Total Unique Shows in Schedule : {len(unique_crids_in_schedule)}")
        log(f"Shows Already Cached         : {len(unique_crids_in_schedule) - total_missing}")
        log(f"New Shows to Download        : {total_missing}")
        log("----------------------------------")
        
        completed = 0
        error_count = 0
        
        # Calculate how often to update the progress bar (roughly every 5%)
        update_interval = max(1, total_missing // 20)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_crid = {executor.submit(fetch_deep_info, c, u): c for c, u in missing_crids.items()}
            
            for future in concurrent.futures.as_completed(future_to_crid):
                crid, subtitle, desc, err = future.result()
                completed += 1
                
                if err:
                    error_count += 1
                    log(f"   [ERROR] Failed to fetch {crid} - Reason: {err}")
                elif subtitle or desc:
                    crid_cache[crid] = {'subtitle': subtitle, 'desc': desc}
                
                # Print the visual progress bar
                if completed % update_interval == 0 or completed == total_missing:
                    percent = (completed / total_missing) * 100
                    filled_blocks = int(20 * completed // total_missing)
                    bar = '█' * filled_blocks + '-' * (20 - filled_blocks)
                    log(f"[{bar}] {percent:.1f}% | Fetched: {completed}/{total_missing} | Errors: {error_count}")
        
        save_cache(crid_cache)
        log(f"\nSaved {len(crid_cache)} total shows to persistent cache.")
    else:
        log("\nAll shows are already in the cache! Skipping download phase.")

    # --- PASS 3: Generate the XML ---
    log(f"\nWriting XML with {len(channels)} channels and {len(progs)} shows...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv>\n')
        
        for cid, info in channels.items():
            clean_name = html.escape(info['name'])
            f.write(f'<channel id="{cid}"><display-name>{clean_name}</display-name>')
            if info['logo']:
                f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}?v=1" />')
            f.write('</channel>\n')
            
        for p in progs:
            clean_title = html.escape(p['title'])
            
            crid = p.get('crid')
            sub = html.escape(crid_cache[crid]['subtitle']) if crid and crid in crid_cache and 'subtitle' in crid_cache[crid] else ""
            desc = html.escape(crid_cache[crid]['desc']) if crid and crid in crid_cache and 'desc' in crid_cache[crid] else ""
            
            f.write(f'<programme start="{p["start"]}" stop="{p["stop"]}" channel="{p["cid"]}">\n')
            f.write(f'  <title>{clean_title}</title>\n')
            if sub: f.write(f'  <sub-title>{sub}</sub-title>\n')
            if desc: f.write(f'  <desc>{desc}</desc>\n')
            f.write('</programme>\n')
            
        f.write('</tv>')
    log("Process Complete. Enjoy the Speed!")

if __name__ == "__main__":
    run()
