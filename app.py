"""
PaddyShield - Cloud App Server
Local : python app.py  →  http://localhost:5000
Cloud : gunicorn via Procfile
"""
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import json, os, urllib.request
from datetime import datetime
from paddyshield import fetch_weather, assess_risks, ADVICE
import database as db

load_dotenv()

app       = Flask(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_URL   = os.environ.get("APP_URL", "")   # e.g. https://paddyshield-2.onrender.com

VILLAGE_COORDS = {
    "quthbullapur":(17.55,78.42),  "medak":(17.975,78.263),
    "nalgonda":(17.057,79.267),    "hyderabad":(17.385,78.486),
    "warangal":(17.977,79.598),    "karimnagar":(18.438,79.128),
    "nizamabad":(18.672,78.094),   "khammam":(17.247,80.150),
    "sangareddy":(17.619,78.085),  "siddipet":(18.102,78.852),
    "suryapet":(17.139,79.623),    "mahabubnagar":(16.738,77.983),
    "adilabad":(19.664,78.532),    "mancherial":(18.869,79.454),
    "jagtial":(18.795,78.914),     "peddapalli":(18.617,79.383),
    "nizamabad":(18.672,78.094),   "narayanpet":(16.745,77.497),
    "wanaparthy":(16.362,78.064),  "jogulamba":(16.396,77.822),
}

def get_coords(village):
    key = village.strip().lower()
    for k,v in VILLAGE_COORDS.items():
        if k in key or key in k: return v
    return (17.385,78.486)

# ── TELEGRAM HELPERS ─────────────────────────────
def tg(method, params):
    if not BOT_TOKEN: return {}
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params).encode()
    req  = urllib.request.Request(url, data=data,
           headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"Telegram error: {e}"); return {}

def send_msg(chat_id, text):
    return tg("sendMessage",{"chat_id":chat_id,"text":text,"parse_mode":"Markdown"})

def build_alert_text(farmer, weather, risks):
    stage = farmer.get("stage","").replace("_"," ").title()
    lines = [
        "🌾 *PaddyShield Weekly Alert*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 *{farmer['name']}*",
        f"📍 {farmer['village']}, {farmer['mandal']}",
        f"🌱 Stage: {stage}  |  📐 {farmer['acres']} acres",
        f"📅 {datetime.now().strftime('%d %b %Y')}","",
        "🌤 *Weather (7-day forecast)*",
        f"  💧 Humidity : {weather['humidity']}%",
        f"  🌧️ Rainfall  : {weather['rainfall']} mm",
        f"  🌡️ Temp      : {weather['temp_min']}°C – {weather['temp_max']}°C","",
        "⚠️ *Disease Risk Levels*",
    ]
    high = []
    for r in risks:
        lines.append(f"  {r['emoji']} *{r['disease']}* : {r['level']}")
        if r["level"] in ("HIGH","MEDIUM"): high.append(r)
    lines += ["","✅ *Recommended Actions*"]
    if high:
        for r in high:
            lines.append(f"\n▪️ *{r['disease']}*\n   → {r['advice']}")
    else:
        lines.append("  ✅ No urgent action needed. Keep monitoring.")
    lines += ["","━━━━━━━━━━━━━━━━━━━━",
              "📞 Follow govt pesticide dosage guidelines.",
              "🤝 _PaddyShield — Protecting Farmers, Proactively._"]
    return "\n".join(lines)

def register_webhook():
    if BOT_TOKEN and APP_URL:
        webhook_url = f"{APP_URL.rstrip('/')}/webhook/{BOT_TOKEN}"
        result = tg("setWebhook", {"url": webhook_url, "drop_pending_updates": True})
        print(f"Webhook set: {result.get('description','...')}")

