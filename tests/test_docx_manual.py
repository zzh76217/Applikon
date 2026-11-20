# -*- coding: utf-8 -*-
"""第七轮补充·Word 说明书测试：docs/使用说明.docx 由 tools/build_docx_manual.py 从 docs/使用说明.txt 生成。

本文件只回答三件事，不重复校验工艺数值（那些在 test_formulas.py / test_validators.py 里）：
1) 生成的 .docx 是不是合法的 OOXML 包（Word 打不开=交付事故）；
2) 内容与 docs/使用说明.txt 是否逐行一致（不丢字、不编造新章节），且伪表格真的变成了 Word 表格；
3) 打包链路 tools/build_exe.py 是否确实会把 .docx 放进交付目录。
"""
from __future__ import annotations

import re
import sys
import xml.dom.minidom
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TXT_PATH = ROOT / "docs" / "使用说明.txt"
DOCX_PATH = ROOT / "docs" / "使用说明.docx"
BUILD_EXE_PATH = ROOT / "tools" / "build_exe.py"

sys.path.insert(0, str(ROOT / "tools"))
import build_docx_manual  # noqa: E402

# Word 说明书必须包含的包部件（缺任何一个，Word 会报「文件已损坏」）
REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/footer1.xml",
    "docProps/core.xml",
    "docProps/app.xml",
]

FW = "　"  # 全角空格：txt 里用它对齐，docx 里必须换成真表格
CONTENT_W = 9640  # A4 正文宽度（11906 - 1133×2，单位 twip）
N_SECTIONS = 10   # 说明书正文节数（封面目录与正文必须一致）


def _read_parts(docx_path: Path) -> dict[str, str]:
    """把 .docx 当 zip 读出来，返回 {部件名: 文本内容}。"""
    with zipfile.ZipFile(docx_path) as zf:
        assert zf.testzip() is None, ".docx 压缩包本身损坏（CRC 校验失败）"
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


@pytest.fixture(scope="module")
def parts() -> dict[str, str]:
    assert DOCX_PATH.exists(), f"缺少 Word 说明书：{DOCX_PATH}，请先运行 python tools\\build_docx_manual.py"
    return _read_parts(DOCX_PATH)


@pytest.fixture(scope="module")
def document_xml(parts: dict[str, str]) -> str:
    return parts["word/document.xml"]


@pytest.fixture(scope="module")
def body_text() -> str:
    return build_docx_manual.docx_text()


def _tables(document_xml: str) -> list[list[list[str]]]:
    """提取每张表为 [[行, ...], ...]，每行为各单元格的纯文本列表。"""
    out = []
    for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", document_xml, re.S):
        rows = []
        for tr in re.findall(r"<w:tr(?:\s[^>]*)?>.*?</w:tr>", tbl, re.S):
            cells = []
            for tc in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S):
                cells.append("".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", tc, re.S)))
            rows.append(cells)
        out.append(rows)
    return out


# ==================== 1. 包合法性 ====================
def test_all_required_parts_exist(parts: dict[str, str]):
    missing = [name for name in REQUIRED_PARTS if name not in parts]
    assert not missing, "Word 说明书缺少这些必需部件：" + "、".join(missing)


def test_every_xml_part_is_well_formed(parts: dict[str, str]):
    for name, content in parts.items():
        if not (name.endswith(".xml") or name.endswith(".rels")):
            continue
        try:
            xml.dom.minidom.parseString(content)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"部件 {name} 不是合法 XML，Word 会提示需要修复：{exc}")


def test_no_empty_valign_tag_left_in_document(document_xml: str):
    # 曾经踩过：写成 <vAlign/> 这种非法空标签，Word 直接判定文件损坏。
    assert "<vAlign/>" not in document_xml, "document.xml 里出现非法空标签 <vAlign/>，Word 会报文件损坏"
    assert "<vAlign />" not in document_xml, "document.xml 里出现非法空标签 <vAlign />，Word 会报文件损坏"


