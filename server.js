import express from "express";

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true, service: "analyzer" }));

// POST /analyze expects the raw payload from /scrape
app.post("/analyze", (req, res) => {
  const raw = req.body || {};
  const { league = "ncaaf", week = 1 } = raw;

  const games = (raw.games || []).map(g => {
    // Toy "model": push spread 2.6 pts toward favorite if OL mismatch
    const olNote = (g.notes || []).join(" ").toLowerCase();
    const olMismatch = olNote.includes("ol") || (g.teamForm?.pennState?.olGrade === "B-"); // example
    const modelSpread = (g.market?.spread ?? 0) - (olMismatch ? 2.6 : 0);
    const value = Math.abs(modelSpread - (g.market?.spread ?? 0));
    const confidence = Math.min(0.9, 0.55 + (olMismatch ? 0.09 : 0));

    return {
      home: g.home,
      away: g.away,
      kickoff: g.kickoff,
      market: g.market,
      narratives: g.notes || [],
      edge: {
        modelSpread: Number(modelSpread.toFixed(1)),
        value: Number(value.toFixed(1)),
        confidence: Number(confidence.toFixed(2)),
        pick: modelSpread < (g.market?.spread ?? 0) ? `${g.home} ${g.market.spread}` : `${g.away} +${Math.abs(g.market.spread)}`
      }
    };
  });

  res.json({
    league,
    week,
    generatedAt: new Date().toISOString(),
    games
  });
});

const PORT = process.env.PORT || 4002;
app.listen(PORT, () => console.log(`analyzer listening on ${PORT}`));
