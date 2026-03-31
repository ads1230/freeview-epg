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
    "North_East": "64369",       # Updated!
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

# Auto-detect GitHub paths for Logo URLs
GITHUB_REPO_FULL = os.getenv('GITHUB_REPOSITORY', 'YourUsername/YourRepo')
GITHUB_USER, GITHUB_REPO = GITHUB_REPO_FULL.split('/') if '/' in GITHUB_REPO_FULL else ("Unknown", "Unknown")
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{LOGO_DIR}/"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# --- Utility Functions ---

def clean_xml_text(text):
    """Removes illegal control characters that break XML parsers."""
    if not text: return ""
    illegal_chars = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')
    return illegal_chars.sub("", str(text))

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
            r = requests.get(full_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
                log(f"   [SAVED LOGO] {filename}")
                return filename
        except:
            return None
    return filename

def get_logo_map():
    logo_map_id, logo_map_name = {}, {}
    try:
        log(f"Fetching master logo list from Live API...")
        r = requests.get("https://www.freeview.co.uk/api/channel-list?nid=64257", headers=HEADERS, timeout=15)
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
        except Exception: pass
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)
    except Exception as e:
        log(f"Cache save error: {e}")

# --- Worker Function ---

def fetch_deep_info(crid, prog_url, cookies):
    for attempt in range(2):
        try:
            r = requests.get(prog_url, headers=HEADERS, cookies=cookies, timeout=25)
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
                        
                        subs, sign, ad = False, False, False
                        events = p_info.get('events', [])
                        if events and isinstance(events, list) and len(events) > 0:
                            first_ev = events[0]
                            if isinstance(first_ev, dict):
                                access = first_ev.get('access_services')
                                if isinstance(access, dict):
                                    tv = access.get('tv', {})
                                    if isinstance(tv, dict):
                                        subs = tv.get('subtitles', False)
                                        sign = tv.get('signing', False)
                                        ad = tv.get('audio_description', False)
                        return crid, subtitle, desc, subs, sign, ad, None
                return crid, "", "", False, False, False, "Empty Data Returned"
            else:
                if attempt == 1: return crid, "", "", False, False, False, f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            if attempt == 1: return crid, "", "", False, False, False, "Timeout"
        except Exception as e:
            if attempt == 1: return crid, "", "", False, False, False, str(e)
        time.sleep(1)
    return crid, "", "", False, False, False, "Unknown Error"

# --- Main Logic ---

