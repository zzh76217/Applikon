# -*- coding: utf-8 -*-
"""tools/build_docx_manual.py —— 由 docs/使用说明.txt 生成 Word 版中文说明书 docs/使用说明.docx

设计原则（第七轮补充，用户拍板"要 Word 说明书"）：
  1) 纯文本 使用说明.txt 是**唯一事实来源**；Word 版是它的排版结果，不单独维护、不另写内容。
  2) 只用 Python 标准库（zipfile + 手写 WordprocessingML），不引入 python-docx 等新依赖，
     保证打包后的实验电脑不需要联网装东西。
  3) 只做排版转换（标题/段落/项目符号/表格/提示框/页脚页码），**不增删任何一句说明书文字**。
  4) 转换失败必须报错退出，不允许静默产出半成品 docx。

用法：
    python tools/build_docx_manual.py                 # 生成/覆盖 docs/使用说明.docx
    python tools/build_docx_manual.py --check         # 只校验现有 docx 与 txt 是否一致
"""
from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT_PATH = os.path.join(ROOT, "docs", "使用说明.txt")
DOCX_PATH = os.path.join(ROOT, "docs", "使用说明.docx")

FW = "\u3000"  # 全角空格：纯文本里用来对齐表格列

# ---------------------------------------------------------------- 行型识别
RE_EQ = re.compile(r"^={10,}\s*$")
RE_DASH = re.compile(r"^-{10,}\s*$")
RE_SECTION = re.compile(r"^第\s*(\d+)\s*节　(.+?)\s*$")
RE_STEP = re.compile(r"^第\s*(\d+)\s*步　(.*)$")
RE_CALL = re.compile(r"^【(.+)】\s*$")
RE_Q = re.compile(r"^(Q\d+)\s+(.+?)\s*$")
RE_RHEAD = re.compile(r"^编号" + FW)
RE_RROW = re.compile(r"^(R\d{2})\s*" + FW + r"+(.*)$")
RE_BOARD = re.compile(r"^板块[①②③④⑤⑥]")
RE_TREE = re.compile(r"^\s*[├└]─「(.+?)」\s*(.*)$")
RE_TREE_CONT = re.compile(r"^\s*│\s*(.*)$")
RE_COL2 = re.compile(r"^([^\s" + FW + r"][^" + FW + r"]*)[" + FW + r"]{2,}(.+)$")
RE_CONT_FW = re.compile(r"^[" + FW + r"\s]+(.*)$")
RE_TERM = re.compile(r"^([^\s" + FW + r"]+)[" + FW + r"]{1,}(.+)$")
RE_BULLET = re.compile(r"^\s*[·\u00b7]\s+(.*)$")
RE_NUM = re.compile(r"^(\d{1,2})[\.、]\s+(.*)$")
RE_NOTE = re.compile(r"^[★☆]\s*(.*)$")
RE_H3 = re.compile(r"^(R06 [^\s\u3000].+|关于「.+」)$")

# 需要在 Word 里用等宽字体显示的"代码样"片段（路径/配置键/规则号/文件名）
RE_CODE = re.compile(
    r"(?:"
    r"[\w.\-]+(?:\\[\w.\-*]+)+"          # config\config.yaml
    r"|[\w.\-]+\.(?:yaml|yml|txt|csv|exe|db|json|bak|docx|pdf)"
    r"|app_info\.[\w.]+|config\.[\w.]+|data[/\\\w.*]+"
    r"|R\d{2}|SIMULATED|YYYYMMDD|HHMM"
    r")"
)


def _plain(text):
    """把一行文字切成 [(文本, 是否等宽)] 的 run 列表。"""
    parts = []
    pos = 0
    for m in RE_CODE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], False))
        parts.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], False))
    return parts or [(text, False)]


