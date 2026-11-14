// keepalive.js – ping Render health endpoint every 10 minutes
// Works with Node >= 18 (built‑in fetch). If using older Node, install node‑fetch.

const url = "https://gen-ai-proj-262c.onrender.com/api/health";

async function ping() {
  try {
    const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
    const now = new Date().toISOString();
    console.log(`[${now}] ✅ ${res.status}`);
  } catch (e) {
    const now = new Date().toISOString();
    console.error(`[${now}] ❌ ${e.message}`);
  }
}

// Run immediately, then every 10 minutes (600,000 ms)
ping();
setInterval(ping, 10 * 60 * 1000);
