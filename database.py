"""
PaddyShield - Database Layer
Uses PostgreSQL on Render cloud, falls back to JSON file locally.
"""
import os, json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── POSTGRES (cloud) ──────────────────────────────
def get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS farmers (
                    id            BIGINT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    phone         TEXT NOT NULL,
                    village       TEXT NOT NULL,
                    mandal        TEXT NOT NULL,
                    stage         TEXT NOT NULL,
                    acres         TEXT,
                    soil_type     TEXT DEFAULT 'clay',
                    paddy_variety TEXT DEFAULT 'sona_masuri',
                    water_level   REAL DEFAULT 5,
                    days_since_irrigation INTEGER DEFAULT 3,
                    fertilizer_type TEXT DEFAULT 'none',
                    fertilizer_days_ago INTEGER DEFAULT 30,
                    disease_history INTEGER DEFAULT 0,
                    telegram_chat_id TEXT,
                    registered    TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telegram_links (
                    phone    TEXT PRIMARY KEY,
                    chat_id  TEXT NOT NULL
                );
            """)
        conn.commit()

def db_get_farmers():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM farmers ORDER BY id DESC")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def db_add_farmer(f):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO farmers
                (id,name,phone,village,mandal,stage,acres,
                 soil_type,paddy_variety,water_level,days_since_irrigation,
                 fertilizer_type,fertilizer_days_ago,disease_history,registered)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                f["id"], f["name"], f["phone"], f["village"], f["mandal"],
                f["stage"], f["acres"], f.get("soil_type","clay"),
                f.get("paddy_variety","sona_masuri"), f.get("water_level",5),
                f.get("days_since_irrigation",3), f.get("fertilizer_type","none"),
                f.get("fertilizer_days_ago",30), f.get("disease_history",0),
                f["registered"]
            ))
        conn.commit()

def db_delete_farmer(fid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM farmers WHERE id=%s", (fid,))
        conn.commit()

def db_get_link(phone):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM telegram_links WHERE phone=%s", (phone,))
            row = cur.fetchone()
            return row[0] if row else None

def db_set_link(phone, chat_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO telegram_links (phone, chat_id)
                VALUES (%s,%s)
                ON CONFLICT (phone) DO UPDATE SET chat_id=EXCLUDED.chat_id
            """, (phone, str(chat_id)))
        conn.commit()

# ── JSON FALLBACK (local dev) ─────────────────────
DATA_FILE  = "farmers.json"
LINKS_FILE = "telegram_links.json"

def _load(path, default):
    if not os.path.exists(path): return default
    with open(path) as f: return json.load(f)

def _save(path, data):
    with open(path,"w") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def json_get_farmers():       return _load(DATA_FILE, [])
def json_add_farmer(f):
    farmers = json_get_farmers(); farmers.append(f); _save(DATA_FILE, farmers)
def json_delete_farmer(fid):
    _save(DATA_FILE, [f for f in json_get_farmers() if f["id"] != fid])
def json_get_link(phone):
    return _load(LINKS_FILE, {}).get(phone)
def json_set_link(phone, chat_id):
    links = _load(LINKS_FILE, {}); links[phone] = str(chat_id); _save(LINKS_FILE, links)

# ── UNIFIED API ───────────────────────────────────
USE_DB = bool(DATABASE_URL)

def setup():
    if USE_DB:
        try: init_db(); print("✅ PostgreSQL connected")
        except Exception as e: print(f"⚠️ DB init failed: {e}")
    else:
        print("📁 Using local JSON storage")

def get_farmers():
    return db_get_farmers()    if USE_DB else json_get_farmers()

def add_farmer(f):
    db_add_farmer(f)           if USE_DB else json_add_farmer(f)

def delete_farmer(fid):
    db_delete_farmer(fid)      if USE_DB else json_delete_farmer(fid)

def get_link(phone):
    return db_get_link(phone)  if USE_DB else json_get_link(phone)

def set_link(phone, chat_id):
    db_set_link(phone,chat_id) if USE_DB else json_set_link(phone, chat_id)