def test_section_title_style_breaks_page_and_is_in_toc(parts: dict[str, str], document_xml: str):
    """每个「第 N 节」都要能整页起新页，并出现在 Word 导航窗格里。"""
    styles = parts["word/styles.xml"]
    section_style = re.search(r'<w:style [^>]*w:styleId="SectionTitle".*?</w:style>', styles, re.S)
    assert section_style is not None, "styles.xml 缺少 SectionTitle 样式"
    assert "<w:pageBreakBefore" in section_style.group(0), "SectionTitle 样式没有 pageBreakBefore，每节不会另起一页"
    assert "<w:outlineLvl" in section_style.group(0), "SectionTitle 样式没有大纲级别，Word 导航窗格看不到目录"
    assert document_xml.count('<w:pStyle w:val="SectionTitle"') == N_SECTIONS, "正文节标题数量与说明书应有的 10 节不一致"


def test_all_paragraph_styles_are_defined(parts: dict[str, str], document_xml: str):
    styles = parts["word/styles.xml"]
    defined = set(re.findall(r'<w:style w:type="\w+" w:styleId="([^"]+)"', styles))
    used = set(re.findall(r'<w:pStyle w:val="([^"]+)"', document_xml))
    missing = sorted(used - defined)
    assert not missing, "正文引用了未在 styles.xml 定义的段落样式：" + "、".join(missing)


def test_footer_has_page_number_fields(parts: dict[str, str], document_xml: str):
    assert "<w:footerReference" in document_xml, "正文没有引用页脚，打印时没有页码"
    footer = parts["word/footer1.xml"]
    assert "PAGE" in footer and "NUMPAGES" in footer, "页脚缺少「第 X 页 / 共 Y 页」域代码"


# ==================== 2. 内容与 txt 逐行一致 ====================
def test_docx_content_covers_every_manual_line():
    problems = build_docx_manual.verify()
    assert problems == [], "Word 说明书与 docs/使用说明.txt 不一致，缺少这些内容：" + " ｜ ".join(str(x) for x in problems[:5])


def test_no_fake_table_spacing_left_in_docx(body_text: str):
    # txt 里用连续全角空格对齐的「伪表格」，在 docx 里必须是真表格，不应再留一串空格。
    assert re.search("[\u3000]{3,}", body_text) is None, "正文里仍有 3 个以上连续全角空格，说明伪表格没转成 Word 表格"
    assert "====" not in body_text, "正文里残留 === 分隔线，排版未清理干净"
    assert "----" not in body_text, "正文里残留 --- 分隔线，排版未清理干净"


def test_three_semantic_tables_with_expected_shape(parts: dict[str, str], document_xml: str):
    """18 条校验表 / 文件清单表 / 术语表必须都是真正的 Word 表格。"""
    tables = _tables(document_xml)
    assert len(tables) == 3, f"应有 3 张表（校验/文件/术语），实际 {len(tables)} 张"
    headers = [tbl[0] for tbl in tables]
    assert ["编号", "查什么", "超范围时"] in headers, "缺少 18 条校验规则表"
    assert ["文件", "说明"] in headers, "缺少数据文件清单表"
    assert ["术语", "含义"] in headers, "缺少术语小词典表"
    grid_sums = [
        sum(int(w) for w in re.findall(r'<w:gridCol w:w="(\d+)"', tbl))
        for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", document_xml, re.S)
    ]
    for width in grid_sums:
        assert width == CONTENT_W, f"表格列宽合计 {width} 不等于正文宽度 {CONTENT_W}，Word 里会超出版心"
    assert document_xml.count(f'<w:tblW w:w="{CONTENT_W}"') == 3, "三张表都应设置整表宽度为正文宽度"


