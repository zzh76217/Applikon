# -*- coding: utf-8 -*-
"""模块 4：SQLite 模板库单元测试（第五轮）。

所有读写都用 tmp_path 里的临时库文件，绝不碰工程 data/templates.db。
断言依据：requirements.md 模块 4（保存常用实验方案为模板 + 调出历史配置微调复用 + 多批次关键参数对比）
与 config.yaml 的 template_library / storage 两段（严禁硬编码，测试同样从 config 读）。
"""
import pytest

from cell_planner.core import template_store as ts
from cell_planner.core.config_loader import get_config

CFG = get_config()
KIND = str(CFG["template_library"]["setup_template_kind"])
FIELDS = [str(item["key"]) for item in CFG["template_library"]["compare_fields"]]
DB_NAME = str(CFG["storage"]["templates_db_path"]).replace("\\", "/").split("/")[-1]


@pytest.fixture()
def db(tmp_path):
    """临时库文件（每次测试独立）。"""
    return tmp_path / DB_NAME


def test_db_path_comes_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "PROJECT_ROOT", tmp_path)
    got = ts.db_path(CFG)
    assert got == tmp_path / str(CFG["storage"]["templates_db_path"])


def test_init_db_is_idempotent(db):
    conn = ts.connect(path=db)
    conn.close()
    ts.init_db(ts.connect(path=db))
    ts.init_db(ts.connect(path=db))
    assert ts.list_setup_templates(path=db) == []
    assert ts.list_batches(path=db) == []


