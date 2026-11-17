"""One-time vendoring of the esm.sh Excalidraw bundle for offline rendering.

Recursively downloads the pinned @excalidraw/excalidraw@0.17.6 bundle and all
its esm.sh dependencies into ./vendor/, rewriting absolute "/..." imports to
relative "./<flat-name>" so render_template.html works without CDN access.

Usage: python3 vendor_deps.py [--proxy http://127.0.0.1:6616]
"""
import argparse
import re
import urllib.request
from pathlib import Path

BASE = "https://esm.sh"
ENTRY = "/@excalidraw/excalidraw@0.17.6/es2022/excalidraw.bundle.mjs"
IMPORT_RE = re.compile(r'((?:from|import)\s*)"(\/[^"]+)"')
REL_IMPORT_RE = re.compile(r'((?:from|import)\s*)"(\./[^"]+)"')


def flat_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "_", path.lstrip("/")) + ".mjs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy", default=None)
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "vendor"
    out_dir.mkdir(exist_ok=True)

    handlers = []
    if args.proxy:
        handlers.append(urllib.request.ProxyHandler({"https": args.proxy, "http": args.proxy}))
    opener = urllib.request.build_opener(*handlers)

    queue = [ENTRY]
    seen = set()
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        url = BASE + path
        with opener.open(url, timeout=120) as resp:
            src = resp.read().decode("utf-8")
        deps = IMPORT_RE.findall(src)
        for _, dep in deps:
            if dep not in seen:
                queue.append(dep)
        # Relative imports resolve against the module's esm.sh directory;
        # handle them first so rewritten absolute imports are not re-mapped
        parent = path.rsplit("/", 1)[0]
        rel_deps = REL_IMPORT_RE.findall(src)
        for _, dep in rel_deps:
            abs_dep = parent + dep[1:]
            if abs_dep not in seen:
                queue.append(abs_dep)
        rewritten = REL_IMPORT_RE.sub(
            lambda m: m.group(1) + '"./' + flat_name(parent + m.group(2)[1:]) + '"', src
        )
        rewritten = IMPORT_RE.sub(lambda m: m.group(1) + '"./' + flat_name(m.group(2)) + '"', rewritten)
        target = out_dir / flat_name(path)
        target.write_text(rewritten, encoding="utf-8")
        print(f"saved {target.name} ({len(src)} bytes, {len(deps)} deps)")

    print(f"done: {len(seen)} modules; entry = vendor/{flat_name(ENTRY)}")


if __name__ == "__main__":
    main()