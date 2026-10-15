#!/usr/bin/env python3
"""Create a single-file offline preview from the same production assets."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

def build(output: Path) -> None:
    html = (PUBLIC / "index.html").read_text()
    css = (PUBLIC / "styles.css").read_text()
    js = (PUBLIC / "app.js").read_text()
    data = {name: json.loads((PUBLIC / "data" / filename).read_text()) for name, filename in
            [("live", "latest.json"), ("status", "status.json"), ("history", "history.json")]}
    embedded = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>')
    html = html.replace('<script src="app.js" defer></script>', '<script>window.GARRISON_EMBEDDED=' + embedded + ';</script>\n<script>\n' + js + '\n</script>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    build(p.parse_args().output)
