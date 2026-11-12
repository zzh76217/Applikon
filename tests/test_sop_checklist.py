# -*- coding: utf-8 -*-
"""模块 5：SOP 防呆引导单元测试（第五轮）。

断言依据：requirements.md 模块 5（按阶段给检查清单与操作提示，可勾选确认）
+ config.yaml 的 sop 段（条目数量、阶段名、导出闸门开关、CSV 编码都从 config 读，不硬编码）。
"""
import csv

import pytest

from cell_planner.core import sop_checklist as sop
from cell_planner.core.config_loader import get_config

CFG = get_config()
S = CFG["sop"]
STAGES = list(S["stages"])
EXPECT_STAGE_NAMES = [str(st["name"]) for st in STAGES]
EXPECT_COUNTS = [len(st["items"]) for st in STAGES]
TOTAL = sum(EXPECT_COUNTS)
ENC = str(S["export"]["csv_encoding"])


def all_ids(cfg=CFG):
    return {row["id"] for row in sop.all_items(cfg)}


def cfg_with(**overrides):
    """改 sop 段做分支测试，不动真实 config。"""
    import copy
    cfg = copy.deepcopy(cfg_with_base())
    cfg["sop"].update(overrides)
    return cfg


def cfg_with_base():
    import copy
    return copy.deepcopy(CFG)


def _body_lines(text):
    """确认单正文行：4 列（3 个全角空格分隔），排除表头行。"""
    return [ln for ln in text.split("\n")
            if ln.count("\u3000") == 3 and not ln.startswith("\u3000".join(sop.CSV_HEADER))]

# ---------------------------------------------------------------- 条目来源
def test_stage_structure_comes_from_config():
    st = sop.stages(CFG)
    assert [x["name"] for x in st] == EXPECT_STAGE_NAMES
    assert [len(x["items"]) for x in st] == EXPECT_COUNTS
    assert sop.total_items(CFG) == TOTAL
    assert [s["key"] for s in st] == [str(x["key"]) for x in STAGES]
    # 条目文字必须与 config 一模一样（界面不许自己编文案）
    flat = [item for row in st for item in row["items"]]
    assert flat == [str(t) for st in STAGES for t in st["items"]]


def test_ids_are_unique_and_stable():
    rows = sop.all_items(CFG)
    assert len(rows) == TOTAL
    assert len({r["id"] for r in rows}) == TOTAL
    first = rows[0]
    assert first["id"] == sop.item_id(str(STAGES[0]["key"]), 1)
    assert first["stage_name"] == EXPECT_STAGE_NAMES[0]
    assert first["index"] == 1


def test_missing_or_broken_sop_section_raises_chinese_error():
    with pytest.raises(ValueError, match="缺少 sop 段"):
        sop.stages({})
    with pytest.raises(ValueError, match="缺少 sop 段"):
        sop.stages({"sop": {"stages": []}})
    bad = cfg_with_base()
    bad["sop"]["stages"][1]["items"] = []
    with pytest.raises(ValueError, match="没有任何检查条目"):
        sop.stages(bad)
    bad2 = cfg_with_base()
    bad2["sop"]["stages"][1]["key"] = str(bad2["sop"]["stages"][0]["key"])
    with pytest.raises(ValueError, match="重复的 key"):
        sop.stages(bad2)
    bad3 = cfg_with_base()
    bad3["sop"]["stages"][0]["name"] = ""
    with pytest.raises(ValueError, match="缺少 name 或 key"):
        sop.stages(bad3)
    with pytest.raises(ValueError, match="缺少 sop 段"):
        sop.export_csv("x.csv", [], {})


# ---------------------------------------------------------------- 进度统计
def test_progress_empty_and_full():
    empty = sop.progress([])
    assert empty["done"] == 0 and empty["total"] == TOTAL and empty["all_done"] is False
    assert [st["done"] for st in empty["stages"]] == [0] * len(EXPECT_COUNTS)
    assert [st["total"] for st in empty["stages"]] == EXPECT_COUNTS
    full = sop.progress(all_ids())
    assert full["done"] == TOTAL and full["all_done"] is True
    assert all(st["all_done"] for st in full["stages"])
    one = sop.progress([sop.item_id(str(STAGES[0]["key"]), 1)])
    assert one["done"] == 1
    assert one["stages"][0]["done"] == 1
    assert "1/" + str(EXPECT_COUNTS[0]) in one["stages"][0]["text"]
    assert "未确认" in one["stages"][0]["text"]


def test_progress_accepts_dict_and_ignores_unknown_ids():
    ids = all_ids()
    a = sorted(ids)[0]
    assert sop.progress({a: True, sorted(ids)[1]: False})["done"] == 1
    assert sop.progress({a: 1})["done"] == 1
    assert sop.progress([a, "不存在的条目:99"])["done"] == 1     # 多余 id 不得虚增进度
    assert sop.progress(None)["done"] == 0
    assert sop.progress(set())["done"] == 0


