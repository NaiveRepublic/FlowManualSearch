"""
Build the offline search index for Flow Finder.

Run once per manual version (e.g. when a new Dirac Flow manual ships):
    python build_tools/build_index.py path\\to\\manual.pdf

Writes to app/data/:
    chunks.json      passages with section, chapter and page metadata
    vectors.npy      one normalised embedding per passage (float16)
    embed.npy        token-embedding table used to embed questions (float16)
    tokenizer.json   tokenizer matching the embedding table
    pages/NN.jpg     page previews shown inside the app
    manual.pdf       copy of the manual, opened by "Open in PDF viewer"
"""
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"

NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s*$")
NUM_TITLE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$")
FOOTER_RE = re.compile(r"^(www\.dirac\.com|\d{1,3})$")
SOFT = "\x00"  # marker for a soft hyphen at a line break


def clean(t: str) -> str:
    t = t.replace("\xad", SOFT)
    t = unicodedata.normalize("NFKC", t).replace("\t", " ")
    return re.sub(r"\s+", " ", t).strip()


def read_lines(doc, first_page):
    """Yield (page, kind, text, bold, box); kind is 'h1', 'h2', 'h3' or 'text'.
    box is the line's position as fractions of the page (x0, y0, x1, y1)."""
    for pno in range(first_page, len(doc)):
        W, H = doc[pno].rect.width, doc[pno].rect.height
        for block in doc[pno].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = clean("".join(s["text"] for s in spans))
                if not text:
                    continue
                size = max(s["size"] for s in spans)
                if size < 6:  # tiny callout numbers inside screenshots
                    continue
                if FOOTER_RE.match(text.replace(SOFT, "")):
                    continue
                bold = any(k in spans[0]["font"] for k in ("SemiBold", "Bold", "Black"))
                kind = "text"
                if bold and size >= 13.5:
                    kind = "h1"
                elif bold and size >= 10.5:
                    kind = "h2"
                elif bold and re.match(r"^\d+\.\d+\.\d+\.", text):
                    kind = "h3"
                x0, y0, x1, y1 = line["bbox"]
                box = [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)]
                yield pno + 1, kind, text, bold, box


def parse_sections(pdf_path):
    doc = pymupdf.open(pdf_path)
    sections, cur, chapter, pending_num, pending_box = [], None, "", None, None
    for page, kind, text, bold, box in read_lines(doc, first_page=2):  # skip cover + contents
        if kind == "text" and bold:
            if pending_num:  # bold title on the line after its number
                kind = "h3"
            elif cur and not cur["body"] and re.search(r"(,|\band|\bor|&)$", cur["title"]):
                cur["title"] += " " + text.replace(SOFT, "")  # wrapped heading
                cur["anchor"] = union(cur["anchor"], box)
                continue
        if kind != "text":
            m_num = NUM_RE.match(text)
            if m_num:  # number on its own line, title follows
                pending_num, pending_box = m_num.group(1), box
                continue
            m = NUM_TITLE_RE.match(text)
            if m:
                num, title = m.group(1), m.group(2)
            elif pending_num:
                num, title = pending_num, text
                if pending_box:
                    box = union(pending_box, box)
            else:  # second line of a long heading, or bold inline text
                if cur and not cur["body"]:
                    cur["title"] += " " + text
                elif cur:
                    cur["body"].append((page, text))
                continue
            pending_num = None
            title = title.replace(SOFT, "")
            if num.count(".") == 0:
                chapter = f"{num}. {title}"
            cur = {"num": num, "title": title, "chapter": chapter,
                   "level": num.count(".") + 1, "page": page, "anchor": box, "body": []}
            sections.append(cur)
            continue
        if pending_num and cur is not None:  # a lone number that was a list item
            cur["body"].append((page, pending_num + "."))
            pending_num = None
        if cur is not None:
            cur["body"].append((page, text))
    return doc, sections


