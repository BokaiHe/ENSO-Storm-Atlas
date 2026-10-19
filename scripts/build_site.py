"""Assemble the single-file website: site/template.html + build/data.json + build/ml_results.json + build/decomp.json + land outlines -> docs/index.html
(and build/artifact.html, the same page without the <html>/<head> wrapper).

The template already contains the page's CSS, JavaScript and both languages (EN / 中文);
this step only embeds the data so the page works offline and on GitHub Pages.

Usage: python scripts/build_site.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def land_geojson():
    """Decode the world-atlas TopoJSON land layer, keeping polygons that touch the Atlantic window."""
    topo = json.loads((ROOT / "data" / "raw" / "land50.json").read_text(encoding="utf-8"))
    sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for a in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append([round(x * sc[0] + tr[0], 3), round(y * sc[1] + tr[1], 3)])
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(seg if not out else seg[1:])
        return out

    polys = []
    for g in topo["objects"]["land"]["geometries"]:
        for poly in g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]:
            rings = [ring(r) for r in poly]
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            if max(xs) < -125 or min(xs) > 15 or max(ys) < -8 or min(ys) > 72:
                continue
            polys.append(rings)
    return json.dumps({"type": "MultiPolygon", "coordinates": polys}, separators=(",", ":"))


if __name__ == "__main__":
    template = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
    data = (ROOT / "build" / "data.json").read_text(encoding="utf-8").replace("</", "<\\/")
    ml_path = ROOT / "build" / "ml_results.json"  # written by analyze.py; the classification chart reads it
    if not ml_path.exists():
        raise SystemExit("build/ml_results.json is missing: run python scripts/analyze.py first")
    ml = json.dumps(json.loads(ml_path.read_text(encoding="utf-8")), separators=(",", ":"))
    dec_path = ROOT / "build" / "decomp.json"  # written by decompose.py
    if not dec_path.exists():
        raise SystemExit("build/decomp.json is missing: run python scripts/decompose.py first")
    dec = json.dumps(json.loads(dec_path.read_text(encoding="utf-8")), separators=(",", ":"))
    page = template.replace("__DATA__", data).replace("__LAND__", land_geojson()).replace("__ML__", ml).replace("__DEC__", dec)
    # the template is a page fragment (the Artifact host adds the skeleton); wrap it for standalone use,
    # moving <title>, font links and <style> into <head>
    cut = page.index('<div class="wrap">')
    head, body = page[:cut], page[cut:]
    html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + head + '</head>\n<body style="margin:0">\n' + body + '\n</body>\n</html>\n')
    # same page as a fragment, for publishing as a claude.ai Artifact (the host adds the skeleton)
    (ROOT / "build" / "artifact.html").write_text(page, encoding="utf-8")
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} KB)")