def read_lines(path=TXT_PATH):
    raw = io.open(path, "rb").read().decode("utf-8")
    return raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse(lines):
    """纯文本 → 块列表。块 kind：title/meta/h1/h2/h3/p/bullet/num/note/callout/indent/table"""
    blocks = []
    section = 0          # 当前"第 N 节"
    table = None         # 正在累积的表格 {"cols":..., "rows":[[...]]}
    callout = False      # 是否在【写在最前面】提示框里
    prev = None          # 上一个块（用于承接续行）
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        i += 1
        if not line.strip():
            table = None
            callout = False
            prev = None
            continue
        if RE_EQ.match(line):
            continue
        if RE_DASH.match(line):
            # 分隔线：若下一行是"第 N 节"标题，则整组（线-标题-线）转成一级标题
            if i < n and RE_SECTION.match(lines[i].strip()):
                m = RE_SECTION.match(lines[i].strip())
                section = int(m.group(1))
                blocks.append({"kind": "h1", "no": m.group(1), "text": m.group(2)})
                blocks[-1]["sec_no"] = section
                i += 1
                if i < n and RE_DASH.match(lines[i].rstrip()):
                    i += 1
                table = None
                prev = blocks[-1]
            continue
        m = RE_SECTION.match(line)
        if m:
            section = int(m.group(1))
            blocks.append({"kind": "h1", "no": m.group(2), "text": m.group(2), "sec_no": section})
            table = None
            prev = blocks[-1]
            continue
        if RE_CALL.match(line):
            callout = True
            blocks.append({"kind": "callout_title", "text": line[1:-1].strip()})
            prev = blocks[-1]
            continue
        m = RE_STEP.match(line)
        if m:
            blocks.append({"kind": "h2", "text": line})
            table = None
            prev = blocks[-1]
            continue
        m = RE_Q.match(line)
        if m:
            blocks.append({"kind": "h3", "lead": m.group(1), "text": m.group(2)})
            table = None
            prev = blocks[-1]
            continue
        if RE_H3.match(line):
            blocks.append({"kind": "h3", "lead": "", "text": line})
            table = None
            prev = blocks[-1]
            continue
        if RE_BOARD.match(line):
            blocks.append({"kind": "h3", "lead": "", "text": line})
            table = None
            prev = blocks[-1]
            continue
        m = RE_TREE.match(line)
        if m:
            blocks.append({"kind": "tree", "name": m.group(1), "text": m.group(2)})
            prev = blocks[-1]
            continue
        m = RE_TREE_CONT.match(line)
        if m and prev is not None and prev.get("kind") == "tree":
            if m.group(1):
                prev["text"] = (prev["text"] + " " + m.group(1)).strip()
            continue
        if RE_RHEAD.match(line):
            cells = [c.strip() for c in re.split(FW + r"+", line) if c.strip()]
            table = {"kind": "table", "id": "rules", "cols": cells, "rows": [], "sec_no": section}
            blocks.append(table)
            prev = None
            continue
        m = RE_RROW.match(line)
        if m:
            cells = [c.strip() for c in re.split(FW + r"+", m.group(2)) if c.strip()]
            if len(cells) == 1 and re.search(r"[🔴🟡🟢]", cells[0]):
                cells = re.split(r"(?=[🔴🟡🟢])", cells[0], 1)
            cells = [m.group(1)] + cells
            while len(cells) < 3:
                cells.append("")
            table = blocks[-1] if blocks and blocks[-1].get("kind") == "table" else None
            if table is None:
                table = {"kind": "table", "id": "rules", "cols": ["编号", "查什么", "超范围时"], "rows": [], "sec_no": section}
                blocks.append(table)
            table["rows"].append(cells[:3])
            prev = table["rows"][-1]
            continue
        if section == 9 and RE_TERM.match(line):
            m = RE_TERM.match(line)
            if not (blocks and blocks[-1].get("kind") == "table" and blocks[-1].get("id") == "terms"):
                blocks.append({"kind": "table", "id": "terms", "cols": ["术语", "含义"], "rows": [], "sec_no": 9})
            blocks[-1]["rows"].append([m.group(1).strip(), m.group(2).strip()])
            prev = blocks[-1]["rows"][-1]
            continue
        if section == 7 and RE_COL2.match(line):
            m = RE_COL2.match(line)
            if not (blocks and blocks[-1].get("kind") == "table" and blocks[-1].get("id") == "files"):
                blocks.append({"kind": "table", "id": "files", "cols": ["文件", "说明"], "rows": [], "sec_no": 7})
            blocks[-1]["rows"].append([m.group(1).strip(), m.group(2).strip()])
            prev = blocks[-1]["rows"][-1]
            continue
        if line[0] in FW and prev is not None:
            m = RE_CONT_FW.match(line)
            txt = m.group(1).strip() if m else line.strip()
            if isinstance(prev, list):        # 表格续行 → 并到上一行最后一格
                prev[-1] = (prev[-1] + "\n" + txt).strip()
                continue
            if prev.get("kind") == "tree" and txt:
                prev["text"] = (prev["text"] + " " + txt).strip()
                continue
        m = RE_BULLET.match(line)
        if m:
            blocks.append({"kind": "bullet", "text": m.group(1), "callout": callout})
            prev = blocks[-1]
            continue
        m = RE_NUM.match(line)
        if m and section in (1, 6):
            blocks.append({"kind": "num", "lead": m.group(1), "text": m.group(2), "callout": callout})
            prev = blocks[-1]
            continue
        m = RE_NOTE.match(line.strip())
        if m:
            blocks.append({"kind": "note", "text": m.group(1)})
            prev = blocks[-1]
            continue
        if callout:
            blocks.append({"kind": "callout", "text": line.strip()})
            prev = blocks[-1]
            continue
        if RE_CONT_FW.match(line) and line[0] in FW:
            blocks.append({"kind": "indent", "text": RE_CONT_FW.match(line).group(1).strip()})
            prev = blocks[-1]
            continue
        blocks.append({"kind": "p", "text": line.strip(), "sec_no": section})
        prev = blocks[-1]
        table = None
    return blocks


