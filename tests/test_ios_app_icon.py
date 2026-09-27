"""Cross-platform contract for the generated iOS app icon project wiring."""
import json
import struct
from pathlib import Path


IOS = Path(__file__).resolve().parents[1] / "ios"


def test_ios_target_compiles_user_logo_as_primary_app_icon():
    icon_set = IOS / "NativeApp" / "Assets.xcassets" / "AppIcon.appiconset"
    manifest = json.loads((icon_set / "Contents.json").read_text(encoding="utf-8"))
    images = manifest["images"]
    assert len(images) == 1
    assert images[0]["idiom"] == "universal"
    assert images[0]["platform"] == "ios"
    assert images[0]["size"] == "1024x1024"
    icon = (icon_set / images[0]["filename"]).read_bytes()
    assert icon.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, depth, color, *_ = struct.unpack(">IIBBBBB", icon[16:29])
    assert (width, height, depth, color) == (1024, 1024, 8, 2)  # RGB, no alpha

    generator = (IOS / "scripts" / "generate_xcode_project.py").read_text(encoding="utf-8")
    project = (IOS / "PotPatrol.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    for source in (generator, project):
        assert "ASSETCATALOG_COMPILER_APPICON_NAME" in source
        assert "Assets.xcassets" in source
        assert "PBXResourcesBuildPhase" in source
    assert '"ASSETCATALOG_COMPILER_APPICON_NAME" = "AppIcon";' in project
