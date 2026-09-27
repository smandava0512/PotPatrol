# potpatrol-vision (Developer 3)

Offline drive-video analysis → a few pothole events with timestamps and evidence JPEGs, plus report drafting and
Florida reporting-destination lookup. Contract: [`docs/contracts/analysis.md`](../docs/contracts/analysis.md).

## Setup

```bash
python -m venv .venv
# GPU (RTX 50xx needs CUDA 12.8 wheels); skip this line for CPU-only
.venv/Scripts/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/pip install -e "worker[dev]"
```

The default model is [`peterhdd/pothole-detection-yolov8`](https://huggingface.co/peterhdd/pothole-detection-yolov8)
(YOLOv8s, Apache-2.0, single class `Pothole`). It downloads to the Hugging Face cache on first run.
Pin `POTPATROL_MODEL_REVISION=<commit>` or set `POTPATROL_MODEL=/path/to/best.pt` to use a local/offline file.
Worker startup rejects any checkpoint without a `pothole` class, such as generic COCO YOLO (`ModelError`, exit 3).

### Measured so far (2026-09-26, RTX 5060 Laptop, CUDA 12.8, torch 2.11, ultralytics 8.4.163)

Still images from the model's dataset test split ([Ryukijano/Pothole-detection-Yolov8](https://huggingface.co/datasets/Ryukijano/Pothole-detection-Yolov8), 100 images / 269 boxes; box match at IoU ≥ 0.3):

| conf | box recall | box precision | pothole images with ≥1 hit |
| --- | --- | --- | --- |
| 0.15 | 0.40 | 0.52 | 59/100 |
| 0.25 | 0.36 | 0.56 | 55/100 |
| 0.35 (default) | 0.33 | 0.63 | 52/100 |
| 0.50 | 0.31 | 0.72 | 50/100 |

Per-frame recall is weak. In video, each pothole passes through several sampled frames, so event recall should be
higher, but that is **not yet measured on real drive footage**. The model's own validation preview also shows a box on
a manhole cover, so treat manholes as a known false-positive risk. Speed: 10 s 720p clip → 40 sampled frames in 6.2 s end to end, including model load.
Next: run `eval/evaluate.py` on our own positive/negative clips. If it misses, fine-tune with `train/finetune.py`
on a Roboflow Universe pothole export plus ~100 labeled frames from our footage.

## Run

```bash
python -m potpatrol_vision path/to/drive.mp4 runs/drive1            # real analysis
python -m potpatrol_vision ignored runs/fixture --fixture           # deterministic sample (demo fallback)
POTPATROL_ANALYSIS_MODE=fixture python -m potpatrol_vision ...       # same, via env for the backend
```

Output: `runs/drive1/analysis.json` and `runs/drive1/evidence/event-NNN.jpg` (boxed) / `event-NNN-raw.jpg`.
Exit codes: `0` ok (including `events: []`), `2` invalid video, `3` model error, `1` other crash. On failure, stderr has a JSON error line and no manifest is written.

Tuning flags: `--sample-fps` (default 4), `--conf` (default 0.35), `--device cpu|0`. Merge thresholds are in
`potpatrol_vision/events.py::MergeParams` and are recorded in every manifest.

## Evaluate on your own clips

1. Put clips in `worker/eval/clips/` (git-ignored): at least one pothole-positive and one negative (smooth road, with shadows/manholes/patches if possible).
2. Copy `eval/labels.example.csv` to `eval/labels.csv`. For each pothole, scrub the video and write the ms offset where it is closest and clearest. Leave negatives empty.
3. `python worker/eval/evaluate.py worker/eval/labels.csv --conf 0.25 0.35 0.5`
4. Open `worker/eval/out/conf*/<clip>/evidence/*.jpg` and check every event against the labels.

## Required Gemini-assisted real analysis (explicit opt-in)

With authorization for **selected JPEG frames only**, install `worker[gemini]`, set `GEMINI_API_KEY` in a private runtime environment, `POTPATROL_ANALYSIS_MODE=model` and `POTPATROL_VISION_MODE=gemini_required`. No full MP4, GPS, UTC timestamp, or other metadata is sent to Google; only up to 24 resized selected road-frame JPEGs (one request each), plus up to 12 YOLO candidate evidence JPEGs. Selection progressively thins 4-fps PTS-sampled frames across the clip in one pass; long clips are therefore sampled sparsely and individual hazards between samples can still be missed. Gemini checks every retained YOLO candidate (negative responses remove it) and independently scans selected frames even when YOLO found none. Scan-only findings get a frame-backed box, `source=gemini_scan`, the Gemini score and `needs_review`; YOLO positives also remain `needs_review` until a human checks. `road_damage` denotes rough/broken road surface that is not clearly a pothole. Zero events is success only after all selected scans completed.

Fixture selection, missing key/SDK, malformed or failed provider response, or >12 YOLO candidates fail the job with no `analysis.json`; there is **no** YOLO-only fallback. The manifest keeps `mode=model`, adds `vision_mode=gemini_required`, `gemini_frames_scanned`, `model` (actual YOLO description), and `validator` (actual Gemini model). This is not a measured accuracy guarantee. Original positive and clean clips have not been retested with Gemini; costs and Google data retention require review before deploying. The AWS Compose template is staged for this mode and refuses to render without a private key, but this commit does not deploy or upload media.

## Optional Gemini check

Off by default. It sends at most `POTPATROL_VALIDATE_MAX` (default 5) raw evidence JPEGs per clip to Google, so get Dev 2's OK first.

```bash
.venv/Scripts/pip install -e "worker[gemini]"
# put GEMINI_API_KEY=... in the repo-root .env (git-ignored), then:
python -m potpatrol_vision.validators worker/potpatrol_vision/fixtures/evidence/event-001-raw.jpg   # one-image check
POTPATROL_VALIDATOR=gemini python -m potpatrol_vision path/to/drive.mp4 runs/drive1
```

Results appear as an advisory `validation` object on events and as `ai_check` in reports. They never drop an event.
Any API error is logged to stderr and the run continues without it.

## Report + destination

```python
from potpatrol_vision.report import draft_report
draft_report(hazard, "evidence/event-001-raw.jpg", 25.7563, -80.374, 8.0, "2026-09-26T18:04:12Z", user_reviewed=True)
```

The destination registry is `potpatrol_vision/data/fl_registry.json`. Every URL carries its official source and the date
it was checked. GPS alone never proves road ownership, so Miami-Dade points resolve to `needs_review` with city,
county and FDOT candidates. A `verified` result needs an authoritative ownership source (`owner_hint`) or a verified `ownership_zone`.

## Tests

```bash
cd worker && ../.venv/Scripts/python -m pytest -q
```
