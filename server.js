const express = require("express");
const app = express();
app.use(express.json());

// log every request so you can see it in Render logs
app.use((req, _res, next) => {
  console.log(`[REQ] ${req.method} ${req.path}`);
  next();
});

// root quick check (use this for health check temporarily)
app.get("/", (_req, res) => res.type("text/plain").send("OK"));

// health
app.get("/healthz", (_req, res) => res.json({ ok: true, service: "analyzer" }));

// analyze echo
app.post("/analyze", (req, res) => res.json({ ok: true, received: req.body ?? {} }));

// last-resort 404 so you *see* what path was hit
app.all("*", (req, res) => res.status(404).json({ ok: false, path: req.path }));

const PORT = process.env.PORT || 4002;
app.listen(PORT, () => console.log(`analyzer listening on ${PORT}`));
