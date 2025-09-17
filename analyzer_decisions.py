print(">>> analyzer_decisions.py starting...")

from pathlib import Path
from datetime import datetime, timedelta, timezone
import re, sqlite3, math, json
import pandas as pd
import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# point to your scraper DB
DB_PATH = Path(r"C:\Users\rorry\OneDrive\Desktop\delphi scraper\delphi-edge-scraper\data\delphi_edge.db")
OUT_DIR = Path("data/analytics")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEAM_MAP = {
    "Saints": ["Saints","New Orleans Saints","New Orleans"],
    "Falcons": ["Falcons","Atlanta Falcons","Atlanta"],
    "Buccaneers": ["Buccaneers","Bucs","Tampa Bay Buccaneers","Tampa Bay"],
    "Ravens": ["Ravens","Baltimore Ravens","Baltimore"],
    "Patriots": ["Patriots","New England Patriots","New England"],
    "Bills": ["Bills","Buffalo Bills","Buffalo"],
    "Alabama": ["Alabama","Crimson Tide","Bama"],
    "LSU": ["LSU","Tigers"],
    "Georgia": ["Georgia","Bulldogs","UGA"],
    "Florida": ["Florida Gators","Gators","Florida"],
    "Arkansas": ["Arkansas","Razorbacks"],
    "South Carolina": ["South Carolina","Gamecocks"],
    "Michigan": ["Michigan","Wolverines"],
    "Ohio State": ["Ohio State","Buckeyes"],
    "Penn State": ["Penn State","Nittany Lions"],
    "Wisconsin": ["Wisconsin","Badgers"],
}

TOPIC_PATTERNS = {
    "Injury": {
        "weight": 4.0,
        "patterns": [
            r"\bACL\b", r"\bIR\b", r"\bMCL\b", r"\bAchilles\b",
            r"\bhamstring\b", r"\bgroin\b", r"\bhigh[- ]ankle\b",
            r"\bconcussion\b", r"\bprotocol\b",
            r"\bout\b(?!\s*of\b)", r"\bquestionable\b", r"\bdoubtful\b", r"\bgame[- ]time decision\b",
            r"\blimited participant\b", r"\bDNP\b",
        ],
    },
    "Transaction": {
        "weight": 2.5,
        "patterns": [
            r"\bsign(?:s|ed|ing)?\b", r"\bre[- ]sign(?:s|ed|ing)?\b", r"\bextension\b",
            r"\btrade(?:d| talks)?\b", r"\bwaiv(?:e|ed)\b", r"\breleas(?:e|ed)\b",
            r"\bpractice squad\b", r"\bactivate(?:d)?\b", r"\belevate(?:d)?\b",
        ],
    },
    "DepthChart": {
        "weight": 1.5,
        "patterns": [
            r"\bstarter\b", r"\bbackup\b", r"\bdepth chart\b",
            r"\bfirst[- ]team\b", r"\bsecond[- ]team\b",
            r"\bRB\d\b|\bWR\d\b|\bCB\d\b|\bLB\d\b|\bTE\d\b|\bQB\d\b",
        ],
    },
    "Rumor": {
        "weight": 0.8,
        "patterns": [
            r"\brumor(s)?\b", r"\breport(s)? say\b", r"\bsources\b", r"\blinked to\b"
        ],
    },
}

def source_weight(source: str, tags: str) -> float:
    s = (source or "").lower()
    t = (tags or "").lower()
    w = 1.0
    if "local" in t or "team" in t:
        w = 1.4
    if "fantasy" in t or "betting" in t:
        w = max(w, 1.3)
    if "reddit" in t:
        w = min(w, 0.7)
    if "espn.com" in s or "sports.yahoo.com" in s or "cbssports.com" in s:
        w = max(w, 1.15)
    return w

def recency_decay(published_at, fetched_at, half_life_hours=36) -> float:
    ts = published_at if pd.notna(published_at) else fetched_at
    if pd.isna(ts):
        return 0.8
    hrs = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return max(0.3, math.exp(-math.log(2) * (hrs / half_life_hours)))

def load_articles():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT id,title,url,published_at,author,summary,tags,fetched_at,source FROM articles ORDER BY id DESC",
            conn
        )
    for c in ("published_at","fetched_at"):
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df

def tag_team(title: str) -> str | None:
    t = title or ""
    for team, aliases in TEAM_MAP.items():
        for a in aliases:
            if re.search(rf"\b{re.escape(a)}\b", t, re.I):
                return team
    return None

