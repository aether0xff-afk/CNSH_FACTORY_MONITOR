# Domain-free, persistent Cloudflare HTTPS for Factory Monitor

This is a separate **Cloudflare Worker** that proxies requests through a **Workers VPC Service** to the Fabric server's local Factory Monitor. Cloudflare issues a stable `*.workers.dev` URL; no custom domain or Quick Tunnel is required.

> **Status:** Setup template only. The Worker is not deployed by committing this folder. Workers VPC is beta. Do not publish the Worker until the FastAPI web password (`FM_PASSWORD`) has been configured securely.

## Requirements

- Cloudflare Workers account with Workers VPC access (beta).
- A healthy `cloudflared` tunnel **on the same Windows machine** as Factory Monitor.
- Factory Monitor responding at `http://127.0.0.1:8000`.
- Cloudflare Tunnel connecting over QUIC (UDP outbound port 7844).
- Node.js on the computer where you run Wrangler (not necessarily the game server).

## Step 1 — Create Workers VPC Service

In Cloudflare Dashboard go to **Workers VPC -> VPC Services -> Create**.

- Name: `factory-monitor-http`
- Tunnel: select your already-connected `cnsh-factory-monitor` if available in the list.
- Type: HTTP
- Host/IP: `127.0.0.1` (same machine as cloudflared)
- HTTP port: `8000`
- Do not configure public network access to RCON `25575`.

Record the **VPC Service ID**. If the Zero Trust tunnel does not appear in the Workers VPC picker, follow Cloudflare's Workers VPC tunnel setup guide for an additional Workers VPC-compatible tunnel; do not re-install a conflicting Windows service blindly.

## Step 2 — Deploy the Worker

Install Node.js on your admin computer if needed, open PowerShell:

```powershell
cd C:\CNSH_FACTORY_MONITOR\cloudflare-worker
notepad wrangler.jsonc
```

Replace `REPLACE_WITH_YOUR_VPC_SERVICE_ID` with the Service ID from step 1 (leave the binding name as `FACTORY_SERVICE`).

```powershell
npx wrangler login
npx wrangler deploy
```

Wrangler prints your persistent address (for example, `https://cnsh-factory-monitor.<your-workers-subdomain>.workers.dev`). **Never guess the account subdomain; copy the actual URL from Wrangler**.

Your browser will ask for Factory Monitor's original Basic Auth credentials. A successful deploy does not prove the VPC-to-origin connection; test the live URL on mobile data.

## Step 3 — Keep it on all the time

- Cloudflare Worker is deployed and hosted by Cloudflare and does **not** need a local console process.
- Keep `cloudflared` running as a **Windows service** on the server.
- Configure the Factory Monitor `start_server.cmd` with Windows Task Scheduler **At startup**, using the real path `C:\CNSH_FACTORY_MONITOR\start_server.cmd`.
- If the Windows server or Minecraft goes down, the URL stays the same but backend may become unavailable.

## Notes

- Do not share RCON passwords, `.env`, tunnel tokens, or SQLite DB.
- Public Worker URL is reachable by anyone, but Factory Monitor's **HTTP Basic Auth** must remain enabled with a strong password. Consider adding an additional Cloudflare Access layer later.
- Only the designated VPC Service at `127.0.0.1:8000` should be bound; don't expose the RCON endpoint.
- Docs: https://developers.cloudflare.com/workers-vpc/get-started/
- Docs: https://developers.cloudflare.com/workers-vpc/configuration/vpc-services/
