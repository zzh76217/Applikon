# -*- coding: utf-8 -*-
"""模块 4：SQLite 模板库（第五轮，答复#11）。

库文件路径只从 config.storage.templates_db_path 读取（data/templates.db，标准库 sqlite3，不联网）。
与第三轮的 JSON 配方分工不同、互不替代：
  配方（data/recipes/*.json）  = ①批次配置页的输入参数快照，人可读、可直接拷贝备份
  模板（本库 setup_templates） = 实验方案模板（细胞株/培养基/工艺设定/备注），可调用回填①页
  批次（本库 batches）        = ③离线分析得到的关键参数摘要，用于"多批次关键参数对比"
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from cell_planner.core.config_loader import PROJECT_ROOT, get_config

SCHEMA_VERSION = 1

_SQL_SETUP = """
CREATE TABLE IF NOT EXISTS setup_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

_SQL_BATCH = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name TEXT NOT NULL UNIQUE,
    saved_at TEXT NOT NULL,
    source_control TEXT NOT NULL DEFAULT '',
    source_offline TEXT NOT NULL DEFAULT '',
    is_simulated INTEGER NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL
);
"""

_SQL_META = """
CREATE TABLE IF NOT EXISTS db_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def db_path(cfg: Optional[dict] = None) -> Path:
    """模板库路径（来自 config.storage.templates_db_path）。"""
    cfg = cfg or get_config()
    return PROJECT_ROOT / str(cfg["storage"]["templates_db_path"])


