const express = require("express");
const http = require("http");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const chokidar = require("chokidar");

const ROOT = path.resolve(__dirname, "..");
const PARSER_SCRIPT = path.join(__dirname, "parser", "extract.py");
const PUBLIC_DIR = path.join(__dirname, "public");
const METADATA_FILE = path.join(PUBLIC_DIR, "metadata.json");
const BASE_PORT = Number.parseInt(process.env.PORT || "3456", 10) || 3456;

const app = express();
app.use(express.static(PUBLIC_DIR));

// SSE clients for live reload
const clients = new Set();

app.get("/api/events", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });
  clients.add(res);
  req.on("close", () => clients.delete(res));
});

function notifyClients(data) {
  const msg = `data: ${JSON.stringify(data)}\n\n`;
  clients.forEach(c => c.write(msg));
}

// Run Python parser and return parsed JSON
function runParser() {
  return new Promise((resolve, reject) => {
    const proc = spawn("python", [PARSER_SCRIPT], {
      cwd: ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", d => (stdout += d.toString()));
    proc.stderr.on("data", d => (stderr += d.toString()));
    proc.on("close", code => {
      if (code !== 0) {
        reject(new Error(stderr || `Parser exited with code ${code}`));
        return;
      }
      console.log(stdout.trim());
      try {
        const raw = fs.readFileSync(METADATA_FILE, "utf-8");
        resolve(JSON.parse(raw));
      } catch (e) {
        reject(e);
      }
    });
    proc.on("error", reject);
  });
}

// API: get metadata
app.get("/api/metadata", async (req, res) => {
  try {
    const data = await runParser();
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Start server
async function start() {
  // Initial parse
  console.log("Parsing source code...");
  try {
    await runParser();
    console.log("Initial parse complete.");
  } catch (e) {
    console.error("Initial parse failed:", e.message);
  }

  // Watch src/ for changes, re-parse
  const watcher = chokidar.watch(path.join(ROOT, "src", "**", "*.py"), {
    ignoreInitial: true,
    awaitWriteFinish: { stabilityThreshold: 300, pollInterval: 100 },
  });

  let debounceTimer = null;
  watcher.on("all", (event, filepath) => {
    console.log(`[${event}] ${path.relative(ROOT, filepath)}`);
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      console.log("Re-parsing...");
      try {
        await runParser();
        notifyClients({ type: "reload", time: Date.now() });
      } catch (e) {
        console.error("Re-parse failed:", e.message);
        notifyClients({ type: "error", message: e.message });
      }
    }, 500);
  });

  listenWithFallback(BASE_PORT);
}

/** Bind HTTP server; if port is taken (EADDRINUSE), try BASE_PORT+1 … up to maxAttempts. */
function listenWithFallback(port, maxAttempts = 24) {
  const server = http.createServer(app);

  server.once("error", err => {
    if (err.code === "EADDRINUSE" && maxAttempts > 0) {
      console.warn(`  Port ${port} is in use, trying ${port + 1}…`);
      listenWithFallback(port + 1, maxAttempts - 1);
      return;
    }
    console.error(err);
    process.exit(1);
  });

  server.listen(port, () => {
    const addr = server.address();
    const actual = typeof addr === "object" && addr ? addr.port : port;
    if (actual !== BASE_PORT) {
      console.warn(`  Note: started on ${actual} (preferred ${BASE_PORT} was busy). Set PORT=${actual} or free port ${BASE_PORT}.`);
    }
    console.log(`\n  Code Viz Server running at http://localhost:${actual}`);
    console.log(`  Watching: ${path.join(ROOT, "src")}`);
    console.log(`  Press Ctrl+C to stop.\n`);
  });
}

start().catch(console.error);
