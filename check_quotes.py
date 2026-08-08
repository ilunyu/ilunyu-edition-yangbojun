#!/usr/bin/env python3
"""Check for unbalanced Chinese double quotation marks (U+201C “ and U+201D ”)
in a JSON file, printing the line numbers that need manual inspection.

Each line is checked independently, because the JSON is pretty-printed with
``indent=4`` so every string value (text / translate / annotation) lives on its
own physical line.  Inside one such line the number of opening “ and closing ”
quotes should match.

Usage:
    python check_quotes.py [file.json ...]

If no files are given, defaults to 05-gongyechang.json in this directory.
"""
from __future__ import annotations

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LEFT = "\u201c"   # “
RIGHT = "\u201d"  # ”


def check_file(path: str) -> None:
    print(f"\n=== {path} ===")
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    total_left = 0
    total_right = 0
    problems = []

    for i, line in enumerate(lines, start=1):
        n_left = line.count(LEFT)
        n_right = line.count(RIGHT)
        total_left += n_left
        total_right += n_right
        if n_left != n_right:
            problems.append((i, n_left, n_right, line.rstrip("\n")))

    print(f"总计: 左引号 “ {total_left} 个, 右引号 ” {total_right} 个, "
          f"差值 {total_left - total_right}")

    if not problems:
        print("未发现行内引号不匹配的行。")
        return

    print(f"发现 {len(problems)} 行引号未正确闭合，行号如下：")
    for lineno, n_left, n_right, text in problems:
        sign = "多左引号" if n_left > n_right else "多右引号"
        print(f"  行 {lineno} (“ {n_left} / ” {n_right}, {sign}): {text}")


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        files = argv[1:]
    else:
        default = os.path.join(BASE, "05-gongyechang.json")
        files = [default]

    for path in files:
        if not os.path.isfile(path):
            print(f"文件不存在: {path}", file=sys.stderr)
            continue
        check_file(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))