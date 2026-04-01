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
DAYS = 8
LOGO_DIR = "logos"
CACHE_FILE = "crid_cache.json"

# Your custom UK Region Map! (100% Unique - 17 Regions)
REGIONS = {
    "London": "64257",
    "East_Midlands": "64345",
    "West_Midlands": "64337",
    "North_West": "64377",
    "North_East": "64369",
    "Yorkshire": "64364",
    "East_Yorkshire": "64353",
    "East_Anglia": "64305",
    "South": "64273",
    "South_East": "64280",
    "South_West": "64328",
    "West": "64321",
    "Scotland": "64405",
    "Wales": "64417",
    "Northern_Ireland": "64425",
    "Channel_Islands": "64334",
    "Border": "64385"
}

# --- GitHub Integration ---
GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# --- Utility Functions ---

def clean_xml_text(text):
    if not text: return ""
    illegal_chars = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')
    return illegal_chars.sub("", str(text))

def download_icon(url, name):
    if not url: return None
    safe_name = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_')) + ".png"
    local_path = os.path.join(LOGO_DIR, safe_name)
    if not os.path.exists(local_path):
        try:
            # Append w=800 for high quality channel logos
            r = requests.get(url.split('?')[0] + "?w=800", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f: f.write(r.content)
                return safe_name
        except: return None
    return safe_name

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

# --- Threaded Worker for Freeview ---

def fetch_deep_info(crid, prog_url, cookies):
    """Worker function to hit the Freeview program details API."""
    for attempt in range(2):
        try:
            r = requests.get(prog_url, headers=HEADERS, cookies=cookies, timeout=20)
            if r.status_code == 200:
                p_data = r.json().get('data', {}).get('programs', [])
                if p_data:
                    p = p_data[0]
                    syn = p.get('synopsis', {})
                    # Extract access services (Subtitles, Sign Language, AD)
                    access = p.get('events', [{}])[0].get('access_services', {}).get('tv', {})
                    return crid, {
                        'sub': p.get('secondary_title', ''),
                        'desc': syn.get('medium', '') or syn.get('short', ''),
                        'subs': access.get('subtitles', False),
                        'sign': access.get('signing', False),
                        'ad': access.get('audio_description', False)
                    }, None
            return crid, {}, f"HTTP {r.status_code}"
        except Exception as e:
            if attempt == 1: return crid, {}, str(e)
            time.sleep(1)
    return crid, {}, "Error"

# --- Main Logic ---

def run(target_region=None):
    if not os.path.exists(LOGO_DIR): os.makedirs(LOGO_DIR)
    meta_cache = load_cache()
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # Matrix Filtering: Only process the region passed via CLI
    items = [(target_region, REGIONS[target_region])] if target_region in REGIONS else REGIONS.items()

    for region_name, nid in items:
        log(f"\n=================================================")
        log(f"--- Processing Freeview: {region_name} (NID: {nid}) ---")
        log(f"=================================================")
        
        cookies = {'fv_location': nid, 'userNid': nid}
        
        # [VERIFY] Check BBC/ITV regional names
        try:
            v_url = f"https://www.freeview.co.uk/api/tv-guide?nid={nid}&start={int(start_of_today.timestamp())}"
            v_res = requests.get(v_url, headers=HEADERS, cookies=cookies, timeout=10)
            if v_res.status_code == 200:
                v_chans = v_res.json().get('data', {}).get('programs', [])
                v_bbc = next((c['title'] for c in v_chans if "bbc one" in c['title'].lower()), "N/A")
                v_itv = next((c['title'] for c in v_chans if "itv1" in c['title'].lower()), "N/A")
                log(f"   [VERIFY] BBC: {v_bbc} | ITV: {v_itv}")
        except: pass

        channels, progs, missing_crids = {}, [], {}

        # PASS 1: Build Schedule
        for day in range(DAYS):
            ts = int((start_of_today + timedelta(days=day)).timestamp())
            log(f"[{region_name}] Parsing Day {day+1}/8...")
            try:
                r = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={nid}&start={ts}", headers=HEADERS, cookies=cookies)
                if r.status_code != 200: continue
                for chan in r.json().get('data', {}).get('programs', []):
                    cid = str(chan.get('service_id'))
                    if cid not in channels:
                        channels[cid] = {'name': chan['title'], 'logo': download_icon(chan.get('service_image'), chan['title'])}
                    
                    for ev in chan.get('events', []):
                        crid = ev.get('program_id')
                        if crid and crid not in meta_cache:
                            # Build the deep-info URL
                            missing_crids[crid] = f"https://www.freeview.co.uk/api/program?sid={cid}&nid={nid}&pid={urllib.parse.quote(crid)}&start_time={urllib.parse.quote(ev['start_time'])}"
                        
                        progs.append({
                            'cid': cid, 'crid': crid, 't': ev.get('main_title'), 'img': ev.get('image_url'),
                            's': datetime.strptime(ev['start_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z'),
                            'e': datetime.strptime(ev['end_time'], "%Y-%m-%dT%H:%M:%S%z").strftime('%Y%m%d%H%M%S %z')
                        })
            except Exception as e: log(f"   ! Error parsing day: {e}")

        # PASS 2: Threaded Metadata Download
        total_m = len(missing_crids)
        if total_m > 0:
            log(f"\n[{region_name}] FETCHING {total_m} FREEVIEW DESCRIPTIONS (4 THREADS)...")
            completed, update_iv = 0, max(1, total_m // 20)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(fetch_deep_info, c, u, cookies) for c, u in missing_crids.items()]
                for f in concurrent.futures.as_completed(futures):
                    c, data, err = f.result()
                    completed += 1
                    if not err: meta_cache[c] = data
                    if completed % update_iv == 0 or completed == total_m:
                        log(f"   Progress: {(completed/total_m)*100:.1f}% ({completed}/{total_m})")
            # Save cache after each region to prevent loss
            with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(meta_cache, f)
        else: log(f"[{region_name}] All metadata cached.")

        # PASS 3: Generate Regional XML
        output_file = f"freeview_{region_name.lower()}.xml"
        log(f"[{region_name}] Writing {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
            for cid, info in channels.items():
                name = html.escape(clean_xml_text(info['name']))
                f.write(f'  <channel id="{cid}"><display-name>{name}</display-name>')
                if info['logo']: f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}" />')
                f.write('</channel>\n')
            
            for p in progs:
                m = meta_cache.get(p['crid'], {})
                title = html.escape(clean_xml_text(p['t']))
                f.write(f'  <programme start="{p["s"]}" stop="{p["e"]}" channel="{p["cid"]}">\n')
                f.write(f'    <title>{title}</title>\n')
                if m.get('sub'): f.write(f'    <sub-title>{html.escape(clean_xml_text(m["sub"]))}</sub-title>\n')
                
                desc = clean_xml_text(m.get('desc', ''))
                if m.get('ad'): desc = f"[Audio Described] {desc}" if desc else "[Audio Described]"
                if desc: f.write(f'    <desc>{html.escape(desc)}</desc>\n')
                
                # Image logic with ?w=800
                if p.get('img'):
                    img_url = p['img']
                    if "w=" not in img_url:
                        img_url += ("&" if "?" in img_url else "?") + "w=800"
                    f.write(f'    <icon src="{html.escape(img_url)}" />\n')
                
                if m.get('subs'): f.write('    <subtitles type="onscreen" />\n')
                if m.get('sign'): f.write('    <subtitles type="deaf-signed" />\n')
                f.write('  </programme>\n')
            f.write('</tv>\n')

if __name__ == "__main__":
    # Check if a region was passed as an argument: python epg_script.py London
    region_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(region_arg)
