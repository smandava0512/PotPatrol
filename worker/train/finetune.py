"""Small fine-tune of the pinned pothole model on a YOLO-format dataset (e.g. a Roboflow Universe pothole export
plus frames labeled from our own drive footage). Single class; the class must be named `pothole`.

  python worker/train/finetune.py path/to/data.yaml --epochs 40 --imgsz 640 --batch 16
  POTPATROL_MODEL=runs/detect/potpatrol-ft/weights/best.pt python worker/eval/evaluate.py worker/eval/labels.csv

Adopt new weights only if evaluate.py shows fewer misses without more confirmed false positives on OUR clips,
then log the model change in docs/coordination/changes.md (it changes output semantics).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--base", default=None, help="starting weights (default: pinned peterhdd best.pt)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="0")
    ap.add_argument("--name", default="potpatrol-ft")
    a = ap.parse_args()

    import yaml
    from ultralytics import YOLO

    names = yaml.safe_load(open(a.data, encoding="utf-8")).get("names")
    names = list(names.values()) if isinstance(names, dict) else names
    if [str(n).lower() for n in names] != ["pothole"]:
        sys.exit(f"data.yaml names must be ['pothole'], got {names}; relabel so the checkpoint is self-describing")

    base = a.base
    if base is None:
        from potpatrol_vision.detector import resolve_weights

        base = resolve_weights()[1]
    model = YOLO(base)
    model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device, name=a.name,
                patience=10, cos_lr=True, close_mosaic=5, seed=0, deterministic=True)
    print("best weights:", os.path.join(model.trainer.save_dir, "weights", "best.pt"))


if __name__ == "__main__":
    main()