# ── TELEGRAM WEBHOOK ─────────────────────────────
@app.route(f"/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != BOT_TOKEN:
        return "Unauthorized", 401

    update   = request.json or {}
    msg      = update.get("message", {})
    chat     = msg.get("chat", {})
    text     = msg.get("text","").strip()
    chat_id  = chat.get("id")
    fname    = chat.get("first_name","Farmer")

    if not text or not chat_id:
        return "ok"

    if text == "/start":
        send_msg(chat_id,
            f"🌾 *Welcome to PaddyShield, {fname}!*\n\n"
            "I send weekly paddy disease risk alerts based on your village weather.\n\n"
            "To link your account, send your *10-digit phone number* "
            "registered on PaddyShield.\n\n_Example: 9876543210_")

    elif text == "/help":
        send_msg(chat_id,
            "🌾 *PaddyShield Commands*\n\n"
            "/start — Welcome & linking info\n"
            "/alert — Get your risk alert now\n"
            "/help  — Show this message\n\n"
            "_Send your 10-digit phone number to link your account._")

    elif text == "/alert":
        phone = db.get_link_by_chat(chat_id) if hasattr(db,"get_link_by_chat") else None
        # find farmer by chat_id
        farmers = db.get_farmers()
        farmer  = None
        for f in farmers:
            p = f.get("phone","").replace("+91","").replace(" ","").strip()
            if db.get_link(p) == str(chat_id):
                farmer = f; break
        if farmer:
            send_msg(chat_id,"⏳ Fetching your risk alert now...")
            lat,lon  = get_coords(farmer["village"])
            weather  = fetch_weather(lat,lon)
            risks    = assess_risks(weather)
            risk_list = [{"disease":d,"level":l.split()[-1],
                          "emoji":"🔴" if l.split()[-1]=="HIGH" else "🟡" if l.split()[-1]=="MEDIUM" else "🟢",
                          "advice":ADVICE[d][l.split()[-1]]} for d,(s,l) in risks.items()]
            send_msg(chat_id, build_alert_text(farmer, weather, risk_list))
        else:
            send_msg(chat_id,"Please link your account first by sending your 10-digit phone number.")

    elif text.replace(" ","").isdigit() and len(text.replace(" ",""))==10:
        phone   = text.replace(" ","").strip()
        farmers = db.get_farmers()
        match   = next((f for f in farmers
                        if f.get("phone","").replace("+91","").replace(" ","")==phone), None)
        if match:
            db.set_link(phone, chat_id)
            send_msg(chat_id,
                f"✅ *Account linked successfully!*\n\n"
                f"👤 Name    : {match['name']}\n"
                f"📍 Village : {match['village']}, {match['mandal']}\n"
                f"🌱 Stage   : {match['stage'].replace('_',' ').title()}\n\n"
                "You'll now receive weekly disease alerts every Monday! 🌾\n"
                "Send /alert anytime to get an instant report.")
            print(f"🔗 Linked: {match['name']} ({phone}) → {chat_id}")
        else:
            send_msg(chat_id,
                "❌ Phone number not found.\n\n"
                "Please ask your coordinator to register you at the PaddyShield web app first.")
    else:
        send_msg(chat_id,
            "I didn't understand that. Try:\n"
            "/start — to get started\n"
            "/help — to see all commands\n"
            "_Or send your 10-digit phone number to link your account._")
    return "ok"

# ── API ROUTES ───────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status":"ok","db":bool(os.environ.get("DATABASE_URL")),
                    "bot":bool(BOT_TOKEN),"webhook":bool(APP_URL)})

@app.route("/api/farmers", methods=["GET"])
def get_farmers(): return jsonify(db.get_farmers())

@app.route("/api/farmers", methods=["POST"])
def add_farmer():
    data = request.json
    farmer = {
        "id":                    int(datetime.now().timestamp()*1000),
        "name":                  data["name"],
        "phone":                 data["phone"],
        "village":               data["village"],
        "mandal":                data["mandal"],
        "stage":                 data["stage"],
        "acres":                 data["acres"],
        "soil_type":             data.get("soil_type","clay"),
        "paddy_variety":         data.get("paddy_variety","sona_masuri"),
        "water_level":           data.get("water_level",5),
        "days_since_irrigation": data.get("days_since_irrigation",3),
        "fertilizer_type":       data.get("fertilizer_type","none"),
        "fertilizer_days_ago":   data.get("fertilizer_days_ago",30),
        "disease_history":       data.get("disease_history",0),
        "registered":            datetime.now().strftime("%d %b %Y"),
    }
    db.add_farmer(farmer)
    return jsonify({"ok":True,"farmer":farmer})

@app.route("/api/farmers/<int:fid>", methods=["DELETE"])
def delete_farmer(fid):
    db.delete_farmer(fid)
    return jsonify({"ok":True})

