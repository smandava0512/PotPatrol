# Real-model review log (Developer 3)

Model: `peterhdd/pothole-detection-yolov8` @ `da7747ee`, sha256 `af2ac6ce…`, CPU unless noted. Default: conf 0.35, 4 FPS sampling.

## 2026-09-26: integration checks, not an acceptance test on real footage

| Check | Result |
| --- | --- |
| Dev 2 backend test suite (`feat/developer-2-backend` @ `9fed256`) against `potpatrol_vision` | **13/13 pass**, including no-GPS: hazards kept with `location: null`, `observed_at: null` |
| Dev 2 backend end-to-end in `POTPATROL_ANALYSIS_MODE=model` with no GPS | `status: complete`, `analysis_mode: model`, 1 hazard, `location: null`, evidence GET 200, report `needs_review` |
| ↳ input | **Simulated** 9 s 1280×720 clip: plain road, then a real pothole photo (Ryukijano test split `0676_jpg…`) zooming in from 2.97–5.94 s, then plain road |
| ↳ detection | 1 event at 4.03 s (inside the visible window), conf 0.96, box correctly on the pothole; no events on plain road |
| ↳ time | 3.3 s total processing for 9 s video (CPU laptop, incl. model already cached) |
| `fixtures/sample-drive.mp4` (backend/iOS placeholder) | 160×120, 4 frames: **not usable** for detection testing (0 detections at any threshold, as expected) |
| Still-image test split (100 images) | at conf 0.35: box recall 0.33, precision 0.63, 52/100 pothole images hit. See `worker/README.md` |

## Not yet done: blocks switching AWS to model mode

- **Original iPhone pothole and clean-road clips have not been reviewed.** Nothing above is real-footage acceptance.
- iPhone rotation (display-matrix) handling is implemented per PyAV docs but not yet verified on an actual iPhone `.MOV`.
- Threshold choice (0.25 / 0.35 / 0.5) is pending real-clip results.

Run when clips are available (kept private, git-ignored):

```
python worker/eval/review.py worker/eval/clips/POTHOLE.MOV worker/eval/clips/CLEAN.MOV --device cpu
```
