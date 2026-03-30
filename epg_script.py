import requests
import time
from datetime import datetime

NID = "64257"
DAYS = 14
OUTPUT = "freeview_rich_14day.xml"
SIX_HOURS = 21600

def get_meta(pid):
    try:
        r = requests.get(f"https://www.freeview.co.uk/api/more-episodes?nid={NID}&pid={pid}", timeout=5)
        if r.status_code == 200:
            d = r.json().get('data', {})
            return {
                'sn': d.get('seriesNumber'), 'en': d.get('episodeNumber'),
                'desc': d.get('description'), 'sub': d.get('episodeTitle'),
                'img': d.get('imageUrl')
            }
    except: pass
    return None

def run():
    # Use the current time, but back up 1 hour to ensure we get the current show
    start = int(time.time() // 3600 * 3600) - 3600
    end = start + (DAYS * 86400)
    channels = {}
    progs = []
    cache = {}
    curr = start

    print(f"Starting fetch at {datetime.fromtimestamp(start)}")

    while curr < end:
        try:
            # Added a proper User-Agent to prevent being blocked as a bot
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={curr}"
            
            r = requests.get(url, headers=headers, timeout=15)
            res = r.json()
            
            # Check if the API returned actual channel data
            data_channels = res.get('data', {}).get('channels', [])
            
            if not data_channels:
                print(f"No data found for chunk: {curr}")
                curr += SIX_HOURS
                continue

            for entry in data_channels:
                c = entry.get('channel', {})
                cid = c.get('id')
                if not cid: continue
                
                if cid not in channels:
                    channels[cid] = {
                        'name': c.get('name'), 
                        'lcn': c.get('lcn'), 
                        'logo': c.get('image')
                    }
                
                for p in entry.get('programs', []):
                    pid = p.get('programId') or p.get('pId')
                    # Use a unique key to prevent duplicates
                    prog_key = f"{cid}_{p['startTime']}"
                    
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05)

                    progs.append({
                        'cid': cid, 
                        's': p['startTime'], 
                        'e': p['endTime'], 
                        't': p['title'], 
                        'pid': pid,
                        'key': prog_key
                    })
            
            curr += SIX_HOURS
            print(f"Successfully fetched up to: {datetime.fromtimestamp(curr)}")
            
        except Exception as e:
            print(f"Error at {curr}: {e}")
            curr += SIX_HOURS

if __name__ == "__main__":
    run()
