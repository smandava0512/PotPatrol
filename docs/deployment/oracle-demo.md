# Temporary PotPatrol Oracle demo

> **Retired:** The Oracle demo was removed. Do not follow the DNS or deployment
> steps below; the active isolated deployment is documented in
> [aws-demo.md](aws-demo.md).

This stack adds **only** `potpatrol-demo` containers and a new Traefik router for
`potpatrol.circlenineteen.me`. It uses a dedicated SQLite database and private media
volume; it does not use or migrate existing databases or change existing proxies.
It runs Developer 3's **synthetic two-event fixture**, not the real model. Never
present it as real pothole detection. `analysis_mode: "fixture"` is returned by the API.

## Prerequisites

- Create a DNS-only A record `potpatrol.circlenineteen.me` → `129.80.54.150`
  in the domain's DNS dashboard. Wait for resolution before expecting a trusted TLS
  certificate; Traefik uses its existing `letsencrypt` resolver.
- The isolated Oracle stack lives in `/home/ubuntu/potpatrol-demo` on
  `admin.circlenineteen.me` and joins the existing external `aio_network` solely
  so the existing Traefik can discover its *new* router. No host ports are published.
- Generate a unique `POTPATROL_DEVICE_TOKEN` in a local `.env` file on the
  server (mode `0600`); **never commit or send it in chat**. Share with Developer 1
  through a private secure channel. Only `/health` is unauthenticated.

## Run

From the isolated directory with the code on the server:

```sh
sudo docker compose -f compose.oracle-demo.yaml build
sudo docker compose -f compose.oracle-demo.yaml run --rm --no-deps api alembic upgrade head
sudo docker compose -f compose.oracle-demo.yaml up -d --no-build
sudo docker compose -f compose.oracle-demo.yaml ps
```

Verify `https://potpatrol.circlenineteen.me/health` returns `{"status":"ok"}`
with a valid TLS certificate before giving the URL to Developer 1. When DNS is
not yet live, test the router locally with a Host header, but do not call it a
public HTTPS test. For a fixture upload use the *same* private token on JSON,
MP4 PUT, and evidence reads; start the app and worker together. The report
adapter exposes nested `destination.status`; ownership is never inferred from GPS.

For real-model acceptance, rebuild with the full Developer 3 model dependencies
and evaluate **actual pothole and clean-road clips** on suitable hardware. This
ARM64 fixture-only image is not evidence that the real model works on this host.

## Move to DigitalOcean later

Keep the canonical API paths/JSON, swap this disposable demo deployment for an
API + worker deployment with durable private object storage, migrate the database
intentionally, then move DNS once HTTPS and the real-model flow both pass. Do not
copy a device token or locally stored evidence into a public repository.
