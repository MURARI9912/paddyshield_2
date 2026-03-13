"""
PaddyShield - AI Disease Prediction Model
Uses Random Forest trained on Telangana-specific paddy disease data.

Features:
  Weather  : humidity, rainfall, temp_max, temp_min
  Farmer   : soil_type, paddy_variety, water_level,
             days_since_irrigation, fertilizer_type,
             fertilizer_days_ago, disease_history, crop_stage

Train:    python ai_model.py train
Predict:  imported by app.py automatically
"""

import json, os, pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from paddyshield import ADVICE

MODEL_FILE    = "paddyshield_model.pkl"
ENCODERS_FILE = "paddyshield_encoders.pkl"

SOIL_TYPES  = ["clay","black_cotton","red","sandy","loamy"]
VARIETIES   = ["sona_masuri","bpt","rnr_15048","telangana_sona","hmt_ir64"]
STAGES      = ["seedling","tillering","flowering","grain_filling"]
FERTILIZERS = ["none","urea","dap","potash","mixed"]
DISEASES    = ["Blast Disease","Brown Spot","Sheath Blight"]

# ── DOMAIN KNOWLEDGE WEIGHTS ──────────────────────
RULES = {
    "Blast Disease": {
        "soil":    {"clay":0.7,"black_cotton":0.6,"red":0.5,"sandy":0.3,"loamy":0.4},
        "variety": {"sona_masuri":0.8,"bpt":0.6,"rnr_15048":0.3,"telangana_sona":0.4,"hmt_ir64":0.5},
        "stage":   {"seedling":0.4,"tillering":0.7,"flowering":1.0,"grain_filling":0.5},
        "wx": lambda h,r,tx,tn: min(1.,h/95)*.4+(1. if 20<=tn<=28 else .3)*.3+(1. if 20<=r<=80 else .4)*.3,
        "wt": lambda wl,di: min(1.,wl/10)*.3+(0.7 if di>5 else .3)*.7,
        "ft": lambda fa,ft: (0.9 if ft=="urea" and fa<14 else .4),
    },
    "Brown Spot": {
        "soil":    {"clay":0.5,"black_cotton":0.4,"red":0.8,"sandy":0.9,"loamy":0.5},
        "variety": {"sona_masuri":0.6,"bpt":0.7,"rnr_15048":0.4,"telangana_sona":0.5,"hmt_ir64":0.6},
        "stage":   {"seedling":0.5,"tillering":0.6,"flowering":0.7,"grain_filling":0.9},
        "wx": lambda h,r,tx,tn: min(1.,h/90)*.35+(1. if 28<=tx<=35 else .3)*.35+(1. if r>50 else .3)*.30,
        "wt": lambda wl,di: (0.8 if wl<3 else .3)*.5+(0.7 if di>7 else .3)*.5,
        "ft": lambda fa,ft: (0.9 if ft in ("none","potash") else .4),
    },
    "Sheath Blight": {
        "soil":    {"clay":0.9,"black_cotton":0.8,"red":0.4,"sandy":0.3,"loamy":0.6},
        "variety": {"sona_masuri":0.7,"bpt":0.8,"rnr_15048":0.5,"telangana_sona":0.6,"hmt_ir64":0.7},
        "stage":   {"seedling":0.2,"tillering":0.8,"flowering":0.9,"grain_filling":0.6},
        "wx": lambda h,r,tx,tn: min(1.,h/98)*.40+(1. if tx>=30 else .3)*.35+(1. if r>60 else .3)*.25,
        "wt": lambda wl,di: min(1.,wl/8)*.6+(0.8 if di<3 else .3)*.4,
        "ft": lambda fa,ft: (0.9 if ft in ("urea","mixed") and fa<10 else .4),
    },
}

def _score(disease, soil, variety, stage, fert_type, fert_days,
           water_lvl, days_irr, dis_hist, humidity, rainfall, temp_max, temp_min):
    r = RULES[disease]
    s = (r["soil"][soil]*.15 + r["variety"][variety]*.15 + r["stage"][stage]*.20 +
         r["wx"](humidity,rainfall,temp_max,temp_min)*.25 +
         r["wt"](water_lvl,days_irr)*.15 + r["ft"](fert_days,fert_type)*.10)
    if dis_hist: s = min(1., s*1.25)
    return s

