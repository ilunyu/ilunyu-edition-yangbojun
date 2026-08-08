#!/usr/bin/env python3
"""Convert yangbojun HTML reference files to JSON format.

Usage:
    python convert_html_to_json.py

Reads text00008.html – text00025.html (篇 3–20) from ref/ directory,
produces 03-bayi.json – 20-yaozue.json in the parent directory.
"""
from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser

BASE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(BASE, "ref")
OUT_DIR = BASE  # parent of ref/

# Mapping circled numbers ⑴-⑳ to [1]-[20]
CIRCLED_MAP = {}
for i in range(1, 21):
    circled_char = chr(0x2474 + i - 1)  # ⑴=U+2474, ⑵=U+2475, ...
    CIRCLED_MAP[circled_char] = f"[{i}]"
    # Also handle ⑽ (U+2469) through ⑳ differently if needed
# Manual check: ⑴=U+2460 in some encodings, let's verify
# Actually the HTML uses ⑴⑵⑶... which are U+2474..U+2487 (parenthesized)
# But there's also ①②③... = U+2460..U+2473
# Let's build a more robust mapping
CIRCLED_MAP = {}
for i in range(1, 21):
    # Try parenthesized circled numbers: ⑴=U+2474
    c1 = chr(0x2474 + i - 1)
    CIRCLED_MAP[c1] = f"[{i}]"
    # Try circled numbers: ①=U+2460  
    c2 = chr(0x2460 + i - 1)
    CIRCLED_MAP[c2] = f"[{i}]"

# Pian filenames mapping
PIAN_FILES = {
    3: "03-bayi.json",
    4: "04-liren.json",
    5: "05-gongyechang.json",
    6: "06-yongye.json",
    7: "07-shuer.json",
    8: "08-taibo.json",
    9: "09-zihan.json",
    10: "10-xiangdang.json",
    11: "101-xianjin.json",
    12: "102-yanyuan.json",
    13: "103-zilu.json",
    14: "104-xianwen.json",
    15: "105-weilinggong.json",
    16: "106-jishi.json",
    17: "107-yanghuo.json",
    18: "108-weizi.json",
    19: "109-zizhang.json",
    20: "20-yaozue.json",
}

# HTML file number = pian_number + 5 (text00006=篇1, text00007=篇2, ...)
def pian_to_html_num(pian: int) -> int:
    return pian + 5


def replace_circled(text: str) -> str:
    """Replace all circled number characters with [n] markers."""
    for char, replacement in CIRCLED_MAP.items():
        text = text.replace(char, replacement)
    return text


class TextExtractor(HTMLParser):
    """Extract text from <p> tags, returning a list of paragraph strings."""
    
    def __init__(self):
        super().__init__()
        self.paragraphs: list[str] = []
        self._current_text: list[str] = []
        self._in_p = False
    
    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._in_p = True
            self._current_text = []
    
    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            self._in_p = False
            text = "".join(self._current_text).strip()
            if text:
                self.paragraphs.append(text)
    
    def handle_data(self, data):
        if self._in_p:
            self._current_text.append(data)


def parse_annotations(ann_text: str) -> list[dict]:
    """Parse annotation text containing [1]label——text[2]label——text...
    
    Returns list of {label, text} dicts.
    """
    # First replace circled numbers
    ann_text = replace_circled(ann_text)
    
    # Split by [n] markers at the start of each annotation
    # Pattern: [1]label——text content until next [n] or end
    parts = re.split(r'\[(\d+)\]', ann_text)
    # parts[0] is before the first [n] (usually empty or whitespace)
    # parts[1] = number, parts[2] = content until next [n], etc.
    
    annotations = []
    i = 1
    while i < len(parts):
        num = int(parts[i])
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        i += 2
        
        if not content:
            continue
        
        # Split label and text by —— or —
        label = content
        text = content
        if "——" in content:
            label, text = content.split("——", 1)
            label = label.strip()
            text = text.strip()
        elif "—" in content:
            label, text = content.split("—", 1)
            label = label.strip()
            text = text.strip()
        else:
            # No separator, use full content as both label and text
            label = content
            text = content
        
        annotations.append({"label": label, "text": text})
    
    return annotations


def strip_chapter_prefix(text: str) -> tuple[int, str]:
    """Strip the X.Y prefix from chapter text. Returns (chapter_id, clean_text).

    Example: "9.1子罕言利..." -> (901, "子罕言利...")

    chapter_id is an integer (pian*100 + ch) to match the existing JSON format.
    """
    m = re.match(r'^(\d+)\.(\d+)', text)
    if m:
        pian_num = int(m.group(1))
        ch_num = int(m.group(2))
        chapter_id = pian_num * 100 + ch_num
        clean_text = text[m.end():]
        return chapter_id, clean_text
    return 0, text


