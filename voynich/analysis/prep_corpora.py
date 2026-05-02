"""Extract plain text from raw corpus files.

Source URLs (re-fetch with curl to voynich/data/comparison/):
  latin_pliny.xml:
    https://raw.githubusercontent.com/PerseusDL/canonical-latinLit/master/data/phi0978/phi001/phi0978.phi001.perseus-lat2.xml
  finnish_bible.xml:
    https://raw.githubusercontent.com/christos-c/bible-corpus/master/bibles/Finnish.xml
  italian_dc.json:
    https://raw.githubusercontent.com/fabiovalse/Divina-Commedia-Visualization/master/divina_commedia.json
  english_pp.txt:
    https://raw.githubusercontent.com/GITenberg/Pride-and-Prejudice_1342/master/1342.txt

This script reads those raw files and writes the cleaned .txt versions that
word_families.py consumes. The extracted .txt files are committed; raw
sources are not (re-fetch via curl + run this script if you need to
regenerate).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "comparison"


def strip_tei(text: str) -> str:
    # remove XML declarations and comments
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # remove the <teiHeader>...</teiHeader> entirely (metadata)
    text = re.sub(r"<teiHeader.*?</teiHeader>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # drop all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # decode common entities
    text = (text.replace("&amp;", "&")
                 .replace("&lt;", "<")
                 .replace("&gt;", ">")
                 .replace("&apos;", "'")
                 .replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


def extract_pliny():
    src = DIR / "latin_pliny.xml"
    raw = src.read_text(encoding="utf-8", errors="ignore")
    text = strip_tei(raw)
    out = DIR / "latin_pliny.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Pliny: {len(text)} chars -> {out}")


def extract_finnish_bible():
    src = DIR / "finnish_bible.xml"
    raw = src.read_text(encoding="utf-8", errors="ignore")
    # CES corpus: keep <seg> contents; drop everything else
    segs = re.findall(r"<seg[^>]*>(.*?)</seg>", raw, flags=re.DOTALL | re.IGNORECASE)
    text = " ".join(re.sub(r"\s+", " ", s).strip() for s in segs)
    text = (text.replace("&amp;", "&")
                 .replace("&apos;", "'")
                 .replace("&quot;", '"'))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    out = DIR / "finnish_bible.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Finnish Bible: {len(text)} chars -> {out}")


def extract_dc():
    src = DIR / "italian_dc.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    parts = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("text")
            if t:
                parts.append(t)
            for c in node.get("children", []):
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(data)
    text = " ".join(parts)
    out = DIR / "italian_dc.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Divina Commedia: {len(text)} chars -> {out}")


def extract_pp():
    src = DIR / "english_pp.txt"
    raw = src.read_text(encoding="utf-8", errors="ignore")
    # Strip Gutenberg header / footer
    m1 = re.search(r"\*\*\* START OF.*?\*\*\*", raw)
    m2 = re.search(r"\*\*\* END OF.*?\*\*\*", raw)
    if m1 and m2:
        text = raw[m1.end():m2.start()]
    else:
        text = raw
    text = re.sub(r"\s+", " ", text).strip()
    out = DIR / "english_pp_clean.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Pride&Prejudice: {len(text)} chars -> {out}")


if __name__ == "__main__":
    extract_pliny()
    extract_finnish_bible()
    extract_dc()
    extract_pp()
