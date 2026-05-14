#!/usr/bin/env node
/** Copy cytoscape / mermaid / cytoscape-dagre builds and bundle dagre for browser globals.
 *  Served from /vendor/* alongside static files so Edge Tracking Prevention won't block CDN storage.
 */
const fs = require("fs");
const path = require("path");
const esbuild = require("esbuild");

const root = path.join(__dirname, "..");
const vendorDir = path.join(root, "public", "vendor");
const nm = path.join(root, "node_modules");

async function main() {
  fs.mkdirSync(vendorDir, { recursive: true });

  const copies = [
    { from: ["cytoscape", "dist", "cytoscape.min.js"], to: "cytoscape.min.js" },
    { from: ["mermaid", "dist", "mermaid.min.js"], to: "mermaid.min.js" },
    { from: ["cytoscape-dagre", "cytoscape-dagre.js"], to: "cytoscape-dagre.js" },
  ];

  let ok = true;
  for (const { from: fromParts, to: destName } of copies) {
    const from = path.join(nm, ...fromParts);
    const to = path.join(vendorDir, destName);
    if (!fs.existsSync(from)) {
      console.error("Missing:", from);
      ok = false;
      continue;
    }
    fs.copyFileSync(from, to);
    console.log("Copied", destName);
  }

  await esbuild.build({
    entryPoints: [path.join(nm, "dagre", "index.js")],
    bundle: true,
    format: "iife",
    globalName: "dagre",
    outfile: path.join(vendorDir, "dagre.min.js"),
    logLevel: "info",
    platform: "browser",
  });
  console.log("Bundled dagre.min.js");

  if (!ok) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
