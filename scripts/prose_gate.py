#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""散文闸门：跑 chinese-prose-style 第 7 节的两条断言。

    A   段首不许是整句判词（粗体段以「。」收尾、去标点后 >= 18 字）
    A′  同类但只有 8–17 字的，列出来供人工看，加 --strict 才算不通过
    B   一句不超过四十字（去掉全角括号内内容后仍超过 --max-len）

只扫散文行：表格、标题、表题与图题、图片、代码块、frontmatter、引用块、带
`<!-- prose-gate: skip -->` 的行都不进扫描。范围的依据是主规程第 4 节与第 7.1 节。

用法：
    python scripts/prose_gate.py 稿件.md [更多稿件.md ...]
        [--max-len 40] [--strict] [--include-captions] [--list 10] [--quiet]

退出码：0 全过；1 有不通过项（含文件不存在、无法读取）。
只读稿，不写盘。只用标准库。
"""

import argparse
import os
import re
import sys

SKIP_MARKER = "<!-- prose-gate: skip -->"
CAPTION = re.compile(r"^附?[表图]\s*[0-9A-Z]")
BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*")
INLINE_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
INLINE_CODE = re.compile(r"`([^`]*)`")
PARENS = re.compile(r"[（(][^（）()]*[）)]")

# 计数时去掉的标点与符号；中文、西文字母与数字各算一个
PUNCT = set(
    "。，、；：？！「」『』（）()《》〈〉【】〔〕…—～·“”‘’"
    "\"',.;:!?[]{}<>/\\|+-=*_#%$&@^~"
)


def text_len(s):
    """字数＝去掉空白与标点后剩下的字符个数。"""
    return sum(1 for ch in s if not ch.isspace() and ch not in PUNCT)


def drop_parens(s):
    """反复剥掉最内层括号，直到没有括号为止（处理嵌套）。"""
    while True:
        new = PARENS.sub("", s)
        if new == s:
            return s
        s = new


def classify(path, include_captions=False):
    """逐行判定类型，返回 [(行号, 原文, 类型)]。"""
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read().splitlines()
    items = []
    in_code = False
    in_fm = bool(raw) and raw[0].strip() == "---"
    for i, line in enumerate(raw, 1):
        s = line.strip()
        if in_fm:
            items.append((i, s, "frontmatter"))
            if i > 1 and s == "---":
                in_fm = False
            continue
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            items.append((i, s, "code"))
            continue
        if in_code:
            items.append((i, s, "code"))
            continue
        if not s:
            items.append((i, s, "blank"))
        elif SKIP_MARKER in s:
            items.append((i, s, "skip"))
        elif s.startswith("#"):
            items.append((i, s, "heading"))
        elif s.startswith("|"):
            items.append((i, s, "table"))
        elif s.startswith("!["):
            items.append((i, s, "image"))
        elif s.startswith(">"):
            items.append((i, s, "quote"))
        elif CAPTION.match(s):
            items.append((i, s, "prose" if include_captions else "caption"))
        else:
            items.append((i, s, "prose"))
    return items


def check_leads(items):
    """断言 A。返回 (硬命中, 软命中)，每项是 (行号, 段首原文, 字数)。"""
    hard, soft = [], []
    for ln, s, kind in items:
        if kind != "prose":
            continue
        m = BOLD_LEAD.match(s)
        if not m:
            continue
        head = m.group(1)
        if not head.endswith("。"):
            continue
        n = text_len(head)
        if n >= 18:
            hard.append((ln, head, n))
        elif n >= 8:
            soft.append((ln, head, n))
    return hard, soft


def check_sentences(items, max_len):
    """断言 B。返回 (超长句, 总句数, 含括号最长的字数)。"""
    bad = []
    total = 0
    raw_max = 0
    for ln, s, kind in items:
        if kind != "prose":
            continue
        t = INLINE_IMG.sub("", s)
        t = INLINE_CODE.sub(r"\1", t)
        t = t.replace("**", "").replace("`", "")
        for sent in re.split(r"[。！？]", t):
            sent = sent.strip()
            if not sent:
                continue
            total += 1
            raw_max = max(raw_max, text_len(sent))
            n = text_len(drop_parens(sent))
            if n > max_len:
                bad.append((ln, sent, n))
    return bad, total, raw_max


def show(rows, fmt, limit):
    for row in rows[:limit]:
        print("      " + fmt(row))
    if len(rows) > limit:
        print(f"      ……另有 {len(rows) - limit} 处，用 --list 调大")


def report(path, args):
    try:
        items = classify(path, include_captions=args.include_captions)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"散文闸门　读不了 {path}：{exc}")
        return True

    prose = sum(1 for _, _, k in items if k == "prose")
    total_lines = sum(1 for _, s, _ in items if s)
    hard, soft = check_leads(items)
    bad, total, raw_max = check_sentences(items, args.max_len)
    failed = bool(hard) or bool(bad) or (args.strict and bool(soft))
    name = os.path.basename(path)

    if args.quiet:
        print(f"散文闸门　{name}｜散文行 {prose}／句子 {total}｜"
              f"A {len(hard)} 处、A′ {len(soft)} 处、B {len(bad)} 句｜"
              f"{'不通过' if failed else '通过'}")
        return failed

    print(f"散文闸门　{name}")
    print(f"  非空行 {total_lines}｜散文行 {prose}｜句子 {total}")
    print(f"  A  段首整句判词（>=18 字）{len(hard)} 处"
          + ("　← 不通过" if hard else "　过"))
    print(f"  A′ 8–17 字段首（只提示，--strict 才算不通过）{len(soft)} 处")
    print(f"  B  超过 {args.max_len} 字的句子 {len(bad)} 句"
          + ("　← 不通过" if bad else "　过")
          + f"（含括号最长为 {raw_max} 字）")
    if hard:
        print("  段首判词：")
        show(hard, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1]}", args.list)
    if soft:
        print("  短段首（人工看一眼）：")
        show(soft, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1]}", min(args.list, 5))
    if bad:
        worse = sorted(bad, key=lambda r: -r[2])
        print("  超长句（按长度降序）：")
        show(worse, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1][:70]}…", args.list)
    print(f"  结论：{'不通过' if failed else '通过'}")
    return failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="chinese-prose-style 第 7 节的散文闸门")
    ap.add_argument("paths", nargs="+", help="要核的 markdown 稿")
    ap.add_argument("--max-len", type=int, default=40, help="句长上限，默认 40 字")
    ap.add_argument("--strict", action="store_true", help="把 8–17 字的段首判词也算不通过")
    ap.add_argument("--list", type=int, default=10, help="每类列出多少处，默认 10")
    ap.add_argument("--include-captions", action="store_true",
                    help="把表题与图题也当散文扫（默认不扫）")
    ap.add_argument("--quiet", action="store_true", help="每份稿只打一行汇总")
    args = ap.parse_args(argv)

    failed_any = False
    for p in args.paths:
        if not os.path.isfile(p):
            print(f"散文闸门　跳过不存在的文件：{p}")
            failed_any = True
            continue
        if report(p, args):
            failed_any = True
        if not args.quiet:
            print()
    return 1 if failed_any else 0


if __name__ == "__main__":
    sys.exit(main())