def test_rules_table_lists_r01_to_r18(document_xml: str):
    tables = _tables(document_xml)
    rules = next((tbl for tbl in tables if tbl[0][:1] == ["编号"]), None)
    assert rules is not None, "找不到 18 条校验规则表"
    codes = [row[0].strip() for row in rules[1:]]
    expected = [f"R{n:02d}" for n in range(1, 19)]
    assert codes == expected, f"校验表编号应为 R01–R18，实际为：{codes}"
    assert len(rules) == 19, "校验表应为表头 + 18 行"


def test_files_and_terms_table_row_counts(document_xml: str):
    tables = _tables(document_xml)
    files = next(tbl for tbl in tables if tbl[0][:1] == ["文件"])
    terms = next(tbl for tbl in tables if tbl[0][:1] == ["术语"])
    assert len(files) == 7, f"数据文件清单应为表头 + 6 行，实际 {len(files)} 行"
    assert len(terms) == 11, f"术语表应为表头 + 10 行，实际 {len(terms)} 行"


def test_docx_mentions_tabs_version_and_safety_words(parts: dict[str, str], body_text: str):
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    app = cfg["app_info"]
    for title in app["outer_tab_titles"]:
        assert title in body_text, f"Word 说明书没提到大板块「{title}」"
    for title in app["tab_titles"]:
        assert title in body_text, f"Word 说明书没提到页面「{title}」"
    assert app["version"] in body_text, "Word 说明书没写当前版本号"
    for keyword in ("人工复核", "SIMULATED"):
        assert keyword in body_text, f"Word 说明缺少关键提醒「{keyword}」"


def test_docx_is_registered_in_config_and_txt_manual():
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["app_info"].get("manual_docx_file") == "使用说明.docx", "config.yaml 的 app_info.manual_docx_file 未登记 Word 说明书"
    txt = TXT_PATH.read_text(encoding="utf-8")
    assert "使用说明.docx" in txt, "txt 说明书没告诉用户还有 Word 版"


# ==================== 3. 生成过程可复现 ====================
def test_build_is_reproducible_and_passes_verify(tmp_path: Path):
    """同一份 txt 连生成两次，正文必须完全一致（不比较字节，因 core.xml 含构建时间）。"""
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"
    info_a = build_docx_manual.build(txt_path=TXT_PATH, docx_path=first, verbose=False)
    info_b = build_docx_manual.build(txt_path=TXT_PATH, docx_path=second, verbose=False)
    assert first.exists() and second.exists(), "生成器没有写出 .docx"
    assert build_docx_manual.docx_text(first) == build_docx_manual.docx_text(second), "两次生成的正文不一致，排版不稳定"
    assert info_a["blocks"] == info_b["blocks"] > 0, "块数应为正且两次相同"
    assert info_a["tables"] == ["rules:18", "files:6", "terms:10"], f"三张表的行数登记不符合预期：{info_a['tables']}"


def test_build_refuses_to_ship_when_content_missing(tmp_path: Path, monkeypatch):
    """逐行核对不通过时必须删掉半成品并报错，绝不能留下一个内容不完整的 .docx。

    触发方式：故意让渲染器只排版第一个块（模拟"生成器漏内容"这类缺陷），
    验证安全闸门确实会拦截 —— 拦不住就等于把残缺说明书发给了用户。
    """
    real_render = build_docx_manual.render
    monkeypatch.setattr(
        build_docx_manual, "render",
        lambda blocks, title, version, meta, now: real_render(blocks[:1], title, version, meta, now),
    )
    out = tmp_path / "不应存在.docx"
    with pytest.raises(SystemExit):
        build_docx_manual.build(txt_path=TXT_PATH, docx_path=out, verbose=False)
    assert not out.exists(), "校验失败后仍残留 .docx，会被误当成交付物"


def test_build_exe_wires_the_docx_into_delivery():
    src = BUILD_EXE_PATH.read_text(encoding="utf-8")
    for token in ("manual_docx_file", "build_docx_manual", "docx_name"):
        assert token in src, f"打包脚本 tools/build_exe.py 里没有「{token}」，Word 说明书不会进交付目录"
