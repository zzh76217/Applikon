# -*- coding: utf-8 -*-
"""第六轮单元测试：core/diagnostics.py（运行日志 + 随包资源查找）。

要点：windowed 打包后 sys.stdout/sys.stderr 都是 None，原代码的
sys.stderr.write 会"出错时再崩一次"；本组测试锁死"绝不抛异常"这条底线。
日志文件名/目录名/轮转上限来自 config.app_info，测试用注入配置的方式验证，不写死。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cell_planner.core import config_loader
from cell_planner.core import diagnostics as dg


@pytest.fixture(autouse=True)
def _clear_config_cache():
    config_loader.get_config.cache_clear()
    yield
    config_loader.get_config.cache_clear()


# ==================== 日志落盘 ====================
def test_write_diagnostic_creates_log_file_and_returns_path(tmp_path):
    got = dg.write_diagnostic("测试一条诊断信息", level="提示", root=tmp_path)
    assert got is not None
    assert got.is_file()
    body = got.read_text(encoding="utf-8")
    assert "测试一条诊断信息" in body
    assert "[提示]" in body
    assert "[源码版]" in body          # 未打包时标注运行模式


def test_write_diagnostic_appends_not_overwrites(tmp_path):
    dg.write_diagnostic("第一条", root=tmp_path)
    got = dg.write_diagnostic("第二条", root=tmp_path)
    lines = [x for x in got.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 2
    assert lines[0].count("第一条") == 1 and "第二条" in lines[1]


def test_write_diagnostic_strips_trailing_blank_lines(tmp_path):
    got = dg.write_diagnostic("末尾有空行\n\n\n", root=tmp_path)
    body = got.read_text(encoding="utf-8")
    assert body.endswith("末尾有空行\n")


def test_write_diagnostic_accepts_non_string_payload(tmp_path):
    got = dg.write_diagnostic(ValueError("参数缺失：叶轮直径"), level="异常", root=tmp_path)
    assert "参数缺失：叶轮直径" in got.read_text(encoding="utf-8")


def test_write_diagnostic_survives_no_console_streams(tmp_path, monkeypatch):
    """打包成 windowed .exe 后 stdout/stderr 均为 None——必须照常写日志、不抛异常。"""
    monkeypatch.setattr(sys, "stdout", None, raising=False)
    monkeypatch.setattr(sys, "stderr", None, raising=False)
    got = dg.write_diagnostic("无控制台时也要能记下来", level="启动失败", root=tmp_path)
    assert got is not None and got.is_file()


def test_write_diagnostic_returns_none_when_io_fails(tmp_path, monkeypatch):
    def boom(root=None):
        raise OSError("磁盘不可用")
    monkeypatch.setattr(dg, "log_file", boom)
    assert dg.write_diagnostic("写不进去也不能崩", root=tmp_path) is None


def test_write_diagnostic_creates_missing_log_directory(tmp_path):
    monkeypatch_target = tmp_path / "新建目录"
    got = dg.write_diagnostic("目录不存在时自动建", root=monkeypatch_target)
    assert got.parent == monkeypatch_target / "logs"


# ==================== 日志设置来源（严禁硬编码） ====================
def test_log_settings_reads_names_from_config(monkeypatch):
    cfg = {"app_info": {"log_dir": "自定义日志目录", "log_file": "自定义日志.txt", "log_max_mb": 2}}
    monkeypatch.setattr(config_loader, "get_config", lambda: cfg)
    assert dg._log_settings() == ("自定义日志目录", "自定义日志.txt", 2)


def test_log_settings_falls_back_when_config_unreadable(monkeypatch):
    def boom():
        raise FileNotFoundError("配置文件不见了")
    monkeypatch.setattr(config_loader, "get_config", boom)
    dir_name, file_name, max_mb = dg._log_settings()
    assert (dir_name, file_name) == (dg._FALLBACK_LOG_DIR, dg._FALLBACK_LOG_FILE)
    assert max_mb == dg._FALLBACK_LOG_MAX_MB


def test_log_settings_falls_back_when_app_info_section_absent(monkeypatch):
    monkeypatch.setattr(config_loader, "get_config", lambda: {"process_defaults": {}})
    assert dg._log_settings() == (dg._FALLBACK_LOG_DIR, dg._FALLBACK_LOG_FILE, dg._FALLBACK_LOG_MAX_MB)


def test_log_path_uses_config_names(tmp_path, monkeypatch):
    cfg = {"app_info": {"log_dir": "L", "log_file": "日志.txt", "log_max_mb": 5}}
    monkeypatch.setattr(config_loader, "get_config", lambda: cfg)
    assert dg.log_dir(tmp_path) == tmp_path / "L"
    assert dg.log_file(tmp_path) == tmp_path / "L" / "日志.txt"


# ==================== 轮转 ====================
def test_log_rotates_when_exceeding_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "_log_settings", lambda: ("logs", "运行日志.txt", 0))  # 上限 0 → 每次都轮转
    dg.write_diagnostic("第一轮的内容", root=tmp_path)
    got = dg.write_diagnostic("第二轮的内容", root=tmp_path)
    old = tmp_path / "logs" / "运行日志.old.txt"
    assert old.is_file() and "第一轮" in old.read_text(encoding="utf-8")
    live = [x for x in got.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(live) == 1 and "第二轮" in live[0]


def test_rotation_failure_does_not_break_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "_log_settings", lambda: ("logs", "运行日志.txt", 0))
    monkeypatch.setattr(dg.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("被占用")))
    got = dg.write_diagnostic("轮转失败也要继续写", root=tmp_path)
    assert got is not None and "轮转失败也要继续写" in got.read_text(encoding="utf-8")


# ==================== 随包资源查找 ====================
def test_bundled_asset_finds_real_project_icon():
    """源码模式下 assets/app.ico 必须真的存在（第六轮交付物，缺失则 exe 无图标）。"""
    got = dg.bundled_asset("assets/app.ico")
    assert got is not None and got.is_file()


def test_bundled_asset_prefers_program_dir_over_meipass(tmp_path, monkeypatch):
    meipass = tmp_path / "meipass"
    (meipass / "assets").mkdir(parents=True)
    (meipass / "assets" / "x.ico").write_text("包内", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x.ico").write_text("程序目录", encoding="utf-8")
    monkeypatch.setattr(dg, "APP_ROOT", tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    got = dg.bundled_asset("assets/x.ico")
    assert got == tmp_path / "assets" / "x.ico"


def test_bundled_asset_uses_meipass_when_frozen(tmp_path, monkeypatch):
    meipass = tmp_path / "meipass"
    (meipass / "assets").mkdir(parents=True)
    (meipass / "assets" / "x.ico").write_text("包内", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    monkeypatch.setattr(dg, "APP_ROOT", tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    got = dg.bundled_asset("assets/x.ico")
    assert got == meipass / "assets" / "x.ico"


def test_bundled_asset_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "APP_ROOT", tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "没有"), raising=False)
    assert dg.bundled_asset("assets/不存在的图标.ico") is None


def test_bundled_asset_tolerates_empty_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "APP_ROOT", tmp_path)
    assert dg.bundled_asset("") is None