def union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def section_words(section):
    """Join wrapped lines (healing soft hyphens) and tag every word with its page."""
    words = []
    for page, text in section["body"]:
        first, *rest = text.split(" ")
        prev = words[-1][0] if words else ""
        if prev.endswith(SOFT):  # soft hyphen: one word split over two lines
            words[-1] = (prev[:-1] + first, words[-1][1])
            words += [(w, page) for w in rest]
        elif re.search(r"[A-Za-z]-$", prev) and first[:1].islower():  # "right-" + "click"
            words[-1] = (prev + first, words[-1][1])
            words += [(w, page) for w in rest]
        else:
            words += [(w, page) for w in text.split(" ")]
    return [(w.replace(SOFT, ""), p) for w, p in words if w.replace(SOFT, "")]


def make_chunks(sections, max_words=110, overlap=25):
    chunks = []
    for s in sections:
        words = section_words(s) or [("", s["page"])]
        step = max_words - overlap
        i = 0
        while True:
            piece = words[i:i + max_words]
            chunks.append({
                "num": s["num"], "title": s["title"], "chapter": s["chapter"],
                "level": s["level"], "section_page": s["page"], "anchor": s["anchor"],
                "page": piece[0][1], "page_end": piece[-1][1],
                "text": " ".join(w for w, _ in piece).strip(),
            })
            if i + max_words >= len(words):
                break
            i += step
    return chunks


def load_model():
    """Read the model files that ship inside the wordllama package (no network)."""
    import wordllama
    from safetensors.numpy import load_file
    from tokenizers import Tokenizer
    pkg = Path(wordllama.__file__).parent
    tokenizer = Tokenizer.from_file(str(pkg / "tokenizers" / "l2_supercat_tokenizer_config.json"))
    weights = load_file(str(pkg / "weights" / "l2_supercat_256.safetensors"))
    return tokenizer, weights["embedding.weight"].astype(np.float32)


def embed(tokenizer, table, texts):
    out = np.zeros((len(texts), table.shape[1]), dtype=np.float32)
    for i, t in enumerate(texts):
        ids = [min(max(x, 0), table.shape[0] - 1)
               for x in tokenizer.encode(t, add_special_tokens=False).ids]
        if ids:
            v = table[ids].mean(axis=0)
            n = np.linalg.norm(v)
            out[i] = v / n if n else v
    return out


def passage_text(c):
    # Heading context is repeated so short sections still carry their topic
    return f"{c['chapter']}. {c['title']}. {c['title']}. {c['text']}"


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pdf or not pdf.exists():
        sys.exit("Usage: python build_tools/build_index.py path\\to\\manual.pdf")
    DATA.mkdir(parents=True, exist_ok=True)

    doc, sections = parse_sections(pdf)
    chunks = [c for c in make_chunks(sections) if c["text"]]  # chapter titles have no body
    chapters = [{"num": s["num"], "title": s["title"], "page": s["page"]}
                for s in sections if s["level"] == 1]
    tokenizer, table = load_model()
    vecs = embed(tokenizer, table, [passage_text(c) for c in chunks])

    np.save(DATA / "vectors.npy", vecs.astype(np.float16))
    np.save(DATA / "embed.npy", table.astype(np.float16))
    tokenizer.save(str(DATA / "tokenizer.json"))
    cover = clean(doc[0].get_text()).replace(SOFT, "")
    meta = {"manual_file": pdf.name, "cover": cover, "pages": len(doc),
            "chapters": chapters, "chunks": chunks}
    (DATA / "chunks.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    pages_dir = DATA / "pages"
    shutil.rmtree(pages_dir, ignore_errors=True)
    pages_dir.mkdir()
    for i, page in enumerate(doc, start=1):
        page.get_pixmap(dpi=110).save(pages_dir / f"{i:02d}.jpg", jpg_quality=80)
    shutil.copy(pdf, DATA / "manual.pdf")
    print(f"{len(sections)} sections, {len(chunks)} passages, {len(doc)} pages -> {DATA}")


if __name__ == "__main__":
    main()