def test_save_then_update_same_name_keeps_one_row(db):
    payload = {"working_volume_ml": 2000.0, "cell_line_name": "CHO-DG44", "culture_days": 10}
    msg = ts.save_setup_template("CHO-DG44 常规", payload, note="第一轮备注", path=db)
    assert "已新建模板" in msg and "CHO-DG44 常规" in msg
    payload2 = dict(payload, working_volume_ml=1500.0)
    msg2 = ts.save_setup_template("  CHO-DG44 常规  ", payload2, note="改过体积", path=db)
    assert "已更新同名模板" in msg2
    rows = ts.list_setup_templates(path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["名称"] == "CHO-DG44 常规"          # 名称首尾空格被去掉
    assert row["类型"] == KIND                      # 默认类型来自 config
    assert row["备注"] == "改过体积"
    assert row["创建时间"] and row["更新时间"]
    loaded = ts.load_setup_template("CHO-DG44 常规", path=db)
    assert loaded["参数"] == payload2               # 内容原样回读（含数值类型）
    assert loaded["备注"] == "改过体积"


def test_list_templates_is_sorted_by_name(db):
    for name in ("乙方案", "甲方案", "丙方案"):
        ts.save_setup_template(name, {"a": 1}, path=db)
    assert [r["名称"] for r in ts.list_setup_templates(path=db)] == sorted(["甲方案", "乙方案", "丙方案"])


def test_template_kind_can_be_overridden(db):
    ts.save_setup_template("特殊", {"a": 1}, kind="自定义模板", path=db)
    assert ts.list_setup_templates(path=db)[0]["类型"] == "自定义模板"


def test_illegal_template_input_raises_chinese_error(db):
    with pytest.raises(ValueError, match="不能为空"):
        ts.save_setup_template("   ", {"a": 1}, path=db)
    with pytest.raises(ValueError, match="过长"):
        ts.save_setup_template("名" * 61, {"a": 1}, path=db)
    with pytest.raises(ValueError, match="必须是参数列表"):
        ts.save_setup_template("坏内容", ["不是字典"], path=db)   # type: ignore[arg-type]
    with pytest.raises(ValueError, match="找不到模板"):
        ts.load_setup_template("没存过", path=db)
    with pytest.raises(ValueError, match="找不到要删除的模板"):
        ts.delete_setup_template("没存过", path=db)


def test_delete_template(db):
    ts.save_setup_template("要删的", {"a": 1}, path=db)
    ts.delete_setup_template("要删的", path=db)
    assert ts.list_setup_templates(path=db) == []


def test_batch_save_and_compare(db):
    m1 = {k: 1.0 for k in FIELDS}
    m1["is_simulated"] = False
    msg = ts.save_batch("批次A", m1, source_control="a_ctrl.csv", source_offline="a_off.csv",
                        is_simulated=False, path=db)
    assert "已新建批次记录" in msg
    m2 = {k: 2.0 for k in FIELDS}
    ts.save_batch("批次B", m2, source_control="b_ctrl.csv", is_simulated=True, path=db)
    rows = ts.list_batches(path=db)
    assert {r["批次名"] for r in rows} == {"批次A", "批次B"}
    sim = {r["批次名"]: r["是否模拟数据"] for r in rows}
    assert sim["批次B"].startswith("是") and "SIMULATED" in sim["批次B"]   # 答复#8：模拟数据必须显式标注
    assert sim["批次A"] == "否"
    assert ts.load_batch_metrics("批次A", path=db)["peak_density_mcells_ml"] == 1.0
    cmp_rows = ts.compare_batches(["批次A", "批次B"], path=db, cfg=CFG)
    assert [r["key"] for r in cmp_rows] == FIELDS                # 对比字段清单来自 config
    assert [r["label"] for r in cmp_rows] == [str(i["label"]) for i in CFG["template_library"]["compare_fields"]]
    assert all(set(r["values"]) == {"批次A", "批次B"} for r in cmp_rows)
    assert cmp_rows[0]["values"]["批次B"] == 2.0


def test_compare_batches_needs_at_least_two(db):
    ts.save_batch("只有一个", {k: 1.0 for k in FIELDS}, path=db)
    with pytest.raises(ValueError, match="至少需要勾选 2 个批次"):
        ts.compare_batches(["只有一个"], path=db)
    with pytest.raises(ValueError, match="至少需要勾选 2 个批次"):
        ts.compare_batches([], path=db)
    with pytest.raises(ValueError, match="找不到批次记录"):
        ts.compare_batches(["只有一个", "不存在的批次"], path=db)


def test_missing_metric_shows_none_instead_of_crashing(db):
    ts.save_batch("有密度", {"peak_density_mcells_ml": 18.0}, path=db)
    ts.save_batch("空乳酸", {"lactate_max_g_l": 3.0}, path=db)
    rows = {r["key"]: r["values"] for r in ts.compare_batches(["有密度", "空乳酸"], path=db, cfg=CFG)}
    assert rows["peak_density_mcells_ml"]["有密度"] == 18.0
    assert rows["lactate_max_g_l"]["有密度"] is None            # 缺字段 → None，由界面显示为 —
    assert rows["lactate_max_g_l"]["空乳酸"] == 3.0


def test_empty_metrics_rejected_and_same_batch_is_updated(db):
    with pytest.raises(ValueError, match="没有可保存的分析摘要"):
        ts.save_batch("空批次", {}, path=db)
    with pytest.raises(ValueError, match="没有可保存的分析摘要"):
        ts.save_batch("空批次", None, path=db)                  # type: ignore[arg-type]
    ts.save_batch("同一批", {"peak_density_mcells_ml": 1.0}, path=db)
    assert "已更新同名批次" in ts.save_batch("同一批", {"peak_density_mcells_ml": 9.0}, path=db)
    assert len(ts.list_batches(path=db)) == 1
    assert ts.load_batch_metrics("同一批", path=db)["peak_density_mcells_ml"] == 9.0
    ts.delete_batch("同一批", path=db)
    assert ts.list_batches(path=db) == []
    with pytest.raises(ValueError, match="找不到要删除的批次记录"):
        ts.delete_batch("同一批", path=db)
    with pytest.raises(ValueError, match="找不到批次记录"):
        ts.load_batch_metrics("同一批", path=db)


def test_corrupt_db_file_gives_chinese_error(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"this is not a sqlite database file")
    with pytest.raises(ValueError) as exc:
        ts.list_setup_templates(path=db)
    assert "模板库" in str(exc.value) or "失败" in str(exc.value)