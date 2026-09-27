# Isolated AWS demo (not production)

`api.potpatrol.miami` points to a dedicated Amazon Linux EC2 instance in `us-east-1`
(`i-08cecb8ac62f95379`, Elastic IP `52.2.5.209`). The `potpatrol-aws`
Compose project runs API, worker and Caddy; only Caddy publishes ports 80/443.
SSH on its dedicated security group is restricted to the operator's current IP.
The unrelated workshop CodeEditor instance and SageMaker bucket are not part of
this deployment.

The database is the **existing** PotPatrol Tiger Cloud PostgreSQL service. Alembic
revision `c8e0a12451d6` has been applied and `jobs.claim_token` independently checked. Videos and
JPEG evidence use an authenticated API and a private Docker volume on the
instance's encrypted EC2 disk; there is **no S3 backup or multi-host durability**.
The EC2 instance, disk and public IPv4 address can incur charges while running.

## Configuration and runbook

- Current API/worker release: `/home/ec2-user/potpatrol-releases/03fe24f`, from
  `dev3-vision` commit `03fe24f3a0b681834dd02e7d4529dd06860abdf5` (PR #2 remains open).
  The older checkout and Caddy bind mount remain at `/home/ec2-user/potpatrol-backend`;
  do not use that stale source directory to rebuild the app. Compose project/volumes
  are still `potpatrol-aws`; no database or media was replaced.
- On that host, keep `.env` (mode `0600`) for device tokens and general settings; the currently running release explicitly selects `POTPATROL_ANALYSIS_MODE=fixture`. **The staged Compose template is not yet live**: it overrides mode to `model` with `gemini_required`. Put `GEMINI_API_KEY=<private key>` in a separate, ignored, mode-`0600` `gemini.env` beside Compose, **not** in `.env` or a Compose `environment:` value. Only the worker loads `gemini.env`; it refuses to start without the key/SDK and never falls back to fixture output. Review the real-clip and cost results before deploying. Selected road-frame JPEGs (up to 24) and candidate evidence JPEGs (up to 12) leave the host for Google; videos and GPS do not. Use
  `POTPATROL_DEVICE_TOKENS` with one distinct, random credential per participating
  device, delivered privately. The legacy `POTPATROL_DEVICE_TOKEN` may be used
  only for a genuinely single-device demo; remove it when assigning separate
  credentials, or its old shared owner remains accessible. Restart the API after
  revoking a credential. Never publish tokens or put them in an image/build argument.
- Create `db.env` (mode `0600`) with `POTPATROL_DATABASE_URL` using the
  `postgresql+psycopg://` driver and TLS (`sslmode=require` or stronger). Compose
  reads this file as **raw** to preserve special characters in the password.
  All three secret files (`.env`, `db.env`, `gemini.env`) must be ignored by Git and the Docker build context. Never print the expanded Compose config; use `config --quiet`.
- From the selected release directory, run `sudo docker compose -f compose.aws.yaml config --quiet`,
  preserve the previous image tag, then `sudo docker compose -f compose.aws.yaml build api`.
  Stop/drain the old worker before replacing lease logic. Run
  `sudo docker compose -f compose.aws.yaml run --rm --no-deps api alembic upgrade head`
  using the **newly built image**, then read back its revision/required columns before
  starting new code. Run `sudo docker compose -f compose.aws.yaml up -d --no-build --no-deps --wait api worker`.
  The currently preserved rollback image is `potpatrol-aws:pre-phone-03fe24f`.
- Verify `https://api.potpatrol.miami/health` **without disabling certificate
  validation**. The live fixture smoke covers HTTPS upload-init, authenticated
  MP4 PUT, `video_started_at`, worker completion, null GPS, `analysis_mode:fixture`,
  private evidence (401 without a token), and a review-only report destination.

The image includes CPU-only PyTorch and Param's pinned pothole model. Isolated
analysis of the supplied pothole-labelled and clear Camera-app clips found no
events on the clear clip, but YOLO identified curbs/parking stops instead of
convincing potholes on the labelled clip. Gemini-assisted accuracy **has not
been evaluated with the actual key**, and the live worker remains in fixture mode.
Do not claim accurate real detection merely because a model loaded or Gemini ran;
review both clips' actual Gemini evidence first. Camera-app originals need private
MP4 conversion for the upload API and must not be assigned an unverified first-frame
UTC/GPS. Final acceptance also requires Shravya's iPhone test over this endpoint.

Replaced MP4s now use distinct private keys; the service does not yet garbage-collect
unreferenced objects. Budget for cleanup and backup before long-term use.

## Phone contract verification

Release `03fe24f` passed public trusted-HTTPS upload → GPS → completion → fixture
worker → authenticated JPEG → scalar report draft checks. Re-fetch repairs the
old wrapped server draft without changing its report ID; phone caches need the
app's Refresh draft action. Gemini remains off **in the live release**. The staged
Compose file in this branch requires Gemini, and has not been deployed.

Existing test drive: `f1dda379-bf7c-47b1-a238-437ebcd74f61`.
New no-GPS fixture: `921da0f1-6bd3-4cd7-aef9-1e2dc599d7a1`.
New fixture with **synthetic Miami GPS**: `e74330c2-1012-4b6b-9caa-229991ddf7bc`.
All three are complete with two synthetic hazards; they require their existing
private demo credential. Never hard-code them as new recording IDs. HTTP 401 for
unauthenticated evidence, immutable completed uploads (409), duplicate GPS, and
idempotent completion/report fetch were checked. Real inference and physical-phone
acceptance remain outstanding; these fixtures do not establish either.

For updates, check out a reviewed commit on the **feature branch** in the isolated
host directory, rebuild/recreate only this Compose project, and rerun migration
and smoke checks. Never copy the server `.env` or `db.env` into Git or a support
message. To stop billing, first preserve any required evidence, then stop the
isolated Compose stack, terminate its dedicated EC2 instance, release its Elastic
IP, and remove only its security group and dedicated key pair. Terminating EC2
will delete the encrypted root disk and private media; it does not delete the
external Tiger Cloud service.
