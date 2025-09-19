// server.js — Analyzer (Render)
const express = require("express");
const cors = require("cors");

// Node 18+ has global fetch; fall back to node-fetch if needed
const fetch =
  global.fetch || ((...a) => import("node-fetch").then(m => m.default(...a)));

// Load optional model pack. If missing, we fall back to a basic model.
let models = null;
try { models = require("./models"); } catch { /* optional */ }

const app = express();

/* ---------- middleware (order matters) ---------- */
app.use(cors({
  origin: [
    "http://localhost:3000",
    "https://webdelphi.vercel.app",
    /\.vercel\.app$/i,
    /\.onrender\.com$/i
  ],
  methods: ["GET","POST","OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true
}));
app.use(express.json());

// tiny request log
app.use((req, _res, next) => {
  console.log(`[REQ] ${req.method} ${req.path}${req.url.includes("?") ? "?" + req.url.split("?")[1] : ""}`);
  next();
});

/* ---------- health ---------- */
app.get("/", (_req, res) => res.type("text/plain").send("OK"));
app.get("/healthz", (_req, res) => res.json({ ok: true, service: "analyzer" }));

/* ---------- helpers ---------- */
const norm = (s) => String(s ?? "").trim().toUpperCase();

function parseUpstreamPayload(text) {
  try {
    const parsed = JSON.parse(text);
    const games = Array.isArray(parsed) ? parsed : (parsed?.games ?? []);
    return Array.isArray(games) ? games : [];
  } catch {
    return [];
  }
}

function filterByConference(games, conferencesCSV) {
  if (!conferencesCSV) return games;
  const allow = new Set(
    conferencesCSV.split(",").map(s => norm(s)).filter(Boolean)
  );
  if (allow.size === 0) return games;

  return games.filter((g) => {
    const fields = [
      g.home_conference, g.away_conference, g.conference, g.league,
      g.homeConference, g.awayConference, g.conferenceName
    ];
    return fields.some(v => allow.has(norm(v)));
  });
}

// Very simple baseline model (used if no external model provided)
function basicModel(games) {
  return games.map((g) => {
    const home = g.home_team ?? g.homeTeam ?? g.home ?? g.homeName ?? "Home";
    const away = g.away_team ?? g.awayTeam ?? g.away ?? g.awayName ?? "Away";
    const hp = g.home_points ?? g.homeScore ?? g.home_points_total ?? null;
    const ap = g.away_points ?? g.awayScore ?? g.away_points_total ?? null;
    const diff = (hp != null && ap != null) ? Math.abs(Number(hp) - Number(ap)) : null;
    const closeGame = diff != null ? diff <= 7 : null;

    return {
      id: g.id ?? g.game_id ?? `${away}@${home}`,
      matchup: `${away} @ ${home}`,
      kickoff: g.start_date ?? g.startTime ?? g.kickoff ?? null,
      status: g.status ?? (g.completed ? "Final" : g.in_progress ? "In-Progress" : "Scheduled"),
      score: (hp != null && ap != null) ? `${ap}-${hp}` : null,
      metrics: { scoreDiff: diff, closeGame },
      pick: closeGame === true ? "No Play (coin-flip)" : "Lean Favorite",
      confidence: closeGame === true ? 0.5 : 0.6
    };
  });
}

function pickModel(name) {
  const key = String(name ?? process.env.DEFAULT_MODEL ?? "basic").toLowerCase();
  if (models && typeof models[key] === "function") return { key, fn: models[key] };
  if (models && typeof models.basic === "function") return { key, fn: models.basic };
  return { key: "basic", fn: basicModel };
}

/* ---------- core: runAnalysis ---------- */
async function runAnalysis({ league = "ncaaf", week, conferencesCSV, model }) {
  if (!week) {
    return { status: 400, body: { ok: false, error: "missing_week" } };
  }

  const base = process.env.SCRAPER_URL;
  if (!base) {
    return { status: 500, body: { ok: false, error: "missing_config", detail: "SCRAPER_URL not set" } };
  }

  // Combine request CSV and server allow-list. We forward *and* enforce.
  const allowEnv = process.env.ALLOWED_CONFERENCES ?? "";
  const effectiveConfs = (conferencesCSV && String(conferencesCSV).trim()) || allowEnv;

  const url = new URL(`${base}/scrape`);
  url.searchParams.set("league", league);
  url.searchParams.set("week", String(week));
  if (effectiveConfs) url.searchParams.set("conferences", effectiveConfs);

  const upstream = await fetch(url.toString(), { cache: "no-store" });

  if (upstream.status === 204) {
    const chosen = pickModel(model);
    return { status: 200, body: { ok: true, league, week, model: chosen.key, count: 0, results: [] } };
  }

  const text = await upstream.text();
  if (!upstream.ok) {
    return {
      status: 502,
      body: { ok: false, error: "upstream", status: upstream.status, body: text.slice(0, 1000) }
    };
  }

  let games = parseUpstreamPayload(text);
  games = filterByConference(games, effectiveConfs);

  const { key, fn } = pickModel(model);
  const results = fn(games);

  return { status: 200, body: { ok: true, league, week, model: key, count: results.length, results } };
}

/* ---------- routes ---------- */
// GET /analyze?league=ncaaf&week=1&conferences=SEC,ACC&model=basic
app.get("/analyze", async (req, res) => {
  try {
    const { league = "ncaaf", week, conferences: conferencesCSV, model } = req.query;
    const { status, body } = await runAnalysis({ league, week, conferencesCSV, model });
    res.status(status).json(body);
  } catch (e) {
    console.error("GET /analyze error", e);
    res.status(500).json({ ok: false, error: "internal", message: e?.message ?? String(e) });
  }
});

// POST /analyze  { league, week, conferences?, model? }
app.post("/analyze", async (req, res) => {
  try {
    const { league = "ncaaf", week, conferences: conferencesCSV, model } = req.body ?? {};
    const { status, body } = await runAnalysis({ league, week, conferencesCSV, model });
    res.status(status).json(body);
  } catch (e) {
    console.error("POST /analyze error", e);
    res.status(500).json({ ok: false, error: "internal", message: e?.message ?? String(e) });
  }
});

/* ---------- start ---------- */
const PORT = process.env.PORT || 4002;
app.listen(PORT, () => console.log(`analyzer listening on ${PORT}`));
