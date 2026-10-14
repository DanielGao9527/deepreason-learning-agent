"""Build searchable local text from pinned OpenDSA source files; no network calls."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workbench" / "deepreason" / "learning_mvp"
SOURCE = WORKSPACE / "source" / "OpenDSA"
KNOWLEDGE = WORKSPACE / "knowledge"
COMMIT = "e02a274498fb8dd5fdcad9ee75bcb02f0efe8bc4"
FILES = {
    "RST/en/Hashing/HashIntro.rst": ("04_opendsa_hashing.txt", "625A0BE83942A3D73C40C54F12D23B1622D73EC5B649E1765BBF09EEC7265CC6"),
    "RST/en/Binary/BST.rst": ("05_opendsa_bst.txt", "9CD45F24E66685935F124403681222DFD41602C239460063D3B825D0D977AFBB"),
    "RST/en/AlgAnal/AnalCases.rst": ("06_opendsa_analysis.txt", "3D6B1EC7DB025AF6B8B863E46FDCF735722D1A874154224F8F1668B81FE69ECF"),
}


def readable_rst(source: str) -> str:
    """Drop embedded widgets/metadata while retaining textbook paragraphs."""
    lines = []
    skipping = False
    for line in source.splitlines():
        if line.startswith(".. "):
            skipping = True
            continue
        if skipping and (line.startswith("   ") or not line.strip()):
            continue
        skipping = False
        if re.fullmatch(r"[=~^-]{3,}", line.strip()):
            continue
        line = re.sub(r":\w+:`([^`]+)`", lambda match: match.group(1).split(" <", 1)[0], line)
        line = line.replace("``", "").replace("**", "").replace("|---|", "—")
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    KNOWLEDGE.mkdir(parents=True, exist_ok=True)
    rows = []
    for relative, (name, expected_hash) in FILES.items():
        original = SOURCE / relative
        data = original.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest().upper()
        if actual_hash != expected_hash:
            raise ValueError(f"OpenDSA source hash mismatch: {relative}")
        url = f"https://github.com/OpenDSA/OpenDSA/blob/{COMMIT}/{relative}"
        header = f"原文页面：{url}\n来源：OpenDSA，MIT；固定提交 {COMMIT}\n\n"
        text = header + readable_rst(data.decode("utf-8"))
        (KNOWLEDGE / name).write_text(text, encoding="utf-8")
        rows.append({"source": relative, "local": name, "sha256": actual_hash, "url": url, "characters": len(text)})
    manifest = {"repository": "https://github.com/OpenDSA/OpenDSA", "commit": COMMIT,
                "license_file": "source/OpenDSA/MIT-license.txt", "documents": rows}
    (WORKSPACE / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