def run():
    if not os.path.exists(LOGO_DIR): os.makedirs(LOGO_DIR)
    
    master_logos_id, master_logos_name = get_logo_map()
    crid_cache = load_cache()
    log(f"Loaded {len(crid_cache)} shows from shared cache.")
    
    now_utc = datetime.now(timezone.utc)
    start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    for region_name, nid in REGIONS.items():
        log(f"\n=================================================")
        log(f"--- Processing Region: {region_name.replace('_', ' ')} (NID: {nid}) ---")
        log(f"=================================================")
        
        region_cookies = {f'fv_location': nid, 'userNid': nid}
        
        # --- NEW: Region Verification ---
        try:
            v_ts = int(start_of_today.timestamp())
            v_url = f"https://www.freeview.co.uk/api/tv-guide?nid={nid}&start={v_ts}"
            v_res = requests.get(v_url, headers=HEADERS, cookies=region_cookies, timeout=10)
            if v_res.status_code == 200:
                v_chans = v_res.json().get('data', {}).get('programs', [])
                v_bbc, v_itv = "not available", "not available"
                for c in v_chans:
                    c_title = c.get('title', '')
                    if "bbc one" in c_title.lower() and v_bbc == "not available": v_bbc = c_title
                    if "itv1" in c_title.lower() and v_itv == "not available": v_itv = c_title
                log(f"   [VERIFY] BBC Name: {v_bbc}")
                log(f"   [VERIFY] ITV Name: {v_itv}")
        except:
            log("   [VERIFY] Region verification skip: API Error")

        channels, progs = {}, []
        missing_crids, unique_crids = {}, set()
        
        # --- PASS 1: Build Schedule ---
        for day in range(DAYS):
            ts = int((start_of_today + timedelta(days=day)).timestamp())
            log(f"[{region_name}] Parsing Day {day+1}/8...")
            try:
                url = f"https://www.freeview.co.uk/api/tv-guide?nid={nid}&start={ts}"
                r = requests.get(url, headers=HEADERS, cookies=region_cookies, timeout=15)
                if r.status_code != 200: continue
                day_data = r.json().get('data', {}).get('programs', [])
                for chan in day_data:
                    cid = str(chan.get('service_id'))
                    chan_name = chan.get('title', 'Unknown')
                    if cid not in channels:
                        l_url = master_logos_id.get(cid) or master_logos_name.get(chan_name.lower())
                        if not l_url:
                            for fam in sorted(master_logos_name.keys(), key=len, reverse=True):
                                if fam in chan_name.lower():
                                    l_url = master_logos_name[fam]; break
                        channels[cid] = {'name': chan_name, 'logo': download_icon(l_url, chan_name)}
                    
                    for ev in chan.get('events', []):
                        try:
                            crid = ev.get('program_id')
                            title = ev.get('main_title', 'Unknown')
                            s_raw = ev.get('start_time', '')
                            s_dt = datetime.strptime(s_raw, "%Y-%m-%dT%H:%M:%S%z")
                            e_dt = datetime.strptime(ev['end_time'], "%Y-%m-%dT%H:%M:%S%z") if 'end_time' in ev else s_dt + timedelta(minutes=30)
                            
                            if crid:
                                unique_crids.add(crid)
                                if crid not in crid_cache and crid not in missing_crids:
                                    missing_crids[crid] = {
                                        'url': f"https://www.freeview.co.uk/api/program?sid={cid}&nid=64257&pid={urllib.parse.quote(crid, safe='')}&start_time={urllib.parse.quote(s_raw, safe='')}",
                                        'title': title
                                    }
                            progs.append({
                                'cid': cid, 'crid': crid, 'title': title,
                                'start': s_dt.strftime('%Y%m%d%H%M%S %z'),
                                'stop': e_dt.strftime('%Y%m%d%H%M%S %z'),
                                'image': ev.get('image_url') or ev.get('fallback_image_url') or ""
                            })
                        except: pass
            except Exception as e: log(f"Error: {e}")

        # --- PASS 2: Download Missing ---
        total_m = len(missing_crids)
        if total_m > 0:
            log(f"\n[{region_name}] FETCHING {total_m} NEW DESCRIPTIONS (4 THREADS)...")
            completed, errors, update_iv = 0, 0, max(1, total_m // 20)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_crid = {executor.submit(fetch_deep_info, c, i['url'], region_cookies): c for c, i in missing_crids.items()}
                for f in concurrent.futures.as_completed(future_to_crid):
                    crid, sub, desc, subs, sign, ad, err = f.result()
                    completed += 1
                    if err:
                        if err == "Empty Data Returned":
                            crid_cache[crid] = {'subtitle': sub, 'desc': desc, 'subs': subs, 'sign': sign, 'ad': ad}
                        else:
                            errors += 1; log(f"   [ERROR] '{missing_crids[crid]['title']}' ({crid}) - {err}")
                    else:
                        crid_cache[crid] = {'subtitle': sub, 'desc': desc, 'subs': subs, 'sign': sign, 'ad': ad}
                    if completed % update_iv == 0 or completed == total_m:
                        pct = (completed / total_m) * 100
                        bar_len = int(20 * completed // total_m)
                        bar = '█' * bar_len + '-' * (20 - bar_len)
                        log(f"[{bar}] {pct:.1f}% | {completed}/{total_m} | Errors: {errors}")
            save_cache(crid_cache)
        else: log(f"\n[{region_name}] All shows already cached!")

        # --- PASS 3: Generate XML ---
        output_file = f"freeview_{region_name.lower()}.xml"
        log(f"\n[{region_name}] Writing {output_file} with {len(channels)} channels...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
            for cid, info in channels.items():
                f.write(f'<channel id="{cid}"><display-name>{html.escape(info["name"])}</display-name>')
                if info['logo']: f.write(f'<icon src="{GITHUB_RAW_BASE}{info["logo"]}?v=1" />')
                f.write('</channel>\n')
            for p in progs:
                cache = crid_cache.get(p['crid'], {})
                title = html.escape(clean_xml_text(p['title']))
                sub = html.escape(clean_xml_text(cache.get('subtitle', '')))
                desc = html.escape(clean_xml_text(cache.get('desc', '')))
                if cache.get('ad'): desc = f"[Audio Described] {desc}" if desc else "[Audio Described]"
                
                f.write(f'<programme start="{p["start"]}" stop="{p["stop"]}" channel="{p["cid"]}">\n')
                f.write(f'  <title>{title}</title>\n')
                if sub: f.write(f'  <sub-title>{sub}</sub-title>\n')
                if p.get('image'): f.write(f'  <icon src="{html.escape(p["image"])}" />\n')
                if desc: f.write(f'  <desc>{desc}</desc>\n')
                if cache.get('subs'): f.write('  <subtitles type="onscreen" />\n')
                if cache.get('sign'): f.write('  <subtitles type="deaf-signed" />\n')
                f.write('</programme>\n')
            f.write('</tv>\n')
        log(f"[{region_name}] Complete!\n")

    log("ALL 17 REGIONS PROCESSED SUCCESSFULLY!")

if __name__ == "__main__": run()
