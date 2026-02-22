import socketio
import json
import threading
import time
import os
from datetime import datetime

socket = socketio.Client()

URL = 'https://socket.haremaltin.com'
ORIGIN = 'https://canlipiyasalar.haremaltin.com'
DAILY_HISTORY = 'data/daily_history.json'
LIVE_DATA = 'data/live_data.json'

SYMBOLS = {
    'KULCEALTIN': 'Gram Altın',
    'ONS': 'Altın Ons',
    'XAGUSD': 'Gümüş Ons',
}
last_saved_minute = -1
full_data = {}

def history_saver():
    global last_saved_minute
    while True:
        now = datetime.now()
        if now.minute % 5 == 0 and now.minute != last_saved_minute:
            if full_data:
                history = []
                if os.path.exists(DAILY_HISTORY):
                    try:
                        with open(DAILY_HISTORY, 'r', encoding='utf-8') as f:
                            history = json.load(f)
                    except: pass
                
                current_date_str = now.strftime('%d-%m-%Y')
                history = [entry for entry in history if entry.get('time', '').startswith(current_date_str)]
                
                cleaned_history_data = []
                for val in full_data.values():
                    item = val.copy()
                    if 'time' in item:
                        del item['time']
                    cleaned_history_data.append(item)
                
                history.append({
                    "time": now.strftime('%d-%m-%Y %H:%M:%S'), 
                    "data": cleaned_history_data
                })
                
                with open(DAILY_HISTORY, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, separators=(',', ':'))
                
                last_saved_minute = now.minute
        
        time.sleep(15)

@socket.on('price_changed')
def on_price_changed(payload):
    global full_data
    try:
        raw_data = payload.get('data', {})
        changed = False
        updated_symbols = []
        
        for symbol, name in SYMBOLS.items():
            if symbol in raw_data:
                item = raw_data[symbol]
                full_data[symbol] = {
                    'name': name,
                    'alis': float(item.get('alis', 0)),
                    'satis': float(item.get('satis', 0)),
                    'time': item.get('tarih')
                }
                updated_symbols.append(name)
                changed = True
        
        if changed:
            output = list(full_data.values())
            with open(LIVE_DATA, 'w', encoding='utf-8') as file:
                json.dump(output, file, ensure_ascii=False, separators=(',', ':'))
                
            last_market_time = item.get('tarih')
            print(f"Güncelleme: {updated_symbols} | {last_market_time}")
                
    except Exception as e:
        print(f"Hata: {e}")

@socket.event
def connect():
    print("Harem Sunucusuna Bağlanıldı")
    if not any(t.name == "HistorySaverThread" for t in threading.enumerate()):
        threading.Thread(target=history_saver, name="HistorySaverThread", daemon=True).start()

try:
    socket.connect(URL, headers={'Origin': ORIGIN}, transports=['websocket'])
    socket.wait()
except Exception as e:
    print(f"Bağlantı Hatası: {e}")