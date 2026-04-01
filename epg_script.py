import requests
import os
import sys
import re
import html
import urllib.parse
import json
import concurrent.futures
import time
import random
from datetime import datetime, timedelta, timezone

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")
    sys.stdout.flush()

# --- Configuration ---
DAYS = 8
LOGO_DIR = "logos"
CACHE_FILE = "crid_cache.json"

REGIONS = {
    "London": "64257", "East_Midlands": "64345", "West_Midlands": "64337",
    "North_West": "64377", "North_East": "64369", "Yorkshire": "64364",
    "East_Yorkshire": "64353", "East_Anglia": "64305", "South": "64273",
    "South_East": "64280", "South_West": "64328", "West": "64321",
    "Scotland": "64405", "Wales": "64417", "Northern_Ireland": "64425",
    "Channel_Islands": "64334", "Border": "64385"
}

GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]
HEADERS = {'User-Agent': random.choice(UAS)}

def clean_xml_text(text):
    if not text: return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]', "", str(text))

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

def fetch_deep_info(crid, prog_url, cookies):
    try:
        r = requests.get(prog_url, headers=HEADERS, cookies=cookies, timeout=15)
        if r.status_code == 200:
            p_data = r.json().get('data', {}).get('programs', [])
            if p_data:
                p = p_data[0]
                syn = p.get('synopsis', {})
                access = p.get('events', [{}])[0].get('access_services', {}).get('tv', {})
                return crid, {'sub': p.get('secondary_title', ''), 'desc': syn.get('medium', '') or syn.get('short', ''), 'subs': access.get('subtitles', False), 'ad': access.get('audio_description', False)}, 200
        return crid, {}, r.status_code
    except Exception as e: return crid, {}, str(e)

def run(target_region=None):
    if not os.path.exists(LOGO_DIR): os.makedirs(LOGO_DIR)
    meta_cache = load_cache()
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    items = [(target_region, REGIONS[target_region])] if target_region in REGIONS else REGIONS.items()

    for region_name, nid in items:
        log(f"--- REGION: {region_name} (Freeview) ---")
        cookies = {'fv_location': nid, 'userNid': nid}
        channels, progs, missing_crids = {}, [], {}

        # PASS 1: Build Schedule
        for day in range(DAYS):
            ts = int((start_of_today + timedelta(days=day)).timestamp())
            try:
                r = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={nid}&start={ts}", headers=HEADERS, cookies=cookies, timeout=15)
                if r.status_code != 200: 
                    log(f"   [ERROR] Pass 1 Failed on Day {day+1}: HTTP {r.status_code}")
                    continue
                
                day_chans = r.json().get('data', {}).get('programs', [])
                log(f"   [INFO] Day {day+1} parsed successfully ({len(day_chans)} channels).")
                
                for chan in day_chans:
                    cid = str(chan.get('service_id'))
                    if cid not in channels: channels[cid] = {'name': chan.get('title', 'Unknown')}
                    
                    for ev in chan.get('events', []):
                        show_title = ev.get('main_title', 'Unknown')
                        try:
                            crid = ev.get('program_id')
                            start_str = ev.get('start_time')
                            duration_str = ev.get('duration') # e.g. "PT1H30M"
                            
                            if not crid or not start_str or not duration_str: 
                                log(f"   [WARNING] Missing essential data for show '{show_title}'. Skipping.")
                                continue
                                
                            start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z")
                            s_time = start_dt.strftime('%Y%m%d%H%M%S %z')
                            
                            h_match = re.search(r'(\d+)H', duration_str)
                            m_match = re.search(r'(\d+)M', duration_str)
                            h = int(h_match.group(1)) if h_match else 0
                            m = int(m_match.group(1)) if m_match else 0
                            e_time = (start_dt + timedelta(hours=h, minutes=m)).strftime('%Y%m%d%H%M%S %z')
                            
                            if crid not in meta_cache:
                                missing_crids[crid] = f"https://www.freeview.co.uk/api/program?sid={cid}&nid={nid}&pid={urllib.parse.quote(crid)}&start_time={urllib.parse.quote(start_str)}"
                            
                            progs.append({
                                'cid': cid, 'crid': crid, 't': show_title, 
                                'img': ev.get('image_url', ''), 's': s_time, 'e': e_time
                            })
                        except Exception as e: 
                            log(f"   [WARNING] Parsing error for show '{show_title}': {e}")
            except Exception as e: log(f"   [CRITICAL] Error parsing day {day+1}: {e}")

        # PASS 2: Metadata 
        total_missing_list = list(missing_crids.items())
        total_to_fetch = len(total_missing_list)
        
        if total_to_fetch > 0:
            log(f"FETCHING {total_to_fetch} metadata items...")
            completed, success_count, blocked_count = 0, 0, 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(fetch_deep_info, c, u, cookies) for c, u in total_missing_list]
                for f in concurrent.futures.as_completed(futures):
                    crid, data, status = f.result()
                    completed += 1
                    
                    if status == 200:
                        meta_cache[crid] = data
                        success_count += 1
                    elif status == 404:
                        meta_cache[crid] = {}
                        success_count += 1
                    elif status in [403, 429]: blocked_count += 1
                    else: log(f"   [WARNING] API returned {status} for ID: {crid}")

                    update_iv = max(1, total_to_fetch // 20)
                    if completed % update_iv == 0 or completed == total_to_fetch:
                        pct = completed / total_to_fetch
                        bar_len = 20
                        filled = int(bar_len * pct)
                        bar = '█' * filled + '-' * (bar_len - filled)
                        log(f"   Progress: [{bar}] {pct*100:.1f}% ({completed}/{total_to_fetch}) | Success: {success_count} | Blocks: {blocked_count}")
                    
                    if blocked_count >= 5:
                        log("CRITICAL: Multiple blocks detected. Stopping to save cache.")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

            with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(meta_cache, f)
        else: log("All shows in this region are already cached.")
        
        # PASS 3: Generate XML
        output_file = f"freeview_{region_name.lower()}.xml"
        log(f"Writing {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><tv>\n')
            for cid, info in channels.items():
                f.write(f'  <channel id="{cid}"><display-name>{html.escape(info["name"])}</display-name></channel>\n')
            for p in progs:
                m = meta_cache.get(p['crid'], {})
                f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}">\n')
                f.write(f'    <title>{html.escape(clean_xml_text(p["t"]))}</title>\n')
                if m.get('sub'): f.write(f'    <sub-title>{html.escape(clean_xml_text(m["sub"]))}</sub-title>\n')
                
                desc = clean_xml_text(m.get('desc', ''))
                if m.get('ad'): desc = f"[AD] {desc}" if desc else "[AD]"
                if desc: f.write(f'    <desc>{html.escape(desc)}</desc>\n')
                
                if p['img']: f.write(f'    <icon src="{html.escape(p["img"])}?w=800" />\n')
                if m.get('subs'): f.write('    <subtitles type="onscreen" />\n')
                f.write('  </programme>\n')
            f.write('</tv>')

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
