"""Detector adapter. The rest of the worker only sees `Detection` objects.

The model must expose a class literally named "pothole" (case-insensitive). A generic COCO checkpoint
is rejected with ModelError rather than silently producing zero hazards.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import numpy as np

from .schema import CATEGORIES, ModelError, env

# Pinned default model (Apache-2.0, YOLOv8s). https://huggingface.co/peterhdd/pothole-detection-yolov8
# Its checkpoint names its only class "0"; the model card states "Classes: 1 (pothole)" and the repo's
# val_batch1_pred.jpg shows class 0 boxes on potholes. The alias applies only to this exact file (sha256).
DEFAULT_MODEL = {
    "name": "peterhdd/pothole-detection-yolov8",
    "repo_id": "peterhdd/pothole-detection-yolov8",
    "filename": "best.pt",
    "revision": "da7747eea7abb4319a0f55961f31809a16c1b10a",
    "sha256": "af2ac6ce7bfec72e71643659ac946caf80ced84869e526a60135c457abfbb200",
    "class_aliases": {"0": "pothole"},
}


def _class_aliases(weights_sha256: str) -> dict[str, str]:
    """Verified aliases for the pinned model, plus explicit POTPATROL_CLASS_ALIASES='0=pothole,...'."""
    aliases = dict(DEFAULT_MODEL["class_aliases"]) if weights_sha256 == DEFAULT_MODEL["sha256"] else {}
    for pair in filter(None, env("CLASS_ALIASES").split(",")):
        k, _, v = pair.partition("=")
        aliases[k.strip()] = v.strip().lower()
    return aliases


@dataclass
class Detection:
    category: str
    confidence: float
    bbox: tuple[float, float, float, float]  # normalized x1,y1,x2,y2


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_weights() -> tuple[str, str]:
    """Return (display_name, local_weights_path). `POTPATROL_MODEL` may be a local .pt path."""
    override = env("MODEL")
    if override:
        if not os.path.isfile(override):
            raise ModelError(f"POTPATROL_MODEL={override!r} does not exist")
        return os.path.basename(override), override
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(DEFAULT_MODEL["repo_id"], DEFAULT_MODEL["filename"],
                               revision=DEFAULT_MODEL["revision"])
    except Exception as e:  # noqa: BLE001
        raise ModelError(f"could not fetch default weights ({DEFAULT_MODEL['repo_id']}); "
                         f"set POTPATROL_MODEL to a local .pt: {e}") from e
    return DEFAULT_MODEL["name"], path


class PotholeDetector:
    def __init__(self, conf_threshold: float = 0.35, device: str | None = None, imgsz: int = 640):
        self.name, self.weights_path = resolve_weights()
        try:
            from ultralytics import YOLO

            self.model = YOLO(self.weights_path)
        except Exception as e:  # noqa: BLE001
            raise ModelError(f"failed to load {self.weights_path}: {e}") from e
        self.conf_threshold = conf_threshold
        self.device = device
        self.imgsz = imgsz
        self.weights_sha256 = _sha256(self.weights_path)
        # Map model class ids -> contract categories; reject models without a pothole class.
        aliases = _class_aliases(self.weights_sha256)
        self.class_map: dict[int, str] = {}
        for cid, cname in self.model.names.items():
            key = str(cname).strip()
            key = aliases.get(key, key).lower()
            if key in CATEGORIES:
                self.class_map[int(cid)] = key
        if "pothole" not in self.class_map.values():
            raise ModelError(f"model {self.name} has no 'pothole' class (classes: {dict(self.model.names)}); "
                             "a generic detector is not pothole-ready")

    def describe(self) -> dict:
        return {
            "name": self.name,
            "weights_sha256": self.weights_sha256,
            "classes": sorted(set(self.class_map.values())),
            "model_classes": {int(k): str(v) for k, v in self.model.names.items()},
            "conf_threshold": self.conf_threshold,
            "imgsz": self.imgsz,
        }

    def detect(self, images: list[np.ndarray]) -> list[list[Detection]]:
        """Run on a batch of BGR images; returns detections per image."""
        try:
            results = self.model.predict(images, conf=self.conf_threshold, device=self.device,
                                         imgsz=self.imgsz, verbose=False)
        except Exception as e:  # noqa: BLE001
            raise ModelError(f"inference failed: {e}") from e
        out: list[list[Detection]] = []
        for img, res in zip(images, results):
            h, w = img.shape[:2]
            dets: list[Detection] = []
            if res.boxes is not None and len(res.boxes):
                xyxy = res.boxes.xyxy.cpu().numpy()
                confs = res.boxes.conf.cpu().numpy()
                clss = res.boxes.cls.cpu().numpy().astype(int)
                for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                    cat = self.class_map.get(int(k))
                    if cat is None:
                        continue
                    box = (float(np.clip(x1 / w, 0, 1)), float(np.clip(y1 / h, 0, 1)),
                           float(np.clip(x2 / w, 0, 1)), float(np.clip(y2 / h, 0, 1)))
                    if box[2] - box[0] <= 0 or box[3] - box[1] <= 0:
                        continue
                    dets.append(Detection(cat, float(c), box))
            out.append(dets)
        return out