def split_header(blocks):
    """把最前面 3 行（标题/版本/日期）识别出来当封面，其余留在正文。"""
    title = version = meta = ""
    rest = []
    for b in blocks:
        if b["kind"] == "p" and not title and ("细胞培养接种与批次配置规划软件" in b["text"]):
            title = b["text"]
        elif b["kind"] == "p" and title and not version and b["text"].startswith("版本"):
            version = b["text"]
        elif b["kind"] == "p" and version and not meta and b["text"].startswith("编写日期"):
            meta = b["text"]
        else:
            rest.append(b)
    return title, version, meta, rest
# ================================================================ WordprocessingML 生成
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CJK = "微软雅黑"
MONO = "Consolas"
TEAL = "2E7D8C"
TEAL_DARK = "1F5560"
TEAL_MID = "2C6E7C"
TEAL_LIGHT_BG = "EAF3F5"
GREY_TEXT = "444444"
BORDER = "B7D0D6"
HEAD_BG = "2E7D8C"
ZEBRA_BG = "F5F9FA"

CONTENT_W = 9640          # A4(11906) - 左右边距(1133*2)


def _rf(mono=False):
    if mono:
        return '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"/>' % (MONO, MONO, CJK, MONO)
    return '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"/>' % (CJK, CJK, CJK, CJK)


