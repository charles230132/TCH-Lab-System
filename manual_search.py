"""Literal, normalized search over source pages; no inferred clinical columns."""
import json
from pathlib import Path
import re
import unicodedata


def normalized(value):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"\s+", "", value).replace("–", "-").replace("−", "-")


ALIASES = [
    ["血氨", "氨", "Ammonia", "NH3", "09037"],
    ["乳酸", "Lactate", "Lactic acid", "09059"],
    ["血液氣體", "血液氣體分析", "血氣", "Blood gas", "ABG", "VBG", "09041"],
    ["血液培養", "血培", "Blood culture", "13016"],
    ["CBC", "全套血液檢查", "全血球計數", "08014", "08011"],
    ["凝血", "凝血功能", "PT", "APTT", "aPTT", "D-Dimer", "D dimer"],
    ["AFP", "甲型胎兒蛋白", "甲型胎兒球蛋白", "甲種胎兒蛋白"],
    ["CRP", "C反應蛋白", "C-反應蛋白"],
]


def expanded_terms(query):
    term = normalized(query)
    if not term:
        return []
    for group in ALIASES:
        if term in [normalized(x) for x in group]:
            # A one-character synonym such as 氨 should resolve to the item,
            # but must not match unrelated 氨基酸 or 抗環瓜氨酸 in full text.
            return list(dict.fromkeys(normalized(x) for x in group if len(normalized(x)) > 1))
    return [term]


def load_index(path):
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if [x["page"] for x in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Page index is not contiguous")
    return rows


def search_pages(index, query, category=None):
    terms = expanded_terms(query)
    if not terms:
        return []
    exact = normalized(query)
    hits = []
    for row in index:
        if category and row["category"] != category:
            continue
        original_text = row["text"]
        text = original_text + "\n" + "\n".join(row.get("topics", []))
        clean = normalized(text)
        matched = []
        for term in terms:
            if len(term) <= 3 and term.isascii() and term.isalpha():
                if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", unicodedata.normalize("NFKC", text).casefold()):
                    matched.append(term)
            elif term in clean:
                matched.append(term)
        if not matched:
            continue
        lines = [x.strip() for x in original_text.splitlines() if x.strip()]
        start = next((i for i, line in enumerate(lines) if any(t in normalized(line) for t in matched)), None)
        snippet = "　".join(lines[start:start + 7])[:240] if start is not None else "此頁含前頁延續的項目資料，請開啟原表查看完整適用條件。"
        score = (100 if exact in clean else 0) + (25 if row["category"] == "collection" else 0) + len(matched)
        hits.append({**row, "snippet": snippet, "score": score})
    return sorted(hits, key=lambda x: (-x["score"], x["page"]))


def find_quick_items(items, query):
    term = normalized(query)
    if not term:
        return []
    return [x for x in items if term in [normalized(a) for a in x["aliases"]] or (len(term) > 2 and term in normalized(x["title"]))]
