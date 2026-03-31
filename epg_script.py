import requests
import os
import sys
import re
import html
import urllib.parse
from datetime import datetime, timedelta, timezone

def log(msg):
    print(msg)
    sys.stdout.flush()

# --- Configuration ---
NID = "64377" # Change this NID to generate the guide for any UK region
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
    logo_map_id = {}
    logo_map_name = {}
    try:
        log(f"Fetching master logo list from Live API (National List: 64257)...")
        r = session.get("https://www.freeview.co.uk/api/channel-list?nid=64257", timeout=15)
        if r.status_code == 200:
            services_data = r.json().get('data', {}).get('services', [])
            for s in services_data:
                sid = str(s.get('service_id'))
                title = s.get('title', '').lower()
                family = s.get('family_alias', '').lower()
                img_url = s.get('service_image') or s.get('images', {}).get('default')
                
                if img_url:
                    logo_map_id[sid] = img_url
                    if family: 
                        logo_map_name[family] = img_url
                    if title:
                        logo_map_name[title] = img_url
                        
            # Manual fallbacks for common naming quirks
            if 'itv1' in logo_map_name:
                logo_map_name['itv'] = logo_map_name['itv1']
                logo_map_name['itv hd'] = logo_map_name['itv1']
            
            log(f"Successfully mapped Station Logos to {len(logo_map_id)} IDs and {len(logo_map_name)} Family Names.")
    except Exception as e:
        log(f"Logo map error: {e}")
    return logo_map_id, logo_map_name

def run():
    if not os.path.exists(LOGO_DIR):
        os.makedirs(LOGO_DIR)

    log(f"--- Running Freeview Guide & Universal Logo Extractor (NID: {NID}) ---")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Cookie': f'fv_location={NID}; userNid={NID}'
    })
    
    master_logos_id, master_logos_name = get_logo_map(session)

    channels, progs = {}, []
    crid_cache = {}
    
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
                    logo_url = master_logos_id.get(cid)
                    
                    # --- UNIVERSAL REGIONAL FALLBACK MATCHER ---
                    if not logo_url:
                        clean_name = chan_name.lower()
                        # 1. Try exact name match
                        if clean_name in master_logos_name:
                            logo_url = master_logos_name[clean_name]
                        else:
                            # 2. Try fuzzy family match (Universal across all UK regions)
                            for fam_name in sorted(master_logos_name.keys(), key=len, reverse=True):
                                if fam_name and fam_name in clean_name:
                                    logo_url = master_logos_name[fam_name]
                                    break
                    
                    logo_file = download_icon(logo_url, chan_name, session) if logo_url else None
                    channels[cid] = {'name': chan_name, 'logo': logo_file}
                
                for ev in chan.get('events', []):
                    try:
                        start_raw = ev.get('start_time', '')
                        start_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%S%z")
                        
                        if 'end_time' in ev:
                            end_dt = datetime.strptime(ev['end_time'], "%Y-%m-%dT%H:%M:%S%z")
                        else:
                            end_dt = start_dt + timedelta(minutes=30)

                        crid = ev.get('program_id')
                        subtitle = ''
                        desc = ''
                        
                        if crid:
                            if crid in crid_cache:
                                subtitle = crid_cache[crid]['subtitle']
                                desc = crid_cache[crid]['desc']
                            else:
                                safe_crid = urllib.parse.quote(crid, safe='')
                                safe_start = urllib.parse.quote(start_raw, safe='')
                                prog_url = f"https://www.freeview.co.uk/api/program?sid={cid}&nid=64257&pid={safe_crid}&start_time={safe_start}"
                                
                                try:
                                    pr = session.get(prog_url, timeout=5)
                                    if pr.status_code == 200:
                                        p_data = pr.json().get('data', {}).get('programs', [])
                                        if p_data:
                                            p_info = p_data[0]
                                            subtitle = p_info.get('secondary_title', '')
                                            synopses = p_info.get('synopsis', {})
                                            desc = synopses.get('medium', '') or synopses.get('short', '')
                                            crid_cache[crid] = {'subtitle': subtitle, 'desc': desc}
                                except Exception:
                                    pass

                        progs.append({
                            'cid': cid,
                            'start': start_dt.strftime('%Y%m%d%H%M%S %z'),
                            'stop': end_dt.strftime('%Y%m%d%H%M%S %z'),
                            'title': ev.get('main_title', 'Unknown'),
                            'subtitle': subtitle,
                            'desc': desc
                        })
                    except Exception as e:
                        pass
        except Exception as e:
            log(f"Error: {e}")

    log(f"Writing XML with {len(channels)} channels and {len(progs)} shows...")
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
            clean_subtitle = html.escape(p['subtitle']) if p['subtitle'] else ""
            clean_desc = html.escape(p['desc']) if p['desc'] else ""
            
            f.write(f'<programme start="{p["start"]}" stop="{p["stop"]}" channel="{p["cid"]}">\n')
            f.write(f'  <title>{clean_title}</title>\n')
            if clean_subtitle:
                f.write(f'  <sub-title>{clean_subtitle}</sub-title>\n')
            if clean_desc:
                f.write(f'  <desc>{clean_desc}</desc>\n')
            f.write('</programme>\n')
            
        f.write('</tv>')
    log("Process Complete.")

if __name__ == "__main__":
    run()