def run(text, mono=False, bold=False, color=None, sz=None, shd=None, italic=False):
    if text == "":
        return ""
    rpr = [_rf(mono)]
    if bold:
        rpr.append("<w:b/><w:bCs/>")
    if italic:
        rpr.append("<w:i/><w:iCs/>")
    if color:
        rpr.append('<w:color w:val="%s"/>' % color)
    if sz:
        rpr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz))
    if shd:
        rpr.append('<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % shd)
    return "<w:r><w:rPr>%s</w:rPr><w:t xml:space=\"preserve\">%s</w:t></w:r>" % (
        "".join(rpr), escape(text))


def runs(text, base_mono=False, base_bold=False, color=None, sz=None, shd=None):
    """把一行文字按"代码样片段"切成多个 run。"""
    out = []
    for t, mono in _plain(text):
        out.append(run(t, mono=mono or base_mono, bold=base_bold, color=color, sz=sz, shd=shd))
    return "".join(out)


def para(text, style="BodyText", mono=False, bold=False, color=None, sz=None, shd=None,
         ind=None, before=None, after=None, page_break=False, keep=True, rich=True):
    ppr = ['<w:pStyle w:val="%s"/>' % style]
    if page_break:
        ppr.append("<w:pageBreakBefore/>")
    if keep:
        ppr.append("<w:keepNext/>")
    if ind:
        ppr.append("<w:ind %s/>" % ind)
    if before is not None or after is not None:
        a = before if before is not None else 0
        b = after if after is not None else 120
        ppr.append('<w:spacing w:before="%d" w:after="%d"/>' % (a, b))
    body = runs(text, base_mono=mono, base_bold=bold, color=color, sz=sz, shd=shd) if rich \
        else run(text, mono=mono, bold=bold, color=color, sz=sz, shd=shd)
    return "<w:p><w:pPr>%s</w:pPr>%s</w:p>" % ("".join(ppr), body)


def cell_p(text, style="TableText", bold=False, color=None):
    out = []
    for i, seg in enumerate(text.split("\n")):
        ppr = ['<w:pStyle w:val="%s"/>' % style]
        ppr.append('<w:spacing w:before="20" w:after="20"/>')
        out.append("<w:p><w:pPr>%s</w:pPr>%s</w:p>" % ("".join(ppr), runs(seg, base_bold=bold, color=color)))
    return "".join(out)


def cell(text, w, head=False, zebra=False):
    shd = ""
    if head:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % HEAD_BG
    elif zebra:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % ZEBRA_BG
    else:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="FFFFFF"/>'
    tcpr = '<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s<w:vAlign w:val="center"/></w:tcPr>' % (w, shd)
    return "<w:tc>%s%s</w:tc>" % (tcpr, cell_p(text, bold=head, color="FFFFFF" if head else None))


def table(block):
    cols = block["cols"]
    rows = block["rows"]
    ncols = len(cols)
    if block["id"] == "rules":
        widths = [900, int(CONTENT_W * 0.52), 0]
        widths[2] = CONTENT_W - widths[0] - widths[1]
    elif block["id"] == "files":
        widths = [int(CONTENT_W * 0.42), 0]
        widths[1] = CONTENT_W - widths[0]
    else:
        widths = [int(CONTENT_W * 0.22), 0]
        widths[1] = CONTENT_W - widths[0]
    while len(widths) < ncols:
        widths.append(0)
    tblpr = (
        '<w:tblPr><w:tblW w:w="%d" w:type="dxa"/><w:tblLayout w:type="fixed"/>' % CONTENT_W
        + '<w:tblBorders>'
        + '<w:top w:val="single" w:sz="6" w:space="0" w:color="%s"/>' % BORDER
        + '<w:left w:val="single" w:sz="6" w:space="0" w:color="%s"/>' % BORDER
        + '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="%s"/>' % BORDER
        + '<w:right w:val="single" w:sz="6" w:space="0" w:color="%s"/>' % BORDER
        + '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="%s"/>' % BORDER
        + '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="%s"/>' % BORDER
        + '</w:tblBorders>'
        + '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="110" w:type="dxa"/>'
        + '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tblCellMar>'
        + '</w:tblPr>'
    )
    grid = "<w:tblGrid>" + "".join('<w:gridCol w:w="%d"/>' % w for w in widths) + "</w:tblGrid>"
    xml = ["<w:tbl>", tblpr, grid]
    xml.append("<w:tr><w:trPr><w:tblHeader/></w:trPr>"
               + "".join(cell(c, widths[i], head=True) for i, c in enumerate(cols)) + "</w:tr>")
    for r, row in enumerate(rows):
        cells = list(row) + [""] * (ncols - len(row))
        xml.append("<w:tr>" + "".join(
            cell(cells[i], widths[i], zebra=(r % 2 == 1)) for i in range(ncols)) + "</w:tr>")
    xml.append("</w:tbl>")
    xml.append('<w:p><w:pPr><w:pStyle w:val="BodyText"/><w:spacing w:before="0" w:after="120"/>'
               '<w:rPr><w:sz w:val="8"/></w:rPr></w:pPr></w:p>')
    return "".join(xml)
# ================================================================ 样式表
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="%W%" xmlns:r="%R%">
<w:docDefaults><w:rPrDefault><w:rPr>%FONT%<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:pPr><w:spacing w:before="0" w:after="160"/><w:pBdr><w:bottom w:val="single" w:sz="18" w:space="6" w:color="2E7D8C"/></w:pBdr></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="1F5560"/><w:sz w:val="42"/><w:szCs w:val="42"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="CoverLine"><w:name w:val="Cover Line"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="60"/></w:pPr><w:rPr>%FONT%<w:color w:val="2C6E7C"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="CoverNote"><w:name w:val="Cover Note"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="120" w:after="120"/></w:pPr><w:rPr>%FONT%<w:color w:val="666666"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TocHead"><w:name w:val="TOC Head"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="100"/></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="1F5560"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TocItem"><w:name w:val="TOC Item"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="40"/><w:ind w:left="280"/></w:pPr><w:rPr>%FONT%<w:color w:val="333333"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="SectionTitle"><w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:link w:val="SectionTitleChar"/><w:pPr><w:keepNext/><w:keepLines/><w:pageBreakBefore/><w:spacing w:before="0" w:after="200"/><w:outlineLvl w:val="0"/><w:pBdr><w:bottom w:val="single" w:sz="12" w:space="3" w:color="2E7D8C"/></w:pBdr></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="2E7D8C"/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="StepTitle"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="90"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="23626E"/><w:sz w:val="25"/><w:szCs w:val="25"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="QTitle"><w:name w:val="Heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="2C6E7C"/><w:sz w:val="23"/><w:szCs w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Bullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="60"/><w:ind w:left="620" w:hanging="260"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Numbered"><w:name w:val="List Number"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="60"/><w:ind w:left="620" w:hanging="300"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="TreeItem"><w:name w:val="Tree Item"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="60"/><w:ind w:left="760" w:hanging="400"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Indent"><w:name w:val="Block Indent"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="60"/><w:ind w:left="620"/></w:pPr><w:rPr>%FONT%<w:color w:val="333333"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="100" w:after="100"/><w:ind w:left="280" w:right="200"/><w:shd w:val="clear" w:color="auto" w:fill="EAF3F5"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="2E7D8C"/></w:pBdr></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="1F5560"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Callout"><w:name w:val="Callout"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="40"/><w:ind w:left="340" w:right="200"/><w:shd w:val="clear" w:color="auto" w:fill="EAF3F5"/></w:pPr><w:rPr>%FONT%<w:color w:val="1B3E46"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="CalloutTitle"><w:name w:val="Callout Title"/><w:basedOn w:val="Normal"/><w:next w:val="Callout"/><w:pPr><w:keepNext/><w:spacing w:before="140" w:after="60"/><w:ind w:left="340" w:right="200"/><w:shd w:val="clear" w:color="auto" w:fill="D6E7EB"/></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="1F5560"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr>%FONT%<w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableHead"><w:name w:val="Table Head"/><w:basedOn w:val="TableText"/><w:pPr><w:spacing w:before="30" w:after="30"/></w:pPr><w:rPr>%FONT%<w:b/><w:bCs/><w:color w:val="FFFFFF"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="2E7D8C"/><w:u w:val="single"/></w:rPr></w:style>
</w:styles>"""


def styles_xml():
    font = '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"/>' % (CJK, CJK, CJK, CJK)
    return (STYLES.replace("%W%", W_NS).replace("%R%", R_NS).replace("%FONT%", font))


FOOTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="%W%" xmlns:r="%R%"><w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="center"/>
<w:rPr><w:color w:val="777777"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:pPr>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">细胞培养接种与批次配置规划软件 · 中文说明书　　第 </w:t></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve"> 页 / 共 </w:t></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> NUMPAGES </w:instrText></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>
<w:r><w:rPr><w:color w:val="777777"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve"> 页</w:t></w:r>
</w:p></w:ftr>"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

RELS_ROOT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

RELS_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>"""


def core_xml(title, version, now):
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>%s</dc:title><dc:subject>中文使用说明</dc:subject>
<dc:creator>细胞培养接种与批次配置规划软件</dc:creator><cp:keywords>生物反应器;CHO;接种规划;开机配置单;SOP</cp:keywords>
<dc:description>本文件由 docs/使用说明.txt 自动生成，内容以纯文本说明书为准。</dc:description>
<cp:lastModifiedBy>tools/build_docx_manual.py</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>
<cp:category>使用说明</cp:category></cp:coreProperties>""" % (escape(title), ts, ts))


APP_XML = ("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>build_docx_manual.py</Application><DocSecurity>0</DocSecurity>
<Company>实验室自用</Company><ScaleCrop>false</ScaleCrop><LinksUpToDate>false</LinksUpToDate>
<SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged></Properties>""")