def match_topics(title: str, summary: str) -> list[str]:
    text = f"{title or ''} {summary or ''}"
    hits = []
    for topic, cfg in TOPIC_PATTERNS.items():
        if any(re.search(p, text, re.I) for p in cfg["patterns"]):
            hits.append(topic)
    return hits

SENTI = SentimentIntensityAnalyzer()

def article_score(row) -> tuple[float, dict]:
    title, summary = row["title"] or "", row["summary"] or ""
    topics = match_topics(title, summary)
    if not topics:
        return 0.0, {"topics": [], "base": 0.0, "src_w": 1.0, "decay": 1.0, "sent": 0.0}
    base = sum(TOPIC_PATTERNS[t]["weight"] for t in topics)
    sw = source_weight(row["source"], row["tags"] or "")
    dec = recency_decay(row["published_at"], row["fetched_at"])
    sent = 0.0
    if any(t in ("Injury","Transaction") for t in topics):
        comp = SENTI.polarity_scores(f"{title} {summary}")["compound"]
        sent = max(0.0, -comp) * 1.2
    score = (base * sw * dec) + sent
    return score, {"topics": topics, "base": base, "src_w": sw, "decay": dec, "sent": sent}

def build_scored_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["team"] = df["title"].apply(tag_team)
    df = df[df["team"].notna()].reset_index(drop=True)
    details, scores = [], []
    for _, r in df.iterrows():
        sc, meta = article_score(r)
        scores.append(sc); details.append(meta)
    df["score"] = scores
    df["topics"] = [d["topics"] for d in details]
    df["score_base"] = [d["base"] for d in details]
    df["score_source_w"] = [d["src_w"] for d in details]
    df["score_decay"] = [d["decay"] for d in details]
    df["score_sentiment_kicker"] = [d["sent"] for d in details]
    return df

def aggregate_edges(scored: pd.DataFrame, hours_recent=48, days_baseline=7):
    now = datetime.now(timezone.utc)
    recent_cut = now - timedelta(hours=hours_recent)
    base_cut = now - timedelta(days=days_baseline)
    scored["ts"] = scored["published_at"].fillna(scored["fetched_at"])
    recent = scored[scored["ts"] >= recent_cut]
    baseline = scored[(scored["ts"] >= base_cut) & (scored["ts"] < recent_cut)]
    agg_recent = (recent.groupby("team")["score"].sum().rename("score_recent").reset_index())
    agg_base = (baseline.groupby("team")["score"].mean().rename("score_baseline_mean").reset_index())
    edges = pd.merge(agg_recent, agg_base, on="team", how="left").fillna({"score_baseline_mean": 0.0})
    edges["edge_signal"] = edges["score_recent"] - 1.0 * edges["score_baseline_mean"]
    return edges.sort_values("edge_signal", ascending=False).reset_index(drop=True), recent

def save_csv(df: pd.DataFrame, name: str):
    p = OUT_DIR / f"{name}.csv"; df.to_csv(p, index=False); print(f">>> saved {p}")

def save_json(df: pd.DataFrame, name: str, orient="records"):
    p = OUT_DIR / f"{name}.json"; df.to_json(p, orient=orient, force_ascii=False); print(f">>> saved {p}")

def save_top_articles(recent_scored: pd.DataFrame, team: str, n=15):
    sub = recent_scored[recent_scored["team"] == team].sort_values("score", ascending=False).head(n)
    keep = ["title","url","team","topics","score","source","tags","published_at","fetched_at",
            "score_source_w","score_decay","score_sentiment_kicker"]
    save_csv(sub[keep], f"top_articles_{team.replace(' ','_')}")

def main():
    df = load_articles()
    print(f">>> loaded {len(df):,} rows")
    scored = build_scored_frame(df)
    print(f">>> team-mapped rows: {len(scored):,}")
    edges, recent = aggregate_edges(scored, hours_recent=48, days_baseline=7)
    print(f">>> recent window teams: {len(edges):,}")
    save_csv(edges, "edges_teams_48h_vs_7d")
    save_json(edges, "edges_teams_48h_vs_7d")
    cols = ["title","url","team","topics","score","source","tags","published_at","fetched_at",
            "score_base","score_source_w","score_decay","score_sentiment_kicker"]
    save_csv(recent[cols].sort_values("score", ascending=False), "recent_scored_articles")
    for t in edges.head(5)["team"].tolist():
        save_top_articles(recent, t, n=20)
    print(">>> analyzer_decisions.py done.")

if __name__ == "__main__":
    main()
