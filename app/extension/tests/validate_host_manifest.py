#!/usr/bin/env python3
"""Validate the native-messaging host manifests (S13 finish).

Checks `com.fetchline.host.json` (Chromium family: Chrome, Edge)
and `com.fetchline.host.firefox.json` (Firefox family) in
app/extension/ against the rules Chrome and Firefox actually
enforce, verified against Chrome's native-messaging docs
(developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
and Firefox's (MDN: Native messaging):

  * both files are valid JSON with name "com.fetchline.host",
    type "stdio", a non-empty description, and a Windows absolute
    path to fetchline-host.exe (the installer edits `path` to the
    installed location);
  * the Chromium file lists callers in `allowed_origins`, one entry
    per extension, each exactly `chrome-extension://<id>/` — the
    id is 32 lowercase a-p characters and the trailing slash is
    mandatory; no wildcards are allowed. The repo copy carries the
    placeholder `__FETCHLINE_EXTENSION_ID__` instead of a real id:
    that is a WARNING, not a failure — the installer replaces it
    with the id from chrome://extensions. A wrong id is the most
    common handshake failure (the popup then says the desktop app
    is not reachable).
  * the Firefox file lists callers in `allowed_extensions`, NOT
    `allowed_origins` — Firefox rejects a manifest that contains
    `allowed_origins` instead; the keys are not interchangeable,
    so the two files must stay separate (BUG-022: the README used
    to say Firefox takes the same file, which would never
    connect). Each entry is the add-on id from
    manifest.json's `browser_specific_settings.gecko.id`.

Run with `npm run test:extension` from app/, or directly:
    python3 app/extension/tests/validate_host_manifest.py
Exit code 0 means both manifests are valid (a placeholder id is
a warning, printed, not a failure); anything else prints the
problems and exits 1.
"""
import json
import re
import sys
from pathlib import Path

HOST_NAME = "com.fetchline.host"
# A Chrome extension id is 32 characters drawn from a-p (it is the
# first 32 characters of the public key's hash, base32-encoded).
CHROME_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}/$")
PLACEHOLDER_ORIGIN = "chrome-extension://__FETCHLINE_EXTENSION_ID__/"
WINDOWS_EXE_RE = re.compile(r"^[A-Za-z]:\\.+fetchline-host\.exe$")


def load(root, name, problems):
    path = root / name
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        problems.append(f"cannot read {path}: {e}")
        return None


def check_common(manifest, name, problems):
    if manifest.get("name") != HOST_NAME:
        problems.append(f"{name}: name must be {HOST_NAME}")
    if manifest.get("type") != "stdio":
        problems.append(f"{name}: type must be stdio")
    if not manifest.get("description", "").strip():
        problems.append(f"{name}: description must not be empty")
    path = manifest.get("path", "")
    if not isinstance(path, str) or not WINDOWS_EXE_RE.match(path):
        problems.append(
            f"{name}: path must be a Windows absolute path to fetchline-host.exe, got {path!r}"
        )


def check_chromium(root, problems, warnings):
    manifest = load(root, "com.fetchline.host.json", problems)
    if manifest is None:
        return
    check_common(manifest, "com.fetchline.host.json", problems)
    if "allowed_extensions" in manifest:
        problems.append(
            "com.fetchline.host.json: allowed_extensions belongs in the Firefox file, not here"
        )
    origins = manifest.get("allowed_origins")
    if not isinstance(origins, list) or not origins:
        problems.append("com.fetchline.host.json: allowed_origins must be a non-empty list")
        return
    for origin in origins:
        if origin == PLACEHOLDER_ORIGIN:
            warnings.append(
                "com.fetchline.host.json: allowed_origins still carries the "
                "__FETCHLINE_EXTENSION_ID__ placeholder — the installer must "
                "replace it with the id from chrome://extensions"
            )
        elif not CHROME_ORIGIN_RE.match(origin):
            problems.append(
                f"com.fetchline.host.json: allowed_origins entry {origin!r} is not "
                "chrome-extension://<32 lowercase a-p chars>/ (trailing slash mandatory, no wildcards)"
            )


def check_firefox(root, problems, warnings):
    manifest = load(root, "com.fetchline.host.firefox.json", problems)
    if manifest is None:
        return
    check_common(manifest, "com.fetchline.host.firefox.json", problems)
    if "allowed_origins" in manifest:
        problems.append(
            "com.fetchline.host.firefox.json: Firefox rejects allowed_origins — "
            "its allow-list key is allowed_extensions (BUG-022)"
        )
    # The Firefox allow-list must name the add-on id the extension
    # declares in manifest.json, or nothing can connect.
    try:
        ext = json.loads((root / "manifest.json").read_text())
        gecko_id = ext.get("browser_specific_settings", {}).get("gecko", {}).get("id", "")
    except (OSError, json.JSONDecodeError) as e:
        problems.append(f"cannot read manifest.json for the Firefox id: {e}")
        return
    allowed = manifest.get("allowed_extensions")
    if not isinstance(allowed, list) or not allowed:
        problems.append(
            "com.fetchline.host.firefox.json: allowed_extensions must be a non-empty list"
        )
        return
    for entry in allowed:
        if entry != gecko_id:
            problems.append(
                f"com.fetchline.host.firefox.json: allowed_extensions entry {entry!r} "
                f"must be the extension's Firefox id {gecko_id!r} from manifest.json"
            )
    if not gecko_id:
        warnings.append(
            "com.fetchline.host.firefox.json: manifest.json sets no gecko id, "
            "so the Firefox allow-list cannot be checked"
        )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = []
    warnings = []
    check_chromium(root, problems, warnings)
    check_firefox(root, problems, warnings)
    for w in warnings:
        print(f"WARN: {w}")
    if problems:
        print("FAIL: host manifest problems:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: host manifests are valid (Chrome: allowed_origins, Firefox: allowed_extensions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
