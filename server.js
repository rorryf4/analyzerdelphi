// server.js — minimal + loud
const express = require("express");
const app = express();

app.use(express.json());

// log every request so we can see it in Render logs
app.use((req, _res, next) => {
  console.log(`[REQ] ${req.method} ${req.path}`);
  next();
});

// health
app.get("/healthz", (_req, res) => {
  res.json({ ok: true, service: "analyzer" });
});

// analyze echo
app.post("/analyze", (req, res) => {
  res.json({ ok: true, received: req.body ?? {} });
});

// root quick check
app.get("/", (_req, res) => res.type("text/plain").send("OK"));

// 404 fallback
app.all("*", (req, res) => res.status(404).json({ ok: false, path: req.path }));

const PORT = process.env.PORT || 4002; // Render injects PORT
app.listen(PORT, () => console.log(`analyzer listening on ${PORT}`));