@app.route("/api/risk/<int:fid>")
def get_risk(fid):
    farmers = db.get_farmers()
    farmer  = next((f for f in farmers if f["id"]==fid), None)
    if not farmer: return jsonify({"error":"not found"}),404
    lat,lon  = get_coords(farmer["village"])
    weather  = fetch_weather(lat,lon)
    # try AI model first, fall back to rules
    try:
        from ai_model import predict as ai_predict
        risk_list = ai_predict(farmer, weather)
    except Exception:
        risks     = assess_risks(weather)
        risk_list = []
        for disease,(score,lvl) in risks.items():
            level = lvl.split()[-1]
            risk_list.append({"disease":disease,"level":level,"score":score,
                "emoji":"🔴" if level=="HIGH" else "🟡" if level=="MEDIUM" else "🟢",
                "advice":ADVICE[disease][level],"method":"rule-based"})
    result = {
        "farmer":farmer,"weather":weather,"risks":risk_list,
        "generated":datetime.now().strftime("%d %b %Y, %I:%M %p"),
    }
    # build whatsapp text
    lines = ["🌾 *PaddyShield Weekly Alert*",
             f"📍 {farmer['village']}, {farmer['mandal']}",
             f"👤 {farmer['name']}  |  🌱 {farmer['stage'].replace('_',' ').title()}",
             f"📅 {result['generated']}","",
             "📊 *Weather*",
             f"  💧 {weather['humidity']}% humidity  🌧️ {weather['rainfall']}mm  🌡️ {weather['temp_min']}–{weather['temp_max']}°C","",
             "⚠️ *Disease Risk*"]
    for r in risk_list:
        lines.append(f"  {r['emoji']} {r['disease']}: *{r['level']}*")
    lines += ["","✅ *Actions*"]
    for r in risk_list:
        if r["level"] in ("HIGH","MEDIUM"):
            lines.append(f"  [{r['disease']}] {r['advice']}")
    lines += ["","📞 Follow govt dosage guidelines.",
              "🤝 _PaddyShield — Protecting Farmers, Proactively._"]
    result["whatsapp_text"] = "\n".join(lines)
    return jsonify(result)

@app.route("/api/risk/all")
def get_all_risks():
    farmers = db.get_farmers()
    results = []
    for farmer in farmers:
        lat,lon = get_coords(farmer["village"])
        weather = fetch_weather(lat,lon)
        risks   = assess_risks(weather)
        summary = {"farmer":farmer,"weather":weather,"risks":[]}
        for disease,(score,lvl) in risks.items():
            label = lvl.split()[-1]
            summary["risks"].append({"disease":disease,"score":score,"level":label,
                "emoji":"🔴" if label=="HIGH" else "🟡" if label=="MEDIUM" else "🟢",
                "advice":ADVICE[disease][label]})
        results.append(summary)
    return jsonify(results)

@app.route("/api/send_alert/<int:fid>", methods=["POST"])
def send_telegram_alert(fid):
    farmers = db.get_farmers()
    farmer  = next((f for f in farmers if f["id"]==fid), None)
    if not farmer: return jsonify({"error":"farmer not found"}),404
    phone   = farmer.get("phone","").replace("+91","").replace(" ","").strip()
    chat_id = db.get_link(phone)
    if not chat_id:
        return jsonify({"ok":False,"error":"Farmer has not linked Telegram yet. Ask them to message the bot."})
    lat,lon  = get_coords(farmer["village"])
    weather  = fetch_weather(lat,lon)
    risks    = assess_risks(weather)
    risk_list= [{"disease":d,"level":l.split()[-1],
                 "emoji":"🔴" if l.split()[-1]=="HIGH" else "🟡" if l.split()[-1]=="MEDIUM" else "🟢",
                 "advice":ADVICE[d][l.split()[-1]]} for d,(s,l) in risks.items()]
    result = send_msg(chat_id, build_alert_text(farmer, weather, risk_list))
    return jsonify({"ok":result.get("ok",False)})

@app.route("/api/send_all", methods=["POST"])
def send_all():
    farmers = db.get_farmers()
    sent=0; skipped=0
    for farmer in farmers:
        phone   = farmer.get("phone","").replace("+91","").replace(" ","").strip()
        chat_id = db.get_link(phone)
        if not chat_id: skipped+=1; continue
        lat,lon  = get_coords(farmer["village"])
        weather  = fetch_weather(lat,lon)
        risks    = assess_risks(weather)
        risk_list= [{"disease":d,"level":l.split()[-1],
                     "emoji":"🔴" if l.split()[-1]=="HIGH" else "🟡" if l.split()[-1]=="MEDIUM" else "🟢",
                     "advice":ADVICE[d][l.split()[-1]]} for d,(s,l) in risks.items()]
        r = send_msg(chat_id, build_alert_text(farmer, weather, risk_list))
        if r.get("ok"): sent+=1
        else: skipped+=1
    return jsonify({"ok":True,"sent":sent,"skipped":skipped})

# ── STARTUP ──────────────────────────────────────
db.setup()
register_webhook()

if __name__ == "__main__":
    print("\n🌾 PaddyShield starting...")
    print("👉 http://localhost:5000\n")
    app.run(debug=True, port=5000)
