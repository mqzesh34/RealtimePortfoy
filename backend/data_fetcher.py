import socketio
import json
import threading
import time
import os
import asyncio
import websockets
import random
import string
import requests
from datetime import datetime, timedelta

socket = socketio.Client()

URL = 'https://socket.haremaltin.com'
ORIGIN = 'https://canlipiyasalar.haremaltin.com'
DAILY_HISTORY = 'data/daily_history.json'
LIVE_DATA = 'data/live_data.json'

if not os.path.exists('data'):
    os.makedirs('data')

HAREM_SYMBOLS = {
    'KULCEALTIN': 'Gram Altın'
}

TV_SYMBOLS = {
    'TVC:GOLD':      'Altın Ons',
    'TVC:SILVER':    'Gümüş Ons',
}

TEFAS_SYMBOLS = {
    'PHE': ('PHE Yatırım Fonu', 'YAT')
}


last_saved_minute = -1
full_data = {}
data_lock = threading.Lock()
last_write_time = 0
WRITE_INTERVAL = 1.0

def write_live():
    global last_write_time
    now = time.time()
    if now - last_write_time < WRITE_INTERVAL:
        return
    last_write_time = now

    with data_lock:
        output = list(full_data.values())
    with open(LIVE_DATA, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
    print(f"✅[{datetime.now().strftime('%H:%M:%S')}]")

def history_saver():
    global last_saved_minute
    while True:
        now = datetime.now()
        if now.minute % 5 == 0 and now.minute != last_saved_minute:
            with data_lock:
                if full_data:
                    history = []
                    if os.path.exists(DAILY_HISTORY):
                        try:
                            with open(DAILY_HISTORY, 'r', encoding='utf-8') as f:
                                history = json.load(f)
                        except: pass
                
                    current_date_str = now.strftime('%d-%m-%Y')
                    history = [entry for entry in history if entry.get('time', '').startswith(current_date_str)]
                    cleaned = []
                    for key, val in full_data.items():
                        item = val.copy()
                        item.pop('time', None)
                        cleaned.append(item)

                    history.append({
                        "time": now.strftime('%d-%m-%Y %H:%M:%S'),
                        "data": cleaned
                    })

                    with open(DAILY_HISTORY, 'w', encoding='utf-8') as f:
                        json.dump(history, f, ensure_ascii=False, separators=(',', ':'))

                    last_saved_minute = now.minute
        time.sleep(15)

@socket.on('price_changed')
def on_price_changed(payload):
    try:
        raw_data = payload.get('data', {})
        changed = False
        for symbol, name in HAREM_SYMBOLS.items():
            if symbol in raw_data:
                item = raw_data[symbol]
                with data_lock:
                    full_data[symbol] = {
                        'name': name,
                        'alis': float(item.get('alis', 0)),
                        'satis': float(item.get('satis', 0)),
                        'time': item.get('tarih')
                    }
                changed = True
        if changed:
            write_live()
    except Exception as e:
        print(f"Hata: {e}")

@socket.event
def connect():
    print("Harem Sunucusuna Bağlanıldı")
    if not any(t.name == "HistorySaverThread" for t in threading.enumerate()):
        threading.Thread(target=history_saver, name="HistorySaverThread", daemon=True).start()

def tv_gen():
    return "qs_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))

def tv_msg(func, args):
    s = json.dumps({"m": func, "p": args}, separators=(',', ':'))
    return f"~m~{len(s)}~m~{s}"

def tv_heartbeat(raw):
    for p in raw.split("~m~"):
        if p.startswith("~h~"):
            return f"~m~{len(p)}~m~{p}"
    return None

def tefas_fetcher():

    while True:
        try:
            today = datetime.now()
            start = (today - timedelta(days=5)).strftime("%Y.%m.%d")
            end   = today.strftime("%Y.%m.%d")
            s = requests.Session()

            for symbol, (name, fontip) in TEFAS_SYMBOLS.items():
                resp = s.post("https://www.tefas.gov.tr/api/DB/BindHistoryInfo", data={
                    "fontip": fontip, "sfonkod": symbol,
                    "bastarih": start, "bittarih": end, "fonturkod": ""
                }, timeout=15)
                rows = [r for r in resp.json().get("data", []) if r.get("FONKODU") == symbol]
                if rows:
                    latest = sorted(rows, key=lambda x: x["TARIH"], reverse=True)[0]
                    price = float(latest["FIYAT"])
                    with data_lock:
                        full_data[symbol] = {
                            'name':  name,
                            'alis':  price,
                            'satis': price,
                            'time':  datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                        }
                    write_live()
            time.sleep(3600)
        except Exception as e:
            print(f"TEFAS error: {e}")
            time.sleep(60)
        

async def tv_connect():
    while True:
        try:
            date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            uri  = f"wss://data.tradingview.com/socket.io/websocket?from=chart%2F&date={date}&type=chart&auth=sessionid"

            async with websockets.connect(uri, additional_headers={
                "Origin":        "https://tr.tradingview.com",
                "User-Agent":    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15",
                "Cache-Control": "no-cache",
                "Pragma":        "no-cache",
            }, ping_interval=None, ping_timeout=None) as ws:

                await ws.recv()
                qs   = tv_gen()
                syms = list(TV_SYMBOLS.keys())
                await ws.send(tv_msg("set_auth_token",       ["unauthorized_user_token"]))
                await ws.send(tv_msg("quote_create_session", [qs]))
                await ws.send(tv_msg("quote_add_symbols",    [qs] + syms))
                await ws.send(tv_msg("quote_fast_symbols",   [qs] + syms))

                async for raw in ws:
                    if "~h~" in raw:
                        hb = tv_heartbeat(raw)
                        if hb:
                            await ws.send(hb)
                        continue

                    for part in raw.split("~m~"):
                        try:
                            d = json.loads(part)
                            if d.get("m") != "qsd":
                                continue
                            sym = d["p"][1].get("n", "")
                            if sym not in TV_SYMBOLS:
                                continue
                            v   = d["p"][1].get("v", {})
                            bid = v.get("bid")
                            ask = v.get("ask")
                            lp  = v.get("lp")

                            price = None
                            if bid and ask:
                                price = round((float(bid) + float(ask)) / 2, 4)
                            elif lp:
                                price = float(lp)

                            if price:
                                with data_lock:
                                    full_data[sym] = {
                                        'name':  TV_SYMBOLS[sym],
                                        'alis':  price,
                                        'satis': price,
                                        'time':  datetime.now().strftime('%d-%m-%Y %H:%M:%S')
                                    }
                                write_live()
                        except:
                            pass

        except Exception as e:
            print(f"TV hata: {e} — 5sn sonra...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=tefas_fetcher,name="TEFASThread", daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(tv_connect()), name="TVThread", daemon=True).start()
    try:
        socket.connect(URL, headers={'Origin': ORIGIN}, transports=['websocket'])
        socket.wait()
    except Exception as e:
        print(f"Bağlantı Hatası: {e}")