#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""散文闸门：跑 chinese-prose-style 第 7 节的四条断言。

    A   段首不许是整句判词（粗体段以「。」收尾、去标点后 >= 18 字）
    A′  同类但只有 8–17 字的，列出来供人工看，加 --strict 才算不通过
    A-ListRatio  加粗小标题加冒号开头的行占散文行的比例超过 --list-ratio（默认 35%），
                 报「疑似全篇列表化」，加 --strict 才算不通过
    B   一句不超过四十五字（去掉全角括号内内容后仍超过 --max-len）
    B′  单个分句不超过二十四字（去掉括号后按，；：、与破折号切开逐段核；
        引号、书名号、代码框与文件名各折算成一个方框），加 --strict 才算不通过
    C   段落不许切成电报碎句（三句以上段落里，短于 18 字的句子达三句且占比超过
        60%，或连续三句短于 16 字）
    D   单句内不许暗中报菜名（去掉括号后顿号达 3 处及以上）；纯数字编号之间的
        顿号（「第 1、3、5 场」）不计，加 --strict 才算不通过

只扫散文行：表格、标题、表题与图题、图片、代码块、frontmatter、引用块、带
`<!-- prose-gate: skip -->` 的行都不进扫描。首几行带 `<!-- prose-gate: skip-list-ratio -->`
的整份稿不判加粗分条占比，那是给清单体的提纲源稿用的。范围的依据是主规程第 4 节与第 7.1 节。

用法：
    python scripts/prose_gate.py 稿件.md [更多稿件.md ...]
        [--max-len 45] [--max-clause-len 24] [--list-ratio 0.35]
        [--strict] [--include-captions] [--list 10] [--quiet]

