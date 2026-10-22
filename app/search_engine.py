"""
Offline search over the pre-built manual index.

Ranking blends two signals:
  * semantic similarity  - static word embeddings (WordLlama, 256-d), averaged
  * keyword relevance    - BM25 over the passage text, with section titles boosted
so that both "flip the polarity" (meaning) and "biquad" (exact term) find the right place.
Everything runs locally with NumPy; nothing is sent anywhere.
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

STOP = set("""a an and are as at be been but by can could do does doing did for from have has had how
i if in into is it its me my of on or our so that the their them then there these this those to
was we were what when where which while who why will with would you your about want wants need needs
should shall get gets getting way ways use using used make makes possible please tell show find
""".split())

WORD_RE = re.compile(r"[a-z0-9]+(?:[/-][a-z0-9]+)*")


def stem(w: str) -> str:
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + rep
    return w


def terms(text: str):
    out = []
    for w in WORD_RE.findall(text.lower()):
        for part in re.split(r"[/-]", w):
            if part and part not in STOP:
                out.append(stem(part))
    return out


class ManualIndex:
    def __init__(self, data_dir: Path, synonyms_path: Path = None):
        self.data_dir = Path(data_dir)
        meta = json.loads((self.data_dir / "chunks.json").read_text(encoding="utf-8"))
        self.meta = meta
        self.chunks = meta["chunks"]
        self.vectors = np.load(self.data_dir / "vectors.npy").astype(np.float32)
        self.table = np.load(self.data_dir / "embed.npy").astype(np.float32)
        self.tokenizer = Tokenizer.from_file(str(self.data_dir / "tokenizer.json"))
        self.synonyms = self._load_synonyms(synonyms_path or self.data_dir.parent / "synonyms.json")
        self._build_bm25()

    @staticmethod
    def _load_synonyms(path: Path):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {stem(k.lower()): [stem(v.lower()) for v in vals]
                for k, vals in raw.items() if not k.startswith("_") and isinstance(vals, list)}

    def _expand(self, q_terms):
        """Query terms with weights: 1.0 for typed words, 0.6 for synonyms."""
        weights = {t: 1.0 for t in q_terms}
        for t in q_terms:
            for syn in self.synonyms.get(t, []):
                for part in re.split(r"[/-]", syn):
                    weights.setdefault(part, 0.6)
        return weights

    # ---------- keyword side ----------
    def _build_bm25(self):
        self.doc_tf, self.doc_len = [], []
        df = Counter()
        for c in self.chunks:
            # titles count three times: a match in a heading matters more
            toks = terms(f"{c['title']} {c['title']} {c['title']} {c['chapter']} {c['text']}")
            tf = Counter(toks)
            self.doc_tf.append(tf)
            self.doc_len.append(len(toks))
            df.update(tf.keys())
        n = len(self.chunks)
        self.avgdl = sum(self.doc_len) / max(n, 1)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _bm25(self, weights, k1=1.4, b=0.75):
        scores = np.zeros(len(self.chunks), dtype=np.float32)
        for t, w in weights.items():
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.doc_tf):
                f = tf.get(t)
                if f:
                    scores[i] += w * idf * f * (k1 + 1) / (f + k1 * (1 - b + b * self.doc_len[i] / self.avgdl))
        return scores

    # ---------- semantic side ----------
    def embed(self, text: str) -> np.ndarray:
        ids = [min(max(x, 0), self.table.shape[0] - 1)
               for x in self.tokenizer.encode(text, add_special_tokens=False).ids]
        if not ids:
            return np.zeros(self.table.shape[1], dtype=np.float32)
        v = self.table[ids].mean(axis=0)
        n = np.linalg.norm(v)
        return v / n if n else v

    # ---------- search ----------
    def search(self, query: str, limit: int = 6):
        query = (query or "").strip()
        if not query:
            return {"query": query, "results": [], "strong": False}
        q_terms = terms(query)
        weights = self._expand(q_terms)
        # Embed the content words; fall back to the raw query if nothing is left
        sem_text = " ".join(w for w in re.findall(r"[\w/-]+", query) if w.lower() not in STOP) or query
        sem = self.vectors @ self.embed(sem_text)
        kw = self._bm25(weights)

        sem_n = np.clip((sem - 0.15) / 0.55, 0, 1)          # cosine -> 0..1
        kw_n = kw / kw.max() if kw.max() > 0 else kw
        score = 0.55 * sem_n + 0.45 * kw_n

        # one result per section: keep its best passage
        best = {}
        for i in np.argsort(-score):
            c = self.chunks[i]
            if c["num"] not in best:
                best[c["num"]] = (float(score[i]), int(i))
            if len(best) >= limit * 3:
                break
        ranked = sorted(best.values(), key=lambda x: -x[0])[:limit]

        results = []
        for s, i in ranked:
            c = self.chunks[i]
            pages = sorted({c["section_page"], c["page"], c["page_end"]})
            results.append({
                "section": c["num"],
                "title": c["title"],
                "chapter": c["chapter"],
                "page": c["page"],
                "pages": pages,
                "section_page": c["section_page"],
                "anchor": c.get("anchor"),
                "snippet": self._snippet(c["text"], weights) or f"Section {c['num']} {c['title']}",
                "score": round(s, 3),
            })
        top = ranked[0][0] if ranked else 0
        if top < 0.2:  # nothing meaningfully related (e.g. typos, off-topic questions)
            results = []
        typed = {w for w in re.findall(r"[A-Za-z0-9]+", query) if w.lower() not in STOP and len(w) > 2}
        synonyms = {t for t, w in weights.items() if w < 1 and len(t) > 2}
        return {"query": query, "results": results, "strong": top >= 0.45,
                "highlight": sorted(typed | synonyms)}

    def _snippet(self, text: str, weights, max_chars=260):
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if not sentences:
            return ""
        best_i = max(range(len(sentences)),
                     key=lambda k: (sum(weights.get(t, 0) for t in set(terms(sentences[k]))), -k))
        snip = sentences[best_i]
        j = best_i + 1
        while j < len(sentences) and len(snip) + len(sentences[j]) < max_chars:
            snip += " " + sentences[j]
            j += 1
        if len(snip) > max_chars:
            snip = snip[:max_chars].rsplit(" ", 1)[0] + " …"
        return ("… " if best_i > 0 else "") + snip

    def info(self):
        return {"cover": self.meta.get("cover", ""), "pages": self.meta["pages"],
                "sections": len({c["num"] for c in self.chunks}),
                "chapters": self.meta.get("chapters", [])}
