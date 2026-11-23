"""Rebuild the literal page index from the explicitly approved PDF, never a URL."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import re
import fitz


def build(pdf_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(pdf_path)
    target = output / "manual115.pdf"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    pages = []
    previous_topic = ""
    with fitz.open(target) as doc:
        for number, page in enumerate(doc, 1):
            if 10 <= number <= 25:
                category, section = "collection", "採檢一覽表"
            elif 26 <= number <= 59:
                category, section = "reference", "參考值、量測不確定度與臨床意義"
            elif 7 <= number <= 9:
                category, section = "containers", "採檢容器與順序"
            elif number == 71:
                category, section = "contacts", "諮詢電話一覽表"
            else:
                category, section = "instructions", "採檢注意事項與附件"
            topics = []
            if 27 <= number <= 59:
                for table in page.find_tables().tables:
                    rows = table.extract()
                    # Only index literal identifiers/names. Never infer reference
                    # intervals or pair the independent age and performance axes.
                    if rows and rows[0] and not str(rows[0][0] or "").strip() and previous_topic:
                        topics.append(previous_topic)
                    for row in rows:
                        if len(row) < 3:
                            continue
                        code = re.sub(r"\s+", "", str(row[0] or ""))
                        if re.fullmatch(r"\d{5,7}[A-Za-z]*", code):
                            topic = " ".join(str(value or "").replace("\n", " ") for value in row[:3])
                            if str(row[1] or "").strip() or str(row[2] or "").strip():
                                previous_topic = topic
                                topics.append(topic)
            pages.append(dict(page=number, category=category, section=section, text=page.get_text(), topics=list(dict.fromkeys(topics))))
    (output / "manual_pages.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    manifest = dict(file=target.name, source_name=source.name, document_number="TCHYM-QP-7.2-2-(1)", pages=len(pages), sha256=hashlib.sha256(target.read_bytes()).hexdigest(), index_sha256=hashlib.sha256((output / "manual_pages.json").read_bytes()).hexdigest(), version_label="115.05.19", source_header="陽明院區檢驗科", service_department="陽明院區檢驗科")
    (output / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default=str(Path(__file__).parent / "data"))
    args = parser.parse_args()
    print(json.dumps(build(args.pdf, args.output), ensure_ascii=False))