SECT_PR = ('<w:sectPr><w:footerReference w:type="default" r:id="rId2"/>'
           '<w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1200" w:right="1133" w:bottom="1200" w:left="1133" w:header="700" '
           'w:footer="500" w:gutter="0"/>'
           '<w:cols w:space="425"/><w:docGrid w:linePitch="312"/></w:sectPr>')
# ================================================================ 块 → 文档
def h1_text(b):
    no = str(b.get("no", ""))
    if no.isdigit():
        return "第 %s 节　%s" % (no, b["text"])
    return b["text"]


def tree_para(b):
    body = run("「%s」" % b["name"], bold=True, color=TEAL_DARK) + runs(b["text"])
    return ('<w:p><w:pPr><w:pStyle w:val="TreeItem"/><w:spacing w:before="0" w:after="60"/></w:pPr>%s</w:p>'
            % body)


def render(blocks, title, version, meta, now):
    out = []
    toc = [b for b in blocks if b["kind"] == "h1"]
    if title:
        out.append(para(title, style="Title", keep=False))
    if version:
        out.append(para(version, style="CoverLine", keep=False))
    if meta:
        out.append(para(meta, style="CoverLine", keep=False))
    out.append(para("本 Word 版由纯文本说明书 docs\\使用说明.txt 自动生成，正文内容一字不改；"
                    "生成脚本 tools\\build_docx_manual.py（只用 Python 标准库，不依赖 Word 或第三方包）。"
                    "两者如有出入，以纯文本为准。", style="CoverNote", keep=False))
    if toc:
        out.append(para("本文目录", style="TocHead", keep=False))
        for b in toc:
            out.append(para(h1_text(b), style="TocItem", keep=False))
    for b in blocks:
        k = b["kind"]
        if k == "h1":
            out.append(para(h1_text(b), style="SectionTitle"))
        elif k == "h2":
            out.append(para(b["text"], style="StepTitle"))
        elif k == "h3":
            lead = (b.get("lead") + " ") if b.get("lead") else ""
            out.append(para(lead + b["text"], style="QTitle"))
        elif k == "p":
            out.append(para(b["text"], style="BodyText", keep=False))
        elif k == "indent":
            out.append(para(b["text"], style="Indent", keep=False))
        elif k == "bullet":
            out.append(para("· " + b["text"], style="Bullet", keep=False))
        elif k == "num":
            out.append(para("%s. %s" % (b["lead"], b["text"]), style="Numbered", keep=False))
        elif k == "note":
            out.append(para("★ " + b["text"], style="Note", keep=False))
        elif k == "callout_title":
            out.append(para("【" + b["text"] + "】", style="CalloutTitle", keep=False))
        elif k == "callout":
            out.append(para(b["text"], style="Callout", keep=False))
        elif k == "tree":
            out.append(tree_para(b))
        elif k == "table":
            out.append(table(b))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="%s" xmlns:r="%s"><w:body>%s%s<w:bookmarkStart w:id="0" w:name="_top"/>'
            '<w:bookmarkEnd w:id="0"/></w:body></w:document>' % (W_NS, R_NS, "".join(out), SECT_PR))