def generate_training_data(n=6000, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        soil      = rng.choice(SOIL_TYPES)
        variety   = rng.choice(VARIETIES)
        stage     = rng.choice(STAGES)
        fert_type = rng.choice(FERTILIZERS)
        fert_days = int(rng.integers(1,60))
        water_lvl = float(rng.uniform(0,15))
        days_irr  = int(rng.integers(0,14))
        dis_hist  = int(rng.integers(0,2))
        humidity  = float(rng.uniform(55,100))
        rainfall  = float(rng.uniform(0,150))
        temp_max  = float(rng.uniform(25,40))
        temp_min  = float(rng.uniform(18,30))
        row = dict(humidity=humidity,rainfall=rainfall,temp_max=temp_max,temp_min=temp_min,
                   soil=soil,variety=variety,stage=stage,water_level=water_lvl,
                   days_since_irrigation=days_irr,fertilizer_type=fert_type,
                   fertilizer_days_ago=fert_days,disease_history=dis_hist)
        for d in DISEASES:
            sc = float(np.clip(_score(d,soil,variety,stage,fert_type,fert_days,
                       water_lvl,days_irr,dis_hist,humidity,rainfall,temp_max,temp_min)
                       + rng.normal(0,.05), 0, 1))
            row[d+"_risk"]  = "HIGH" if sc>=0.65 else "MEDIUM" if sc>=0.40 else "LOW"
            row[d+"_score"] = round(sc,3)
        rows.append(row)
    return pd.DataFrame(rows)

FEAT_COLS = ["humidity","rainfall","temp_max","temp_min","soil_enc","variety_enc",
             "stage_enc","water_level","days_since_irrigation","fertilizer_type_enc",
             "fertilizer_days_ago","disease_history"]

def train():
    print("🌾 PaddyShield AI — Training Disease Prediction Models")
    print("="*55)
    df = generate_training_data()
    print(f"✅ Generated {len(df)} training samples\n")
    cat_cols = ["soil","variety","stage","fertilizer_type"]
    encoders = {}
    for col in cat_cols:
        le = LabelEncoder()
        df[col+"_enc"] = le.fit_transform(df[col])
        encoders[col] = le
    models = {}
    for d in DISEASES:
        X = df[FEAT_COLS]
        y = df[d+"_risk"]
        Xtr,Xte,ytr,yte = train_test_split(X,y,test_size=.2,random_state=42,stratify=y)
        clf = RandomForestClassifier(n_estimators=150,max_depth=12,
              min_samples_leaf=5,class_weight="balanced",random_state=42,n_jobs=-1)
        clf.fit(Xtr,ytr)
        print(f"📊 {d}")
        print(classification_report(yte,clf.predict(Xte)))
        models[d] = clf
    with open(MODEL_FILE,"wb") as f: pickle.dump({"models":models,"features":FEAT_COLS},f)
    with open(ENCODERS_FILE,"wb") as f: pickle.dump(encoders,f)
    print(f"\n✅ Saved → {MODEL_FILE}  &  {ENCODERS_FILE}")
    print("🚀 AI model ready!")

def predict(farmer, weather):
    if not os.path.exists(MODEL_FILE):
        # fallback rule-based
        from paddyshield import assess_risks
        risks = assess_risks(weather)
        out = []
        for disease,(score,lvl) in risks.items():
            level = lvl.split()[-1]
            out.append({"disease":disease,"level":level,
                        "probability":round(score/8*100,1),"score":score,
                        "proba_breakdown":{"HIGH":0,"MEDIUM":0,"LOW":0},
                        "emoji":"🔴" if level=="HIGH" else "🟡" if level=="MEDIUM" else "🟢",
                        "advice":ADVICE[disease][level],"method":"rule-based"})
        return out

    with open(MODEL_FILE,"rb") as f:  saved    = pickle.load(f)
    with open(ENCODERS_FILE,"rb") as f: encoders = pickle.load(f)
    models = saved["models"]

    def enc(col, val, default):
        try: return encoders[col].transform([val])[0]
        except: return encoders[col].transform([default])[0]

    X = pd.DataFrame([{
        "humidity":              weather["humidity"],
        "rainfall":              weather["rainfall"],
        "temp_max":              weather["temp_max"],
        "temp_min":              weather["temp_min"],
        "soil_enc":              enc("soil",    farmer.get("soil_type","clay"),         "clay"),
        "variety_enc":           enc("variety", farmer.get("paddy_variety","sona_masuri"),"sona_masuri"),
        "stage_enc":             enc("stage",   farmer.get("stage","tillering"),         "tillering"),
        "water_level":           float(farmer.get("water_level", 5)),
        "days_since_irrigation": int(farmer.get("days_since_irrigation", 3)),
        "fertilizer_type_enc":   enc("fertilizer_type", farmer.get("fertilizer_type","none"),"none"),
        "fertilizer_days_ago":   int(farmer.get("fertilizer_days_ago", 30)),
        "disease_history":       int(farmer.get("disease_history", 0)),
    }])

    out = []
    for disease, clf in models.items():
        proba   = clf.predict_proba(X)[0]
        classes = list(clf.classes_)
        pd_     = dict(zip(classes, proba))
        level   = clf.predict(X)[0]
        out.append({
            "disease":  disease,
            "level":    level,
            "probability": round(max(proba)*100,1),
            "proba_breakdown": {
                "HIGH":   round(pd_.get("HIGH",  0)*100,1),
                "MEDIUM": round(pd_.get("MEDIUM",0)*100,1),
                "LOW":    round(pd_.get("LOW",   0)*100,1),
            },
            "emoji":  "🔴" if level=="HIGH" else "🟡" if level=="MEDIUM" else "🟢",
            "advice": ADVICE[disease][level],
            "method": "ai",
        })
    return out

if __name__ == "__main__":
    import sys
    if len(sys.argv)>1 and sys.argv[1]=="train":
        train()
    else:
        print("Usage: python ai_model.py train")
