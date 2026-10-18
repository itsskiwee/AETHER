import { DurableObject } from "cloudflare:workers";

const CONTAINER_PORT = 8080;
const CONTAINER_IDLE_TIMEOUT_MS = 10 * 60 * 1000;
const HEALTH_CHECK_ATTEMPTS = 100;
const HEALTH_CHECK_INTERVAL_MS = 200;
const HEALTH_CHECK_TIMEOUT_MS = 1000;

export class AetherReplayContainer extends DurableObject<Env> {
  private starting: Promise<void> | undefined;

  async fetch(request: Request): Promise<Response> {
    this.starting ??= this.startAndWaitForHealth().finally(() => {
      this.starting = undefined;
    });

    try {
      await this.starting;
      const url = new URL(request.url);
      url.protocol = "http:";
      url.host = "container";
      const forwarded = new Request(url, request);
      forwarded.headers.delete("host");
      return await this.ctx.container!.getTcpPort(CONTAINER_PORT).fetch(forwarded);
    } catch (error) {
      console.error("AETHER replay container is unavailable", error);
      return new Response("Replay service is temporarily unavailable.", {
        status: 503,
        headers: { "Retry-After": "5" },
      });
    }
  }

  private async startAndWaitForHealth(): Promise<void> {
    const container = this.ctx.container;
    if (!container) {
      throw new Error("Cloudflare did not bind the AETHER replay container");
    }

    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: "standard-1",
        enableInternet: true,
        env: {
          AETHER_ENABLE_LIVE: "1",
          AETHER_HTTP_HOST: "0.0.0.0",
          PORT: String(CONTAINER_PORT),
        },
      });
    }

    await container.setInactivityTimeout(CONTAINER_IDLE_TIMEOUT_MS);

    const port = container.getTcpPort(CONTAINER_PORT);
    let lastError: unknown;
    for (let attempt = 0; attempt < HEALTH_CHECK_ATTEMPTS; attempt += 1) {
      try {
        const response = await port.fetch("http://container/healthz", {
          signal: AbortSignal.timeout(HEALTH_CHECK_TIMEOUT_MS),
        });
        await response.body?.cancel();
        if (!response.ok) {
          throw new Error(`Health check returned ${response.status}`);
        }
        return;
      } catch (error) {
        lastError = error;
        await scheduler.wait(HEALTH_CHECK_INTERVAL_MS);
      }
    }

    throw new Error("AETHER replay container did not become healthy", {
      cause: lastError,
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed.", {
        status: 405,
        headers: { Allow: "GET, HEAD" },
      });
    }

    return await env.AETHER_REPLAY.getByName("public-replay").fetch(request);
  },
} satisfies ExportedHandler<Env>;
