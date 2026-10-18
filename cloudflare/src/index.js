const SNAPSHOT_PREFIX = "/_aether_snapshot__";

const exactPaths = {
  "/api/runs": "runs.json",
  "/api/project": "project.json",
  "/api/project/historical-context": "project-historical-context.json",
  "/api/live-context": "live-context.json",
  "/api/benchmark-results.csv": "benchmark-results.json",
  "/api/benchmark-confidence-intervals.json": "benchmark-confidence-intervals.json",
  "/api/benchmark-protocol": "benchmark-protocol.json",
  "/api/research-status": "research-status.json",
  "/api/development-timing.json": "development-timing.json",
  "/api/example": "example.json",
  "/openapi.json": "openapi.json",
  "/healthz": "healthz.json",
};

const API_DOCS_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AETHER read-only API</title>
    <style>
      body { max-width: 56rem; margin: 4rem auto; padding: 0 1.25rem; font: 16px/1.6 system-ui, sans-serif; color: #182c36; }
      h1 { font-size: 2rem; } code { background: #eef3ef; padding: .15rem .35rem; border-radius: .25rem; }
      li { margin: .45rem 0; } a { color: #145b4e; }
    </style>
  </head>
  <body>
    <p><a href="/">← AETHER replay console</a></p>
    <h1>Read-only replay API</h1>
    <p>This deployment serves timestamped snapshots of the checked-in replay archive. It does not run the simulator or planner.</p>
    <p><a href="/openapi.json">OpenAPI schema</a></p>
    <ul>
      <li><code>GET /api/runs</code> — saved replay index</li>
      <li><code>GET /api/runs/{run_id}</code> — saved run record</li>
      <li><code>GET /api/runs/{run_id}/export</code> — verified replay ZIP</li>
      <li><code>GET /api/project</code> — scenario and project summary</li>
      <li><code>GET /api/live-context</code> — timestamped public-provider snapshot</li>
    </ul>
  </body>
</html>`;

const runFiles = {
  "": "run.json",
  "/windows": "windows.json",
  "/plans": "plans.json",
  "/manifest.json": "manifest.json",
  "/historical-context": "historical-context.json",
  "/performance.json": "performance.json",
  "/export": "export.zip",
};

function assetPath(pathname) {
  const exactFile = exactPaths[pathname];
  if (exactFile) return `${SNAPSHOT_PREFIX}/${exactFile}`;

  const match = /^\/api\/runs\/([^/]+)(\/.*)?$/.exec(pathname);
  if (!match) return null;

  let runId;
  try {
    runId = decodeURIComponent(match[1]);
  } catch {
    return null;
  }
  if (!/^[A-Za-z0-9_-]+$/.test(runId)) return null;

  const file = runFiles[match[2] ?? ""];
  if (!file) return null;
  return `${SNAPSHOT_PREFIX}/runs/${encodeURIComponent(runId)}/${file}`;
}

function jsonNotFound() {
  return Response.json({ detail: "Not found" }, {
    status: 404,
    headers: { "Cache-Control": "no-store" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/") || url.pathname === "/openapi.json" || url.pathname === "/healthz") {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method not allowed.", {
          status: 405,
          headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" },
        });
      }

      if (url.pathname === "/api/docs" || url.pathname === "/api/docs/") {
        return new Response(request.method === "HEAD" ? null : API_DOCS_HTML, {
          headers: {
            "Cache-Control": "no-store",
            "Content-Type": "text/html; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
          },
        });
      }

      const path = assetPath(url.pathname);
      if (!path) return jsonNotFound();

      const snapshotUrl = new URL(path, url.origin);
      const asset = await env.ASSETS.fetch(new Request(snapshotUrl, request));
      if (!asset.ok) return jsonNotFound();

      const headers = new Headers(asset.headers);
      headers.set("Cache-Control", "no-store");
      headers.set("X-Content-Type-Options", "nosniff");
      if (url.pathname === "/api/benchmark-results.csv") {
        headers.set("Content-Type", "application/json; charset=utf-8");
      }
      if (/\/export$/.test(url.pathname)) {
        const runId = decodeURIComponent(url.pathname.split("/")[3]);
        headers.set("Content-Type", "application/zip");
        headers.set("Content-Disposition", `attachment; filename="${runId}.zip"`);
      }

      return new Response(request.method === "HEAD" ? null : asset.body, {
        status: asset.status,
        headers,
      });
    }

    return env.ASSETS.fetch(request);
  },
};