def process_paragraphs(paragraphs: list[str], pian_num: int) -> list[dict]:
    """Process paragraphs into chapter dicts.
    
    Pattern: [title] [comment] [chapter_text] [translation] [annotations] ...
    Some chapters may not have annotations.
    """
    chapters = []
    
    # Find the first paragraph starting with a chapter number (X.Y format)
    i = 0
    while i < len(paragraphs):
        if re.match(r'^\d+\.\d+', paragraphs[i]):
            break
        i += 1
    
    # Now process chapters
    while i < len(paragraphs):
        p = paragraphs[i]
        
        # Check if this paragraph starts with a chapter number (X.Y format)
        if not re.match(r'^\d+\.\d+', p):
            i += 1
            continue
        
        chapter_id, raw_text = strip_chapter_prefix(p)
        raw_text = raw_text.strip()
        
        # Replace circled numbers in text with [n] markers
        text = replace_circled(raw_text)
        
        i += 1
        
        # Next paragraph should be translation (starts with 【译文】)
        translate = ""
        annotations = []
        
        if i < len(paragraphs) and "【译文】" in paragraphs[i]:
            translate = paragraphs[i].replace("【译文】", "").strip()
            i += 1
        
        # Next might be annotations (starts with 【注释】 or typo 【注释）)
        if i < len(paragraphs) and re.match(r'^【注释[】\)\）]', paragraphs[i]):
            ann_text = re.sub(r'^【注释[】\)\）]', '', paragraphs[i]).strip()
            annotations = parse_annotations(ann_text)
            i += 1
        
        # Also check for continuation paragraphs of the same chapter
        # (some chapters have text split across multiple <p> tags)
        # The text might continue until we hit 【译文】
        # We need to merge continuation paragraphs into the text
        # But since we already processed above, let's handle it differently
        
        chapters.append({
            "id": chapter_id,
            "text": text,
            "translate": translate,
            "annotation": annotations,
        })
    
    return chapters


def merge_continuation_chapters(paragraphs: list[str]) -> list[str]:
    """Merge continuation paragraphs that belong to the same chapter.

    In the HTML, some chapters have their text split across multiple <p> tags.
    We merge paragraphs that don't start with X.Y or 【译文】or 【注释】into
    the previous chapter text, joining them with a newline so that the
    paragraph break is preserved in the JSON output.
    """
    result = []
    for p in paragraphs:
        # If this paragraph starts with a chapter number, translation, or annotation marker,
        # it's a new logical paragraph
        if (
            re.match(r'^\d+\.\d+', p)
            or "【译文】" in p
            or re.match(r'^【注释[】\)\）]', p)
        ):
            result.append(p)
        elif result:
            # This is a continuation of the previous paragraph; keep the paragraph break
            result[-1] += "\n" + p
        else:
            result.append(p)
    return result


def convert_file(html_path: str, pian_num: int) -> dict:
    """Convert a single HTML file to JSON dict."""
    html = open(html_path, encoding="utf-8").read()
    
    parser = TextExtractor()
    parser.feed(html)
    
    # Merge continuation paragraphs
    paragraphs = merge_continuation_chapters(parser.paragraphs)
    
    # Extract title
    title = ""
    for p in parser.paragraphs:
        if "篇" in p and len(p) < 20:
            title = p.strip()
            break
    
    # Process chapters
    chapters = process_paragraphs(paragraphs, pian_num)
    
    return {
        "title": title,
        "comment": "",
        "content": chapters,
    }


def main():
    for pian_num in range(3, 21):
        html_num = pian_to_html_num(pian_num)
        html_path = os.path.join(REF_DIR, f"text{html_num:05d}.html")
        
        if not os.path.isfile(html_path):
            print(f"SKIP: {html_path} not found")
            continue
        
        out_filename = PIAN_FILES[pian_num]
        out_path = os.path.join(OUT_DIR, out_filename)
        
        try:
            data = convert_file(html_path, pian_num)
            
            # Verify
            ch_count = len(data["content"])
            if ch_count == 0:
                print(f"WARNING: {out_filename} has 0 chapters!")
                continue
            
            # Write JSON
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print(f"OK: {out_filename} - {data['title']} - {ch_count} chapters")
            
            # Verify annotation markers match
            for ch in data["content"]:
                text_markers = set(re.findall(r'\[(\d+)\]', ch["text"]))
                ann_count = len(ch["annotation"])
                max_marker = max(int(m) for m in text_markers) if text_markers else 0
                if max_marker != ann_count:
                    print(f"  WARN: {ch['id']} has {ann_count} annotations but max marker [{max_marker}]")
        
        except Exception as e:
            print(f"ERROR: {html_path} -> {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()