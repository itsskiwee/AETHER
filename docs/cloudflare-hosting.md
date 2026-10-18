# Cloudflare hosting

AETHER's console and read-only API use one origin. The deployment uses a Cloudflare
Worker as the public entry point and a Durable Object-managed Container for the
existing FastAPI application and React build. The Container builds from the repository
`Dockerfile`; it does not run the simulation or change saved replay artifacts.

The Worker accepts `GET` and `HEAD` requests and forwards them to the Container. The
Container becomes available after `/healthz` succeeds. The console is served at `/`,
the API at `/api`, and interactive API documentation at `/api/docs`.

## Data connections

AETHER has no runtime MCP client or MCP server requirement. Its current public context
already comes from the policy-checked CelesTrak GP and NASA CMR HTTP feeds in
`scripts/live_context.py`. The Cloudflare MCP connection is for managing Cloudflare
resources; its credentials are not passed to the deployed application. The Container
is configured to enable those existing public feed refreshes and needs outbound
internet access. Satellite positions remain SGP4/Skyfield estimates, NASA catalogue
entries remain historical metadata, and neither feed is telemetry or a methane
measurement. These feeds do not change the recorded scientific runs.

## Deploy with Workers Builds

Workers Builds can build and publish the Dockerfile image remotely. This is the
recommended route when the deployment machine has no local Docker daemon.
See Cloudflare's [Workers Builds configuration](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/)
and [Container deployment guide](https://developers.cloudflare.com/containers/guides/deploy/)
for current dashboard fields and rollout behavior.

1. Merge this delivery branch into the intended production branch, then connect the
   GitHub repository to a Cloudflare Worker using Workers Builds.
2. Set the repository root as the build root. Use `npm run cloudflare:typecheck` as
   the optional build command and `npm run deploy:cloudflare` as the deploy command.
   The root lockfile pins Wrangler; Wrangler builds the Container image from
   `Dockerfile` during deployment.
3. Before the first deploy, check that the account does not already contain a Worker
   named `aether-replay-hosted`. If it does, change the `name` in `wrangler.jsonc`
   so this deployment cannot replace that Worker.
4. Open the assigned `workers.dev` URL and confirm `/healthz` returns status `ok`.
   Then check `/`, `/api/runs` and `/api/live-context`.

Workers Builds needs the Cloudflare GitHub App connected to the repository and a
Cloudflare token that can deploy Workers and Containers. Keep tokens in the Cloudflare
dashboard or build settings; never commit them. A custom domain is not configured.

For a local deployment, install Node dependencies with `npm ci`, run
`npm run cloudflare:typecheck`, then `npm run deploy:cloudflare`. Local `wrangler deploy`
also needs Docker running. `wrangler dev` with this Container image has the same local
Docker requirement.

## Plan and usage

Cloudflare Containers require Workers Paid. Cloudflare currently lists a $5 USD monthly
minimum for that plan, with Container usage included up to monthly allowances and
metered beyond them. This setup uses the supported `standard-1` Container size, which
allocates 4 GiB of memory, and stops the Container after ten minutes without a request.
At that size, each active hour uses 4 GiB-hours of the included monthly memory
allowance; longer or frequent visits can create additional charges. Review the current
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/) and
[Container limits](https://developers.cloudflare.com/containers/platform/limits/)
before enabling a paid plan.

## Current deployment status

The deployment source and local type checks are prepared. No Cloudflare Worker or
Container has been created from this repository. The connected Cloudflare MCP can list
the account but account-scoped Workers requests currently return Cloudflare error
10000, so it cannot inspect or deploy resources. The account's existing plan status
also could not be read. Workers Builds or a Cloudflare connection with account-level
Workers and Containers deployment access is still required to publish the site.