退出码：0 全过；1 有不通过项（含文件不存在、无法读取）。--strict 下软命中
（A′、A-ListRatio、B′、D）也算不通过。只读稿，不写盘。只用标准库。
"""

import argparse
import os
import re
import sys

SKIP_MARKER = "<!-- prose-gate: skip -->"
SKIP_LIST_RATIO = "<!-- prose-gate: skip-list-ratio -->"
CAPTION = re.compile(r"^附?[表图]\s*[0-9A-Z]")
BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*")
BOLD_LABEL = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)?\*\*[^*]+\*\*\s*[：:]")
INLINE_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
INLINE_CODE = re.compile(r"`([^`]*)`")
PARENS = re.compile(r"[（(][^（）()]*[）)]")
SENT_SPLIT = re.compile(r"[。！？]")
CLAUSE_SPLIT = re.compile(r"[，；：、]|——")
# 成串的引文折算成一个方框：引号、书名号、代码框里的字串，以及文件名。
# 读者把它们当一个名词看，不该按字数论长短，也不该让里面的顿号把分句切开。
FOLDED = "▢"
SPANS = re.compile(
    r"[「『][^」』]*[」』]|《[^》]*》|`[^`]*`|<!--.*?-->"
)
FILENAME = re.compile(
    r"[A-Za-z0-9_./\\-]+\.(?:md|markdown|py|json|ya?ml|docx?|xlsx?|csv|tsv|txt|pdf|png|jpe?g|html?)"
    r"(?:[A-Za-z0-9_.-]*)?"
)

# 计数时去掉的标点与符号；中文、西文字母与数字各算一个
PUNCT = set(
    "。，、；：？！「」『』（）()《》〈〉【】〔〕…—～·“”‘’"
    "\"',.;:!?[]{}<>/\\|+-=*_#%$&@^~"
)

# 电报腔与报菜名的判定阈值
SHORT_SENT = 18          # 短句线：去标点后少于这个字数算短句
SHORT_RUN = 16           # 连击线：连续三句都少于这个字数即报
SHORT_SHARE = 0.60       # 段落里短句占比超过这个数、且短句不少于三句，即报
MIN_SENTS_PER_PARA = 3   # 少于三句的段落不判电报腔
ENUM_LIMIT = 3           # 单句顿号达到这个数即报
NUM_RUN = re.compile(r"(?<![0-9A-Za-z])[0-9]+(?:\s*、\s*[0-9]+)+(?![0-9A-Za-z])")


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


def clean_line(s):
    """去图片、去行内代码标记、去加粗标记，留下可判的正文。"""
    t = INLINE_IMG.sub("", s)
    t = INLINE_CODE.sub(r"\1", t)
    return t.replace("**", "").replace("`", "")


def fold_spans(s):
    """把引号、书名号、代码框里的字串与文件名各折成一个方框。

    读者把它们当一个名词看，不该按字数论长短，也不该让引文里的顿号
    把分句切开——报菜名的顿号在正文里，不在引文里。
    """
    return FILENAME.sub(FOLDED, SPANS.sub(FOLDED, s))


def prep_clause_line(s):
    """分句判定用的行：先去图片，再把引文与文件名折成方框，最后去掉加粗标记。

    折一步要在去掉反引号之前做，否则代码框里的字串认不出来。
    """
    return fold_spans(INLINE_IMG.sub("", s)).replace("**", "")


def sentences(s):
    """按句号、问号、叹号切句，保留句末标点，去掉空段与只剩强调符号的碎段。"""
    out = []
    for m in re.finditer(r"[^。！？]+[。！？]?", s):
        x = m.group(0).strip().strip("*_~").strip()
        if x and text_len(x) > 0:
            out.append(x)
    return out


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
    """断言 A 与 A′。返回 (硬命中, 软命中)，每项是 (行号, 段首原文, 字数)。"""
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


def check_list_ratio(items, threshold):
    """断言 A 的扩展：加粗小标题加冒号的行占散文行的比例。"""
    prose = [(ln, s) for ln, s, k in items if k == "prose"]
    if len(prose) < 5:
        return [], len(prose), 0.0
    hits = [(ln, s) for ln, s in prose if BOLD_LABEL.match(s)]
    ratio = len(hits) / len(prose)
    return (hits if ratio > threshold else []), len(prose), ratio


def check_sentences(items, max_len):
    """断言 B。返回 (超长句, 总句数, 含括号最长的字数)。"""
    bad = []
    total = 0
    raw_max = 0
    for ln, s, kind in items:
        if kind != "prose":
            continue
        t = clean_line(s)
        for sent in sentences(t):
            total += 1
            raw_max = max(raw_max, text_len(sent))
            n = text_len(drop_parens(sent))
            if n > max_len:
                bad.append((ln, sent, n))
    return bad, total, raw_max


def check_clauses(items, max_clause):
    """断言 B′。返回 (超长分句, 分句总数)。

    切开的口径见主规程第 7.2 节：逗号、分号、冒号、顿号与破折号都算停顿，
    引文与文件名先折成一个方框再数。
    """
    bad = []
    total = 0
    for ln, s, kind in items:
        if kind != "prose":
            continue
        for sent in sentences(prep_clause_line(s)):
            for clause in CLAUSE_SPLIT.split(drop_parens(sent)):
                clause = clause.strip()
                if not clause:
                    continue
                total += 1
                n = text_len(clause)
                if n > max_clause:
                    bad.append((ln, clause, n))
    return bad, total


def check_telegraph(items):
    """断言 C。返回 [(行号, 句数, 短句占比, 最长短句连击, 该行首句)]。

    短句要成串才算电报腔：短句不足三句、或只是两三句里夹一句长的，
    不算——执行材料里的现场指令本来就这么短。整行都是问句的核对清单
    也不判，那是清单的形态，不是段落的形态。
    """
    hits = []
    for ln, s, kind in items:
        if kind != "prose":
            continue
        sents = [x for x in sentences(clean_line(s)) if text_len(drop_parens(x)) > 0]
        if len(sents) < MIN_SENTS_PER_PARA:
            continue
        if all(x.endswith("？") for x in sents):
            continue
        lens = [text_len(drop_parens(x)) for x in sents]
        short = [n for n in lens if n < SHORT_SENT]
        share = len(short) / len(lens)
        run = best = 0
        for n in lens:
            run = run + 1 if n < SHORT_RUN else 0
            best = max(best, run)
        if (len(short) >= 3 and share > SHORT_SHARE) or best >= 3:
            hits.append((ln, len(sents), share, best, sents[0][:40]))
    return hits


def check_enumeration(items):
    """断言 D。返回 (顿号超载句, 句中顿号数)。

    纯数字之间的顿号是编号写法（「第 1、3、5 场」），不计入。
    """
    bad = []
    for ln, s, kind in items:
        if kind != "prose":
            continue
        for sent in sentences(clean_line(s)):
            t = NUM_RUN.sub("", drop_parens(sent))
            n = t.count("、")
            if n >= ENUM_LIMIT:
                bad.append((ln, sent, n))
    return bad


def show(rows, fmt, limit):
    for row in rows[:limit]:
        print("      " + fmt(row))
    if len(rows) > limit:
        print(f"      ……另有 {len(rows) - limit} 处，用 --list 调大")


def has_body_marker(path, marker, within=3):
    """首几行里带某个整份稿生效的标记，就认。"""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            head = [ln.strip() for ln, _ in zip(fh, range(within * 4))]
    except OSError:
        return False
    seen = 0
    for line in head:
        if not line:
            continue
        seen += 1
        if marker in line:
            return True
        if seen >= within:
            break
    return False


def report(path, args):
    try:
        items = classify(path, include_captions=args.include_captions)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"散文闸门　读不了 {path}：{exc}")
        return True

    prose = sum(1 for _, _, k in items if k == "prose")
    total_lines = sum(1 for _, s, _ in items if s)
    hard, soft = check_leads(items)
    lr_hits, lr_total, lr_ratio = check_list_ratio(items, args.list_ratio)
    lr_off = has_body_marker(path, SKIP_LIST_RATIO)
    if lr_off:
        lr_hits = []
    bad, total, raw_max = check_sentences(items, args.max_len)
    clauses, clause_total = check_clauses(items, args.max_clause_len)
    tele = check_telegraph(items)
    enum = check_enumeration(items)

    failed = bool(hard) or bool(bad) or bool(tele)
    if args.strict:
        failed = failed or bool(soft) or bool(lr_hits) or bool(clauses) or bool(enum)
    name = os.path.basename(path)

    if args.quiet:
        print(f"散文闸门　{name}｜散文行 {prose}／句子 {total}｜"
              f"A {len(hard)}、A′ {len(soft)}、A-ListRatio {len(lr_hits)}、"
              f"B {len(bad)}、B′ {len(clauses)}、C {len(tele)}、D {len(enum)}｜"
              f"{'不通过' if failed else '通过'}")
        return failed

    print(f"散文闸门　{name}")
    print(f"  非空行 {total_lines}｜散文行 {prose}｜句子 {total}"
          f"｜分句 {clause_total}")
    print(f"  A  段首整句判词（>=18 字）{len(hard)} 处"
          + ("　← 不通过" if hard else "　过"))
    print(f"  A′ 8–17 字段首（软，--strict 才算不通过）{len(soft)} 处")
    if lr_off:
        print(f"  A-ListRatio  已按首行标记豁免（占散文行 {lr_ratio:.0%}）")
    else:
        print(f"  A-ListRatio  加粗小标题加冒号的行 {len(lr_hits)} 行"
              f"（占散文行 {lr_ratio:.0%}，阈值 {args.list_ratio:.0%}；软）")
    print(f"  B  超过 {args.max_len} 字的句子 {len(bad)} 句"
          + ("　← 不通过" if bad else "　过")
          + f"（含括号最长为 {raw_max} 字）")
    print(f"  B′  超过 {args.max_clause_len} 字的分句 {len(clauses)} 处（软）")
    print(f"  C  电报碎句的段落 {len(tele)} 段"
          + ("　← 不通过" if tele else "　过"))
    print(f"  D  顿号达 {ENUM_LIMIT} 处的句子 {len(enum)} 句"
          + ("（软，--strict 才算不通过）" if enum else "　过"))
    if hard:
        print("  段首判词：")
        show(hard, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1]}", args.list)
    if soft:
        print("  短段首（人工看一眼）：")
        show(soft, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1]}", min(args.list, 5))
    if lr_hits:
        print("  加粗分条（人工看一眼）：")
        show(lr_hits, lambda r: f"第 {r[0]} 行 {r[1][:60]}", min(args.list, 5))
    if bad:
        worse = sorted(bad, key=lambda r: -r[2])
        print("  超长句（按长度降序）：")
        show(worse, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1][:70]}…", args.list)
    if clauses:
        worse = sorted(clauses, key=lambda r: -r[2])
        print("  超长分句（按长度降序）：")
        show(worse, lambda r: f"第 {r[0]} 行 [{r[2]} 字] {r[1][:70]}…", min(args.list, 10))
    if tele:
        print("  电报碎句：")
        show(tele, lambda r: f"第 {r[0]} 行 [共 {r[1]} 句，短句占 {r[2]:.0%}，"
                             f"最长短句连击 {r[3]}] {r[4]}…", min(args.list, 5))
    if enum:
        print("  段内报菜名：")
        show(enum, lambda r: f"第 {r[0]} 行 [{r[2]} 个顿号] {r[1][:70]}…", min(args.list, 5))
        print("  两步判定（逐条过，见主规程 7.2 的断言 D）："
              "①把顿号换成「或」，条件与后果都不变的，是并列可任一触发，留作一句；"
              "②换成「或」会改变意思的，看每项是不是五字以内的单纯标签，"
              "带附加说明就归并成上位类别或做表。")
    print(f"  结论：{'不通过' if failed else '通过'}")
    return failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="chinese-prose-style 第 7 节的散文闸门")
    ap.add_argument("paths", nargs="+", help="要核的 markdown 稿")
    ap.add_argument("--max-len", type=int, default=45, help="整句上限，默认 45 字")
    ap.add_argument("--max-clause-len", type=int, default=24,
                    help="单分句上限，默认 24 字（软命中，--strict 才算不通过）")
    ap.add_argument("--list-ratio", type=float, default=0.35,
                    help="加粗分条占散文行的比例上限，默认 0.35（软命中）")
    ap.add_argument("--strict", action="store_true",
                    help="把软命中（A′、A-ListRatio、B′、D）也算不通过")
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