def write_docx(document_xml, title, version, now, docx_path=DOCX_PATH):
    docx_path = os.fspath(docx_path)  # 兼容 str 与 pathlib.Path
    parts = [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", RELS_ROOT),
        ("word/document.xml", document_xml),
        ("word/_rels/document.xml.rels", RELS_DOC),
        ("word/styles.xml", styles_xml()),
        ("word/footer1.xml", FOOTER.replace("%W%", W_NS).replace("%R%", R_NS)),
        ("docProps/core.xml", core_xml(title or "中文使用说明", version, now)),
        ("docProps/app.xml", APP_XML),
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts:
            zf.writestr(name, data.encode("utf-8"))
    tmp = docx_path + ".tmp"
    with io.open(tmp, "wb") as f:
        f.write(buf.getvalue())
    os.replace(tmp, docx_path)
    return os.path.getsize(docx_path)


def docx_text(docx_path=DOCX_PATH):
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    segs = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml, flags=re.S)
    return "".join(_unescape(s) for s in segs)


def _unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&amp;", "&"))


DROP = re.compile(r"[\s\u3000─│├└\u2500\u2502\u251c\u2514]+")


def norm(s):
    return DROP.sub("", s)


def verify(txt_path=TXT_PATH, docx_path=DOCX_PATH):
    """逐行核对：纯文本说明书的每一行，都必须原样出现在 docx 里。返回缺失行列表。"""
    body = norm(docx_text(docx_path))
    missing = []
    for line in read_lines(txt_path):
        s = line.strip()
        if not s or RE_EQ.match(s) or RE_DASH.match(s):
            continue
        if norm(s) not in body:
            missing.append(s)
    return missing