def test_unchecked_items_lists_the_missing_ones():
    ids = all_ids()
    partial = ids - {sop.item_id(str(STAGES[0]["key"]), 1)}
    missing = sop.unchecked_items(partial)
    assert len(missing) == 1
    assert missing[0]["text"] == str(STAGES[0]["items"][0])


# ---------------------------------------------------------------- 导出闸门
def test_export_gate_follows_config_switch():
    loose = cfg_with(require_all_checked_for_export=False)
    ok, msg = sop.export_gate([], loose)
    assert ok is True
    assert sop.NOT_CONFIRMED in msg and "未勾选" in msg
    strict = cfg_with(require_all_checked_for_export=True)
    ok2, msg2 = sop.export_gate([], strict)
    assert ok2 is False and "暂不能导出" in msg2
    ok3, msg3 = sop.export_gate(all_ids(), strict)
    assert ok3 is True and "均已确认" in msg3
    assert sop.require_all_checked(strict) is True
    assert sop.require_all_checked(loose) is False


# ---------------------------------------------------------------- 确认单内容
def test_build_rows_keeps_unchecked_items():
    rows = sop.build_rows([])
    assert len(rows) == TOTAL
    assert all(r[3] == sop.NOT_CONFIRMED for r in rows)
    header_len = sum(EXPECT_COUNTS[:1])
    assert rows[0][:3] == [EXPECT_STAGE_NAMES[0], "1", str(STAGES[0]["items"][0])]
    assert rows[header_len][0] == EXPECT_STAGE_NAMES[1]        # 阶段切换位置正确
    ids = all_ids()
    picked = {sop.item_id(str(STAGES[0]["key"]), 2)}
    rows2 = sop.build_rows(picked)
    assert [r[3] for r in rows2].count(sop.CONFIRMED) == 1
    assert rows2[1][3] == sop.CONFIRMED


def test_export_csv_content(tmp_path):
    ids = all_ids() - {sop.item_id(str(STAGES[-1]["key"]), 1)}
    path = sop.export_csv(tmp_path / "SOP确认单.csv", ids, CFG)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                     # utf-8-sig：Excel/WPS 双击不乱码
    text = raw.decode(ENC)
    with open(path, "r", encoding=ENC, newline="") as fh:
        rows = [r for r in csv.reader(fh) if r]
    body = [r for r in rows if len(r) >= 4]                     # 前 4 列为确认单正文行
    assert [EXPECT_STAGE_NAMES[0], "1", str(STAGES[0]["items"][0]), sop.CONFIRMED] in body
    assert any(r[3] == sop.NOT_CONFIRMED for r in body)         # 未勾选项也在单子里
    assert sop.CSV_HEADER in rows
    assert len(body) == TOTAL + 1                               # 表头 + 全部条目（一条都不能漏）
    joined = "\n".join(",".join(r) for r in rows)
    assert "需人工复核" in joined or "人工复核" in joined
    assert "my-Control" in joined                              # 保留"不控制硬件"边界声明
    assert "生成时间" in joined and "勾选进度" in joined


def test_export_csv_is_blocked_by_strict_switch(tmp_path):
    strict = cfg_with(require_all_checked_for_export=True)
    p = tmp_path / "不该存在.csv"
    with pytest.raises(ValueError, match="暂不能导出"):
        sop.export_csv(p, [], strict)
    assert not p.exists()
    # force=True（界面上的"我已知悉，仍要导出"）必须能落盘
    p2 = sop.export_csv(p, [], strict, force=True)
    assert p2.exists() and p2.stat().st_size > 0


def test_sheet_text_for_clipboard():
    txt = sop.sheet_text(all_ids(), CFG)
    assert "　".join(sop.CSV_HEADER) in txt
    body = _body_lines(txt)
    assert len(body) == TOTAL                                   # 正文行 = 条目数，一条不多一条不少
    assert all(ln.endswith(sop.CONFIRMED) for ln in body)
    assert "均已确认" in txt
    txt2 = sop.sheet_text([], CFG)
    body2 = _body_lines(txt2)
    assert len(body2) == TOTAL
    assert all(ln.endswith(sop.NOT_CONFIRMED) for ln in body2)
    assert _body_lines(txt2)[0].startswith(EXPECT_STAGE_NAMES[0])


def test_reset_switch_is_read_from_config():
    assert sop.reset_on_new_batch(CFG) is bool(S["reset_on_new_batch"])
    assert sop.reset_on_new_batch(cfg_with(reset_on_new_batch=False)) is False
    assert sop.reset_on_new_batch({"sop": {"stages": [{"key": "a", "name": "A", "items": ["x"]}]}}) is True