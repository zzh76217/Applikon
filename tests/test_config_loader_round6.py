# -*- coding: utf-8 -*-
"""第六轮单元测试：core/config_loader.py 的打包路径规则 + config.app_info 段完整性。

覆盖三条打包底线：
1) 打包版所有可写文件必须落在 exe 所在目录，而不是 onefile 的临时解包目录（否则用户数据随进程消失）。
2) exe 同目录没有 config.yaml 时，要能把内置默认配置释放出来；目录只读时要退回内置副本而不是崩溃。
3) 界面标题/日志/说明书/exe 名这些身份信息只能来自 config.yaml（AGENTS.md 硬约束 1、2），本文件负责守住这份完整性。
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from string import Formatter

import pytest

from cell_planner.core import config_loader as cl

APP_INFO_KEYS = (
    "name", "version", "round_label", "title_template", "log_dir", "log_file",
    "log_max_mb", "manual_file", "icon_file", "exe_name", "locations_template",
)
TEXT_KEYS = ("name", "round_label", "title_template", "log_dir", "log_file",
             "manual_file", "icon_file", "exe_name", "locations_template")


@pytest.fixture(autouse=True)
def _clear_cache():
    cl.get_config.cache_clear()
    yield
    cl.get_config.cache_clear()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """把配置目录/文件指针挪到临时目录，避免测试碰到真实工程文件。"""
    cfg_dir = tmp_path / "config"
    monkeypatch.setattr(cl, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cl, "CONFIG_FILE", cfg_dir / "config.yaml")
    return tmp_path


# ==================== 根目录规则 ====================
def test_project_root_kept_as_alias_of_app_root():
    """历史模块都用 PROJECT_ROOT 派生 data/ 路径，第六轮必须让它与 APP_ROOT 同指一处。"""
    assert cl.PROJECT_ROOT is cl.APP_ROOT


def test_run_mode_label_matches_frozen_flag():
    assert cl.RUN_MODE == ("打包版" if cl.IS_FROZEN else "源码版")


def test_config_paths_hang_off_app_root():
    assert cl.CONFIG_DIR == cl.APP_ROOT / "config"
    assert cl.CONFIG_FILE == cl.CONFIG_DIR / "config.yaml"


def test_source_run_root_is_repo_root():
    assert cl.APP_ROOT == Path(__file__).resolve().parents[1]


def test_frozen_root_is_exe_directory_not_meipass(tmp_path, monkeypatch):
    """关键：onefile 的临时解包目录（_MEIPASS）不能当根目录，否则用户数据会随程序关闭消失。"""
    monkeypatch.setattr(cl, "IS_FROZEN", True)
    fake_exe = tmp_path / "细胞培养接种与批次配置规划软件.exe"
    fake_exe.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI12345"), raising=False)
    assert cl._resolve_app_root() == tmp_path.resolve()


def test_source_root_ignores_executable(monkeypatch):
    monkeypatch.setattr(cl, "IS_FROZEN", False)
    assert cl._resolve_app_root() == Path(cl.__file__).resolve().parents[3]


# ==================== ensure_external_config 四个分支 ====================
def test_existing_external_config_used_untouched(isolated, monkeypatch):
    target = cl.CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("marker: 用户自己改过的外部配置", encoding="utf-8")
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: pytest.fail("外部配置存在时不该去碰内置副本"))
    assert cl.ensure_external_config() == target


def test_bundled_default_config_is_released_next_to_exe(isolated, monkeypatch):
    bundled = isolated / "pkg" / "config.yaml"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_text("marker: 内置出厂默认", encoding="utf-8")
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: bundled)
    got = cl.ensure_external_config()
    assert got == cl.CONFIG_FILE
    assert got.read_text(encoding="utf-8") == "marker: 内置出厂默认"


def test_missing_everywhere_raises_chinese_hint(isolated, monkeypatch):
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: None)
    with pytest.raises(FileNotFoundError, match="找不到配置文件"):
        cl.ensure_external_config()


def test_copy_failure_falls_back_to_bundled_copy(isolated, monkeypatch):
    """装在 Program Files 等只读位置时：释放失败要能用内置副本继续跑，不能拒绝启动。"""
    bundled = isolated / "pkg" / "config.yaml"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_text("marker: 内置", encoding="utf-8")
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: bundled)
    monkeypatch.setattr(cl, "shutil", types.SimpleNamespace(
        copyfile=lambda *a, **k: (_ for _ in ()).throw(PermissionError("拒绝写入"))))
    assert cl.ensure_external_config() == bundled


def test_mkdir_failure_falls_back_to_bundled_copy(isolated, monkeypatch):
    bundled = isolated / "pkg" / "config.yaml"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_text("marker: 内置", encoding="utf-8")
    blocker = isolated / "我其实是文件"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(cl, "CONFIG_DIR", blocker / "config")
    monkeypatch.setattr(cl, "CONFIG_FILE", blocker / "config" / "config.yaml")
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: bundled)
    assert cl.ensure_external_config() == bundled


def test_bundled_config_absent_in_source_run():
    """源码运行时没有 _MEIPASS，内置副本必须是 None（否则会误覆盖用户手改的配置）。"""
    assert cl._bundled_config_file() is None


# ==================== config_source ====================
def test_config_source_always_names_a_path(isolated, monkeypatch):
    monkeypatch.setattr(cl, "_bundled_config_file", lambda: None)
    got = cl.config_source()
    assert got.endswith(str(Path("config") / "config.yaml"))


# ==================== get_config / reload_config ====================
def test_get_config_reads_whichever_file_is_active(isolated):
    cl.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.CONFIG_FILE.write_text("probe:\n  answer: 42\n", encoding="utf-8")
    assert cl.get_config()["probe"]["answer"] == 42


def test_get_config_rejects_non_mapping_top_level(isolated):
    cl.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.CONFIG_FILE.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="配置文件格式错误"):
        cl.get_config()


def test_reload_config_picks_up_external_edits(isolated):
    cl.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.CONFIG_FILE.write_text("probe:\n  answer: 1\n", encoding="utf-8")
    assert cl.get_config()["probe"]["answer"] == 1
    cl.CONFIG_FILE.write_text("probe:\n  answer: 2\n", encoding="utf-8")
    assert cl.get_config()["probe"]["answer"] == 1          # 缓存生效
    assert cl.reload_config()["probe"]["answer"] == 2       # 强制重读


# ==================== 真实 config.yaml 的 app_info 完整性 ====================
@pytest.fixture(scope="module")
def real_app_info():
    cl.get_config.cache_clear()
    cfg = cl.get_config()
    cl.get_config.cache_clear()
    assert "app_info" in cfg, "config.yaml 必须保留 app_info 段（窗口标题/日志/说明书/exe 名的唯一来源）"
    return cfg["app_info"]


def test_app_info_has_all_required_keys(real_app_info):
    for key in APP_INFO_KEYS:
        assert key in real_app_info, "app_info 缺少键：" + key


def test_app_info_text_keys_are_non_empty_strings(real_app_info):
    for key in TEXT_KEYS:
        assert isinstance(real_app_info[key], str) and real_app_info[key].strip(), "app_info." + key + " 不能为空"


def test_app_info_version_looks_like_a_version(real_app_info):
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(real_app_info["version"]).strip())


def test_app_info_log_max_mb_is_positive_int(real_app_info):
    value = int(real_app_info["log_max_mb"])
    assert 1 <= value <= 100


def test_exe_name_is_filesystem_safe(real_app_info):
    """exe 主名会直接进 PyInstaller --name 和文件名，不能含 Windows 非法字符。"""
    assert not re.search(r'[<>:"/\\|?*]', str(real_app_info["exe_name"]))


def test_title_template_only_uses_supported_placeholders(real_app_info):
    fields = {f[1] for f in Formatter().parse(str(real_app_info["title_template"])) if f[1]}
    assert fields <= {"name", "version", "round_label", "mode"}


def test_locations_template_only_uses_supported_placeholders(real_app_info):
    fields = {f[1] for f in Formatter().parse(str(real_app_info["locations_template"])) if f[1]}
    assert fields <= {"config", "data", "log", "manual"}


def test_manual_and_icon_actually_ship_with_the_software(real_app_info):
    assert (cl.APP_ROOT / "docs" / str(real_app_info["manual_file"])).is_file()
    assert (cl.APP_ROOT / str(real_app_info["icon_file"])).is_file()


def test_templates_db_path_shape_matches_ui_expectation(real_app_info):
    """①页底部提示取 storage.templates_db_path 的父目录当"数据目录"，这里防止该键被改成绝对路径或去掉目录前缀。"""
    raw = str(cl.get_config()["storage"]["templates_db_path"])
    assert raw.strip()
    assert not Path(raw).is_absolute(), "templates_db_path 必须是相对路径，否则打包后数据会散落到固定盘符"
    assert Path(raw).parent.name, "templates_db_path 需要带目录前缀（如 data/xxx.db）"


def test_app_info_tab_titles_has_six_ordered_names():
    """页签名称进 config 后，必须守住「6 条、按 ①–⑥ 顺序、都不为空」，
    否则界面会退回内置兜底名，用户改的配置看着像没生效。"""
    titles = cl.get_config()["app_info"]["tab_titles"]
    assert isinstance(titles, list) and len(titles) == 6
    marks = "①②③④⑤⑥"
    for i, name in enumerate(titles):
        assert isinstance(name, str) and name.strip(), "第 %d 个页签名为空" % (i + 1)
        assert name.strip().startswith(marks[i]), "第 %d 个页签应以 %s 开头，实际：%s" % (i + 1, marks[i], name)
