"""Prefer the newest available iOS runtime and an iPhone Pro simulator."""
import json
import re
import subprocess

devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "--json"]))["devices"]
candidates = []
for runtime, group in devices.items():
    if ".iOS-" not in runtime:
        continue
    version = tuple(int(item) for item in re.findall(r"\d+", runtime))
    for device in group:
        if device["name"].startswith("iPhone"):
            preference = ("17 Pro" in device["name"], "Pro" in device["name"])
            candidates.append((version, preference, device["udid"]))
if not candidates:
    raise SystemExit("No available iPhone Simulator runtime")
print(max(candidates)[2])
