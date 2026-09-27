# Isolated AWS demo (not production)

`api.potpatrol.miami` points to a dedicated Amazon Linux EC2 instance in `us-east-1`
(`i-08cecb8ac62f95379`, Elastic IP `52.2.5.209`). The `potpatrol-aws`
Compose project runs API, worker and Caddy; only Caddy publishes ports 80/443.
SSH on its dedicated security group is restricted to the operator's current IP.
The unrelated workshop CodeEditor instance and SageMaker bucket are not part of
this deployment.

The database is the **existing** PotPatrol Tiger Cloud PostgreSQL service. Alembic
revision `8d1f94a35d20` has been applied and its columns checked. Videos and
JPEG evidence use an authenticated API and a private Docker volume on the
instance's encrypted EC2 disk; there is **no S3 backup or multi-host durability**.
The EC2 instance, disk and public IPv4 address can incur charges while running.

## Configuration and runbook

- Clone `feat/developer-2-backend` into `/home/ec2-user/potpatrol-backend`.
- On that host, create `.env` (mode `0600`) with an **explicit**
  `POTPATROL_ANALYSIS_MODE=fixture` for the synthetic transport demo. Use
  `POTPATROL_DEVICE_TOKENS` with one distinct, random credential per participating
  device, delivered privately. The legacy `POTPATROL_DEVICE_TOKEN` may be used
  only for a genuinely single-device demo; remove it when assigning separate
  credentials, or its old shared owner remains accessible. Restart the API after
  revoking a credential. Never publish tokens or put them in an image/build argument.
- Create `db.env` (mode `0600`) with `POTPATROL_DATABASE_URL` using the
  `postgresql+psycopg://` driver and TLS (`sslmode=require` or stronger). Compose
  reads this file as **raw** to preserve special characters in the password.
  Both secret files are ignored by Git and the Docker build context.
- On the host, run `sudo docker compose -f compose.aws.yaml config --quiet`, then
  `sudo docker compose -f compose.aws.yaml run --rm --no-deps api alembic upgrade head`
  before starting new API code (the worker-fencing release requires revision
  `c8e0a12451d6`). Run `sudo docker compose -f compose.aws.yaml build api`
  and `sudo docker compose -f compose.aws.yaml up -d --no-build`.
- Verify `https://api.potpatrol.miami/health` **without disabling certificate
  validation**. The live fixture smoke covers HTTPS upload-init, authenticated
  MP4 PUT, `video_started_at`, worker completion, null GPS, `analysis_mode:fixture`,
  private evidence (401 without a token), and a review-only report destination.

The image includes CPU-only PyTorch and Param's pinned pothole model. Loading the
model on the instance succeeded, **but the running worker remains in fixture mode**.
Do not switch to `POTPATROL_ANALYSIS_MODE=model` or claim real detection acceptance
until a genuine pothole clip and clean clip have been evaluated and evidence
reviewed. Camera-app originals need private MP4 conversion for the upload API and
must not be assigned an unverified first-frame UTC/GPS. Final acceptance also
requires Shravya's iPhone test over this HTTPS endpoint.

Replaced MP4s now use distinct private keys; the service does not yet garbage-collect
unreferenced objects. Budget for cleanup and backup before long-term use.

For updates, check out a reviewed commit on the **feature branch** in the isolated
host directory, rebuild/recreate only this Compose project, and rerun migration
and smoke checks. Never copy the server `.env` or `db.env` into Git or a support
message. To stop billing, first preserve any required evidence, then stop the
isolated Compose stack, terminate its dedicated EC2 instance, release its Elastic
IP, and remove only its security group and dedicated key pair. Terminating EC2
will delete the encrypted root disk and private media; it does not delete the
external Tiger Cloud service.
