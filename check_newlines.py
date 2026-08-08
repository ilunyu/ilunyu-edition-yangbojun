#!/usr/bin/env python3
"""检查并修复 yangbojun JSON 文件中丢失的换行符。

HTML 源文件中，某些章节的原文 "text" 或译文 "translate" 跨越多个 <p> 标签。
convert_html_to_json.py 的 merge_continuation_chapters 函数在合并这些段落时
直接拼接（result[-1] += p），丢失了段落间的换行符 \\n。

本脚本通过重新解析 HTML 源文件，将每个章节的原文/译文按 <p> 标签分段，
然后与 JSON 中对应字段的 \\n 数量对比，找出缺少换行符的章节。
使用 --fix 可自动修复。

Usage:
    python check_newlines.py [--fix] [html_file json_file ...]

不带参数时检查 ref/ 目录下所有 HTML 与同级 JSON 的对应关系。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from html.parser import HTMLParser

BASE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(BASE, "ref")

# ── 圈码映射（与 convert_html_to_json.py 保持一致）──────────────────────
CIRCLED_MAP: dict[str, str] = {}
for _i in range(1, 21):
    CIRCLED_MAP[chr(0x2474 + _i - 1)] = f"[{_i}]"  # ⑴⑵⑶…
    CIRCLED_MAP[chr(0x2460 + _i - 1)] = f"[{_i}]"  # ①②③…


def replace_circled(text: str) -> str:
    """将圈码字符替换为 [n] 标记。"""
    for char, replacement in CIRCLED_MAP.items():
        text = text.replace(char, replacement)
    return text


# ── HTML 解析 ──────────────────────────────────────────────────────────
class TextExtractor(HTMLParser):
    """提取所有 <p> 标签的文本，返回段落列表。"""

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


# 注释标记正则：容错 HTML 源文件中的拼写差异，如
#   【注释】（标准）、【注释）【注释)（括号方向错误或全半角混用）
ANNOTATION_RE = re.compile(r"^【注释[】\)\）]")


# ── 段落分组 ───────────────────────────────────────────────────────────
def group_paragraphs(paragraphs: list[str]) -> list[dict]:
    """将 HTML 段落按章节分组，保留每个字段的分段信息。

    返回结构::
        [{"id": 906, "text_segments": [...], "translate_segments": [...]}, ...]
    """
    chapters: list[dict] = []
    current: dict | None = None
    field: str | None = None  # "text" | "translate" | "annotation"

    for p in paragraphs:
        m = re.match(r"^(\d+)\.(\d+)", p)
        if m:
            if current:
                chapters.append(current)
            pian, ch = int(m.group(1)), int(m.group(2))
            current = {
                "id": pian * 100 + ch,
                "text_segments": [p[m.end():].strip()],
                "translate_segments": [],
            }
            field = "text"
        elif p.startswith("【译文】"):
            if current:
                current["translate_segments"].append(p[len("【译文】"):].strip())
            field = "translate"
        elif ANNOTATION_RE.match(p):
            field = "annotation"
        else:
            # 段落续行——归属当前字段
            if field == "text" and current:
                current["text_segments"].append(p.strip())
            elif field == "translate" and current:
                current["translate_segments"].append(p.strip())
            # annotation 续行暂不处理（注释通常在单个 <p> 内）

    if current:
        chapters.append(current)
    return chapters


# ── 核心检查逻辑 ───────────────────────────────────────────────────────
def check_pair(
    html_path: str, json_path: str, fix: bool = False
) -> tuple[list[str], bool]:
    """检查一对 HTML/JSON 文件，返回 (问题描述列表, 是否已修复)。"""
    # 解析 HTML
    html = open(html_path, encoding="utf-8").read()
    parser = TextExtractor()
    parser.feed(html)
    html_chapters = group_paragraphs(parser.paragraphs)

    # 加载 JSON
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    json_by_id = {ch["id"]: ch for ch in data["content"]}

    issues: list[str] = []
    modified = False

    for hc in html_chapters:
        ch_id = hc["id"]
        if ch_id not in json_by_id:
            continue
        jc = json_by_id[ch_id]

        for field_name, segments in [
            ("text", hc["text_segments"]),
            ("translate", hc["translate_segments"]),
        ]:
            if len(segments) <= 1:
                continue  # 单段不可能缺换行

            # 对每段做与转换器相同的圈码替换
            processed = [replace_circled(s) for s in segments]
            joined_no_nl = "".join(processed)
            joined_with_nl = "\n".join(processed)
            json_val = jc.get(field_name, "")

            expected_nl = len(segments) - 1
            actual_nl = json_val.count("\n")

            if actual_nl >= expected_nl:
                continue  # 换行数量已正确

            if joined_no_nl == json_val:
                # 内容完全匹配，只是缺少换行——可以安全修复
                issues.append(
                    f"  章节 {ch_id} {field_name}: HTML {len(segments)} 段，"
                    f"应有 {expected_nl} 个 \\n，实际 {actual_nl} 个"
                )
                if fix:
                    jc[field_name] = joined_with_nl
                    modified = True
            elif joined_with_nl == json_val:
                pass  # 已经正确
            else:
                # 内容有其他差异，不能安全自动修复
                issues.append(
                    f"  章节 {ch_id} {field_name}: HTML {len(segments)} 段，"
                    f"但内容与 JSON 不完全匹配（需人工检查）"
                )

    if modified:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    return issues, modified


# ── 文件配对 ───────────────────────────────────────────────────────────
def find_pairs() -> list[tuple[str, str]]:
    """自动发现 ref/ 下的 HTML 文件与对应的 JSON 文件。"""
    pairs = []
    for html_path in sorted(glob.glob(os.path.join(REF_DIR, "text*.html"))):
        m = re.search(r"text(\d+)\.html", html_path)
        if not m:
            continue
        pian = int(m.group(1)) - 5  # text00006 = 篇1
        if pian < 1:
            continue
        json_files = glob.glob(os.path.join(BASE, f"{pian:02d}-*.json"))
        if json_files:
            pairs.append((html_path, json_files[0]))
    return pairs


# ── 主入口 ─────────────────────────────────────────────────────────────
def main() -> int:
    fix = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--fix"]

    if len(args) >= 2:
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args) - 1, 2)]
    elif not args:
        pairs = find_pairs()
    else:
        print("用法: python check_newlines.py [--fix] [html json ...]")
        return 1

    if not pairs:
        print("未找到 HTML/JSON 文件对。")
        return 1

    total_issues = 0
    total_fixed = 0

    for html_path, json_path in pairs:
        name = os.path.basename(json_path)
        issues, modified = check_pair(html_path, json_path, fix=fix)
        if issues:
            print(f"\n=== {name} ===")
            for line in issues:
                print(line)
            total_issues += len(issues)
        if modified:
            print(f"  ✅ 已修复 {name}")
            total_fixed += 1

    verb = "修复" if fix else "检测"
    print(f"\n{verb}完成: 共发现 {total_issues} 处换行缺失", end="")
    if fix:
        print(f"，修复了 {total_fixed} 个文件")
    else:
        print("（加 --fix 可自动修复）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())