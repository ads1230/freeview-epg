import requests
import os
import sys
import re
import html
import urllib.parse
import json
import concurrent.futures
import time
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
            r = requests.get(full_url, headers=HEADERS, cookies=COOKIES, timeout=15)
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

def fetch_deep_info(crid, prog_url):
    for attempt in range(2):
        try:
            r = requests.get(prog_url, headers=HEADERS, cookies=COOKIES, timeout=25)
            if r.status_code == 200:
                p_data = r.json().get('data', {}).get('programs', [])
                
                if p_data and isinstance(p_data, list) and len(p_data) > 0:
                    p_info = p_data[0]
                    
                    if isinstance(p_info, dict):
                        subtitle = p_info.get('secondary_title', '')
                        
                        synopses = p_info.get('synopsis')
                        desc = ""
                        if isinstance(synopses, dict):
                            desc = synopses.get('medium', '') or synopses.get('short', '')
                            
                        # --- REMOVED the "No programme information" injection. We let it be blank! ---
                            
                        subs, sign, ad = False, False, False
                        events = p_info.get('events', [])
                        
                        if events and isinstance(events, list) and len(events) > 0:
                            first_event = events[0]
                            if isinstance(first_event, dict):
                                access_services = first_event.get('access_services')
                                
                                if isinstance(access_services, dict):
                                    tv_access = access_services.get('tv')
                                    if isinstance(tv_access, dict):
                                        subs = tv_access.get('subtitles', False)
                                        sign = tv_access.get('signing', False)
                                        ad = tv_access.get('audio_description', False)
                                        
                        return crid, subtitle, desc, subs, sign, ad, None
                    else:
                        return crid, "", "", False, False, False, "Empty Data Returned" 
                else:
                    return crid, "", "", False, False, False, "Empty Data Returned" 
            else:
                if attempt == 1: 
                    return crid, "", "", False, False, False, f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            if attempt == 1:
                return crid, "", "", False, False, False, "Timeout"
        except Exception as e:
            if attempt == 1:
                return crid, "", "", False, False, False, str(e)
        
        time.sleep(1)

    return crid, "", "", False, False, False, "Unknown Error"

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running TURBO Freeview Guide (NID: {NID}) ---")
    
    master_logos_id, master_logos_name = get_logo_map()
    channels, progs = {}, []
    crid_cache = load_cache()
    missing_crids = {} 
    unique_crids_in_schedule = set()
    
    log(f"Loaded {len(crid_cache)} remembered shows from cache.")
    
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # --- PASS 1: Build Schedule ---
    for day in range(DAYS):
        ts = int((start_of_today + timedelta(days=day)).timestamp())
        log(f"Parsing Day {day+1}/8...")
        try:
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={ts}"
            r = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=15)
            if r.status_code != 200:
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
                        show_title = ev.get('main_title', 'Unknown')
                        
                        # --- ADD THIS: Grab the best available image ---
                        prog_img = ev.get('image_url') or ev.get('fallback_image_url') or ""
                        
                        if crid:
                            unique_crids_in_schedule.add(crid)
                            if crid not in crid_cache and crid not in missing_crids:
                                safe_crid = urllib.parse.quote(crid, safe='')
                                safe_start = urllib.parse.quote(start_raw, safe='')
                                
                                missing_crids[crid] = {
                                    'url': f"https://www.freeview.co.uk/api/program?sid={cid}&nid=64257&pid={safe_crid}&start_time={safe_start}",
                                    'title': show_title
                                }

                        progs.append({
                            'cid': cid,
                            'start': start_dt.strftime('%Y%m%d%H%M%S %z'),
                            'stop': end_dt.strftime('%Y%m%d%H%M%S %z'),
                            'title': show_title,
                            'crid': crid,
                            'image': prog_img  # --- ADD THIS to our temporary memory ---
                        })
                    except Exception:
                        pass
        except Exception as e:
            log(f"Error: {e}")

    # --- PASS 2: Multithreaded Downloading ---
    total_missing = len(missing_crids)
    if total_missing > 0:
        log("\n--- DEEP INFO FETCHING ---")
        log(f"Total Unique Shows in Schedule : {len(unique_crids_in_schedule)}")
        log(f"Shows Already Cached         : {len(unique_crids_in_schedule) - total_missing}")
        log(f"New Shows to Download        : {total_missing}")
        log("----------------------------------")
        
        completed = 0
        error_count = 0
        update_interval = max(1, total_missing // 20)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_crid = {executor.submit(fetch_deep_info, c, info['url']): c for c, info in missing_crids.items()}
            
            for future in concurrent.futures.as_completed(future_to_crid):
                crid, subtitle, desc, subs, sign, ad, err = future.result()
                completed += 1
                
                if err:
                    show_name = missing_crids[crid]['title']
                    
                    # --- THE FIX: Silently cache empty data without logging it as an error ---
                    if err == "Empty Data Returned":
                        crid_cache[crid] = {'subtitle': subtitle, 'desc': desc, 'subs': subs, 'sign': sign, 'ad': ad}
                    else:
                        error_count += 1
                        log(f"   [ERROR] Failed to fetch '{show_name}' ({crid}) - Reason: {err}")
                else:
                    crid_cache[crid] = {'subtitle': subtitle, 'desc': desc, 'subs': subs, 'sign': sign, 'ad': ad}
                
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
            cache_data = crid_cache.get(crid, {})
            
            sub = html.escape(cache_data.get('subtitle', ''))
            desc = html.escape(cache_data.get('desc', ''))
            
            f.write(f'<programme start="{p["start"]}" stop="{p["stop"]}" channel="{p["cid"]}">\n')
            f.write(f'  <title>{clean_title}</title>\n')
            if sub: f.write(f'  <sub-title>{sub}</sub-title>\n')
            
            # --- ADD THIS: Write the show image URL for Jellyfin ---
            if p.get('image'):
                safe_img = html.escape(p['image'])
                f.write(f'  <icon src="{safe_img}" />\n')
            
            if cache_data.get('ad'):
                desc = f"[Audio Described] {desc}" if desc else "[Audio Described]"
            
            if desc: 
                f.write(f'  <desc>{desc}</desc>\n')
            
            if cache_data.get('subs'): f.write('  <subtitles type="onscreen" />\n')
            if cache_data.get('sign'): f.write('  <subtitles type="deaf-signed" />\n')
            
            f.write('</programme>\n')
            
        f.write('</tv>')
    log("Process Complete. Enjoy the Cleaner Logs!")

if __name__ == "__main__":
    run()
