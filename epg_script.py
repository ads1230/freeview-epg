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
    start = int(time.time() // 3600 * 3600)
    end = start + (DAYS * 86400)
    channels = {}
    progs = []
    cache = {}
    curr = start

    while curr < end:
        try:
            res = requests.get(f"https://www.freeview.co.uk/api/tv-guide?nid={NID}&start={curr}", timeout=10).json()
            for entry in res.get('data', {}).get('channels', []):
                c = entry['channel']
                cid = c['id']
                if cid not in channels:
                    channels[cid] = {'name': c['name'], 'lcn': c.get('lcn'), 'logo': c.get('image')}
                
                for p in entry.get('programs', []):
                    pid = p.get('programId') or p.get('pId')
                    if pid and pid not in cache:
                        cache[pid] = get_meta(pid)
                        time.sleep(0.05)
                    progs.append({'cid': cid, 's': p['startTime'], 'e': p['endTime'], 't': p['title'], 'pid': pid})
            curr += SIX_HOURS
        except: curr += SIX_HOURS

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for cid, info in channels.items():
            f.write(f'  <channel id="{cid}">\n    <display-name>{info["name"]}</display-name>\n')
            if info["lcn"]: f.write(f'    <display-name>{info["lcn"]}</display-name>\n')
            if info["logo"]: f.write(f'    <icon src="{info["logo"]}" />\n')
            f.write('  </channel>\n')
        for p in progs:
            m = cache.get(p['pid'])
            st = datetime.fromtimestamp(int(p['s'])).strftime('%Y%m%d%H%M%S +0000')
            et = datetime.fromtimestamp(int(p['e'])).strftime('%Y%m%d%H%M%S +0000')
            f.write(f'  <programme start="{st}" stop="{et}" channel="{p["cid"]}">\n')
            f.write(f'    <title>{p["t"].replace("&", "&amp;")}</title>\n')
            if m:
                if m['sub']: f.write(f'    <sub-title>{m["sub"].replace("&", "&amp;")}</sub-title>\n')
                if m['desc']: f.write(f'    <desc>{m["desc"].replace("&", "&amp;")}</desc>\n')
                if m['img']: f.write(f'    <icon src="{m["img"]}" />\n')
                if m['sn'] and m['en']: f.write(f'    <episode-num system="onscreen">S{m["sn"]} E{m["en"]}</episode-num>\n')
            f.write('  </programme>\n')
        f.write('</tv>')

if __name__ == "__main__":
    run()