def connect(path: Optional[Path] = None, cfg: Optional[dict] = None) -> sqlite3.Connection:
    p = Path(path) if path is not None else db_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(p))
    except sqlite3.Error as exc:
        raise ValueError("无法打开模板库文件 %s：%s。请确认 data 目录可写、文件没被别的程序占用。" % (p, exc)) from exc
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    try:
        conn.executescript(_SQL_SETUP + _SQL_BATCH + _SQL_META)
        conn.execute("INSERT OR IGNORE INTO db_meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
    except sqlite3.Error as exc:
        raise ValueError("模板库初始化失败：" + str(exc)) from exc


def _check_name(name: str, what: str) -> str:
    s = str(name or "").strip()
    if not s:
        raise ValueError("%s名称不能为空，请先在名称框里填写。" % what)
    if len(s) > 60:
        raise ValueError("%s名称过长（最多 60 个字符），请精简后再保存。" % what)
    return s


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 实验方案模板
def save_setup_template(name: str, payload: Dict[str, object], note: str = "",
                        kind: Optional[str] = None, path: Optional[Path] = None) -> str:
    cfg = get_config()
    name = _check_name(name, "模板")
    kind = str(kind or cfg["template_library"]["setup_template_kind"])
    if not isinstance(payload, dict):
        raise ValueError("模板内容必须是参数列表（对象），当前内容无法保存。")
    now = _now()
    conn = connect(path=path, cfg=cfg)
    try:
        cur = conn.execute("SELECT id, created_at FROM setup_templates WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE setup_templates SET kind=?, note=?, updated_at=?, payload_json=? WHERE id=?",
                (kind, str(note or ""), now, json.dumps(payload, ensure_ascii=False), row["id"]))
            action = "已更新同名模板"
        else:
            conn.execute(
                "INSERT INTO setup_templates(name, kind, note, created_at, updated_at, payload_json) "
                "VALUES(?,?,?,?,?,?)",
                (name, kind, str(note or ""), now, now, json.dumps(payload, ensure_ascii=False)))
            action = "已新建模板"
        conn.commit()
    except sqlite3.Error as exc:
        raise ValueError("保存模板失败：" + str(exc)) from exc
    finally:
        conn.close()
    return "%s：%s" % (action, name)


def list_setup_templates(path: Optional[Path] = None) -> List[dict]:
    conn = connect(path=path)
    try:
        rows = conn.execute(
            "SELECT name, kind, note, created_at, updated_at FROM setup_templates ORDER BY name").fetchall()
        return [{"名称": r["name"], "类型": r["kind"], "备注": r["note"],
                 "创建时间": r["created_at"], "更新时间": r["updated_at"]} for r in rows]
    except sqlite3.Error as exc:
        raise ValueError("读取模板列表失败：" + str(exc)) from exc
    finally:
        conn.close()


def load_setup_template(name: str, path: Optional[Path] = None) -> dict:
    conn = connect(path=path)
    try:
        r = conn.execute("SELECT payload_json, note, updated_at FROM setup_templates WHERE name = ?",
                         (str(name or "").strip(),)).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("读取模板失败：" + str(exc)) from exc
    finally:
        conn.close()
    if not r:
        raise ValueError("找不到模板：" + str(name) + "（请先在列表里选中一个模板）")
    try:
        payload = json.loads(r["payload_json"])
    except ValueError as exc:
        raise ValueError("模板内容已损坏，无法解析：" + str(exc)) from exc
    if not isinstance(payload, dict):
        raise ValueError("模板内容格式不对（应为参数列表），请删除后重新保存。")
    return {"参数": payload, "备注": r["note"], "更新时间": r["updated_at"]}


def delete_setup_template(name: str, path: Optional[Path] = None) -> None:
    conn = connect(path=path)
    try:
        cur = conn.execute("DELETE FROM setup_templates WHERE name = ?", (str(name or "").strip(),))
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("找不到要删除的模板：" + str(name))
    except sqlite3.Error as exc:
        raise ValueError("删除模板失败：" + str(exc)) from exc
    finally:
        conn.close()


# ---------------------------------------------------------------- 批次摘要
def save_batch(batch_name: str, metrics: Dict[str, object], source_control: str = "",
               source_offline: str = "", is_simulated: bool = False,
               path: Optional[Path] = None) -> str:
    batch_name = _check_name(batch_name, "批次")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("没有可保存的分析摘要，请先在③离线分析页导入 CSV 并运行分析。")
    conn = connect(path=path)
    try:
        now = _now()
        payload = json.dumps(metrics, ensure_ascii=False, default=str)
        r = conn.execute("SELECT id FROM batches WHERE batch_name = ?", (batch_name,)).fetchone()
        if r:
            conn.execute("UPDATE batches SET saved_at=?, source_control=?, source_offline=?, is_simulated=?, "
                         "metrics_json=? WHERE id=?",
                         (now, str(source_control or ""), str(source_offline or ""), int(bool(is_simulated)), payload, r["id"]))
            action = "已更新同名批次"
        else:
            conn.execute("INSERT INTO batches(batch_name, saved_at, source_control, source_offline, is_simulated, "
                         "metrics_json) VALUES(?,?,?,?,?,?)",
                         (batch_name, now, str(source_control or ""), str(source_offline or ""),
                          int(bool(is_simulated)), payload))
            action = "已新建批次记录"
        conn.commit()
    except sqlite3.Error as exc:
        raise ValueError("保存批次记录失败：" + str(exc)) from exc
    finally:
        conn.close()
    return "%s：%s" % (action, batch_name)


def list_batches(path: Optional[Path] = None) -> List[dict]:
    conn = connect(path=path)
    try:
        rows = conn.execute(
            "SELECT batch_name, saved_at, source_control, source_offline, is_simulated FROM batches "
            "ORDER BY saved_at DESC, batch_name").fetchall()
        return [{"批次名": r["batch_name"], "保存时间": r["saved_at"], "控制数据文件": r["source_control"],
                 "离线取样文件": r["source_offline"], "是否模拟数据": "是（SIMULATED）" if r["is_simulated"] else "否"}
                for r in rows]
    except sqlite3.Error as exc:
        raise ValueError("读取批次列表失败：" + str(exc)) from exc
    finally:
        conn.close()


def load_batch_metrics(batch_name: str, path: Optional[Path] = None) -> Dict[str, object]:
    conn = connect(path=path)
    try:
        r = conn.execute("SELECT metrics_json, is_simulated FROM batches WHERE batch_name = ?",
                         (str(batch_name or "").strip(),)).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("读取批次记录失败：" + str(exc)) from exc
    finally:
        conn.close()
    if not r:
        raise ValueError("找不到批次记录：" + str(batch_name))
    try:
        data = json.loads(r["metrics_json"])
    except ValueError as exc:
        raise ValueError("批次摘要已损坏，无法解析：" + str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("批次摘要格式不对（应为参数列表），请删除后重新保存。")
    data.setdefault("is_simulated", bool(r["is_simulated"]))
    return data


def delete_batch(batch_name: str, path: Optional[Path] = None) -> None:
    conn = connect(path=path)
    try:
        cur = conn.execute("DELETE FROM batches WHERE batch_name = ?", (str(batch_name or "").strip(),))
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("找不到要删除的批次记录：" + str(batch_name))
    except sqlite3.Error as exc:
        raise ValueError("删除批次记录失败：" + str(exc)) from exc
    finally:
        conn.close()


def compare_batches(names: Sequence[str], fields: Optional[Sequence[str]] = None,
                    path: Optional[Path] = None, cfg: Optional[dict] = None) -> List[dict]:
    """多批次关键参数对比：返回 [{key, label, values: {批次名: 值}}]，字段清单来自 config。"""
    cfg = cfg or get_config()
    picked = [str(n).strip() for n in (names or []) if str(n).strip()]
    if len(picked) < 2:
        raise ValueError("至少需要勾选 2 个批次才能对比（在批次列表里按住 Ctrl 点选）。")
    if fields is None:
        fields = [str(item["key"]) for item in cfg["template_library"]["compare_fields"]]
    metrics = {n: load_batch_metrics(n, path=path) for n in picked}
    rows: List[dict] = []
    label = {}
    for item in cfg["template_library"]["compare_fields"]:
        label[str(item["key"])] = str(item.get("label") or item["key"])
    for key in fields:
        rows.append({"key": key, "label": label.get(key, key),
                     "values": {n: metrics[n].get(key) for n in picked}})
    return rows