def build(txt_path=TXT_PATH, docx_path=DOCX_PATH, verbose=True):
    # 调用方既可能传 str 也可能传 pathlib.Path（tools/build_exe.py 传 str，测试传 Path），
    # 这里一次性归一化成 str，避免下面 docx_path + ".tmp" 之类的字符串拼接报 TypeError。
    txt_path = os.fspath(txt_path)
    docx_path = os.fspath(docx_path)
    lines = read_lines(txt_path)
    blocks = parse(lines)
    title, version, meta, rest = split_header(blocks)
    now = datetime.datetime.now()
    document = render(rest, title, version, meta, now)
    size = write_docx(document, title, version, now, docx_path)
    miss = verify(txt_path, docx_path)
    if miss:
        os.remove(docx_path)
        raise SystemExit("Word 说明书缺少纯文本里的 %d 行，已放弃生成：%s" % (
            len(miss), " / ".join(miss[:3])))
    tables = [b["id"] + ":" + str(len(b["rows"])) for b in blocks if b["kind"] == "table"]
    if verbose:
        print("已生成 %s（%.1f KB）" % (docx_path, size / 1024.0))
        print("块数 %d，表格 %s，逐行核对通过（%d 行全部命中）" % (
            len(blocks), tables, sum(1 for l in lines if l.strip() and not RE_EQ.match(l.strip()) and not RE_DASH.match(l.strip()))))
    return {"path": docx_path, "bytes": size, "blocks": len(blocks), "tables": tables}


def main():
    ap = argparse.ArgumentParser(description="由 使用说明.txt 生成 Word 版中文说明书（纯标准库）")
    ap.add_argument("--txt", default=TXT_PATH)
    ap.add_argument("--docx", default=DOCX_PATH)
    ap.add_argument("--check", action="store_true", help="只校验现有 docx 是否覆盖了 txt 的每一行")
    a = ap.parse_args()
    if a.check:
        miss = verify(a.txt, a.docx)
        if miss:
            print("不一致，缺少 %d 行：" % len(miss))
            for m in miss:
                print("  - " + m)
            return 1
        print("一致：docx 覆盖了 txt 的每一行内容")
        return 0
    build(a.txt, a.docx)
    return 0


if __name__ == "__main__":
    sys.exit(main())