# -*- coding: utf-8 -*-
"""第六轮交付完整性测试：中文说明书、打包脚本、仓库卫生。

本文件只回答"交付物齐不齐、说没说清、有没有混进不该混的东西"，
不重复校验工艺数值（那些在 tests/test_validators.py、test_formulas.py 里）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# config.yaml 顶层段（第 1–5 轮建立 + 第六轮新增 app_info）。
# 第五轮曾发生"插新键时误删段头"的事故，这里用清单守住，任何一段丢失即测试失败。
REQUIRED_TOP_LEVEL_SECTIONS = [
    "hardware", "process_defaults", "liquid_additives", "mixing_physics",
    "density_input", "alkali_pump", "sampling", "do_alarm", "metabolite_limits",
    "harvest_hint", "csv_import", "setup_sheet_export", "storage", "recipes",
    "total_cells", "agitation_start_suggestion", "setup_sheet_strict", "ui_defaults",
    "column_mapping", "unit_constants", "analysis", "template_library",
    "simulation", "sop", "app_info",
]

# 模拟数据唯一允许的存放处（答复#8：文件名必须带 SIMULATED，且不得混入交付物）
SIMULATED_ALLOWED_DIRS = (os.path.join("data", "simulated"),)
SKIP_SCAN_DIRS = {".git", "build", "dist", "__pycache__", ".pytest_cache", ".venv", "venv"}


def _manual_text() -> str:
    return (ROOT / "docs" / "使用说明.txt").read_text(encoding="utf-8")


# ==================== config 结构完整性 ====================
def test_all_top_level_config_sections_survive():
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_TOP_LEVEL_SECTIONS if key not in cfg]
    assert not missing, "config.yaml 丢失了这些顶层段：" + "、".join(missing)


def test_config_top_level_sections_not_more_than_expected():
    """顶层段只增不减：新增段要同步登记进本清单，防止误删无人察觉。"""
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    assert set(cfg) == set(REQUIRED_TOP_LEVEL_SECTIONS)


# ==================== 中文说明书 ====================
def test_manual_file_exists_and_is_long_enough():
    text = _manual_text()
    assert len(text) > 8000, "说明书内容过少，不像给零代码用户看的手册"
    assert len(text.splitlines()) > 150


def test_manual_has_at_least_ten_sections():
    heads = re.findall(r"^第 \d+ 节　.+.*$", _manual_text(), flags=re.M)
    assert len(heads) >= 10, "说明书分节不足 10 节，实际：" + str(len(heads))


def test_manual_covers_all_eighteen_validation_rules():
    text = _manual_text()
    missing = ["R%02d" % i for i in range(1, 19) if ("R%02d" % i) not in text]
    assert not missing, "说明书未逐条讲到的校验规则：" + "、".join(missing)


def test_manual_covers_all_six_pages():
    text = _manual_text()
    missing = [mark for mark in "①②③④⑤⑥" if mark not in text]
    assert not missing, "说明书未覆盖的界面页签：" + "、".join(missing)


def test_manual_keeps_manual_review_disclaimer():
    """AGENTS.md 硬约束 6：结果仅供规划参考，必须写明需人工复核。"""
    assert "人工复核" in _manual_text()


def test_manual_says_the_software_does_not_control_hardware():
    text = _manual_text()
    assert "my-Control" in text
    assert "不连接" in text and "不联网" in text


def test_manual_explains_missing_impeller_diameter_warning():
    """D 仍为 null（用户决定），说明书必须解释这条黄色警告的来历与补法。"""
    text = _manual_text()
    assert "叶轮直径" in text and "比功率" in text


def test_manual_tells_where_files_live():
    text = _manual_text()
    assert "config.yaml" in text and "logs" in text


# ==================== 仓库卫生 ====================
def test_simulated_data_only_in_designated_folder():
    """带 SIMULATED 标记的数据文件只允许待在 data/simulated/（答复#8 的硬要求）。"""
    offenders = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for name in filenames:
            if "SIMULATED" not in name:
                continue
            rel = str(Path(dirpath, name).relative_to(ROOT))
            if not any(rel.startswith(allowed) for allowed in SIMULATED_ALLOWED_DIRS):
                offenders.append(rel)
    assert not offenders, "模拟数据混进了交付仓库：" + "、".join(offenders)


def test_simulated_files_are_named_as_simulated():
    folder = ROOT / "data" / "simulated"
    if not folder.is_dir():
        pytest.skip("本机尚未生成演示 CSV，不算缺陷")
    for csv in folder.glob("*.csv"):
        assert "SIMULATED" in csv.name


def test_no_leftover_temp_scripts_in_repo_root():
    leftovers = [p.name for p in ROOT.glob("*.py") if p.name.startswith("_")]
    assert not leftovers, "仓库根目录残留临时脚本：" + "、".join(leftovers)


def test_gitignore_keeps_build_output_and_db_out_of_repo():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for frag in ("build/", "dist/", "*.spec", "data/simulated/", "data/*.db", "__pycache__/"):
        assert frag in text, ".gitignore 缺少对 %s 的忽略" % frag


# ==================== 打包脚本自检 ====================
@pytest.fixture(scope="module")
def build_script_text():
    return (ROOT / "tools" / "build_exe.py").read_text(encoding="utf-8")


def test_build_script_flags(build_script_text):
    for frag, why in (("--windowed", "不弹黑色控制台窗口"),
                      ("--onefile", "单文件分发"),
                      ("--noconfirm", "重复构建不交互"),
                      ("run.py", "入口脚本"),
                      ("config.yaml", "默认配置随包"),
                      ("SIMULATED", "禁止模拟数据混入交付")):
        assert frag in build_script_text, "打包脚本缺少 %s（%s）" % (frag, why)


def test_build_script_excludes_unused_heavy_modules(build_script_text):
    """代码里从未 import pandas/scipy，打包时必须排除，否则 exe 体积白涨一百多 MB。"""
    for mod in ("pandas", "scipy", "IPython", "tkinter"):
        assert '"%s"' % mod in build_script_text, "打包排除清单缺少 " + mod


def test_excluded_modules_really_are_not_imported():
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for mod in ("pandas", "scipy", "IPython", "tkinter"):
            if re.search(r"^\s*(import|from)\s+" + mod + r"\b", text, flags=re.M):
                offenders.append("%s 用了 %s" % (path.name, mod))
    assert not offenders, "排除清单与代码不一致：" + "、".join(offenders)


def test_requirements_declares_pyinstaller():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^PyInstaller>=\d", text, flags=re.M), "requirements.txt 应放开 PyInstaller 依赖"
    assert not re.search(r"^pandas>=|^scipy>=", text, flags=re.M), "已确认未使用的依赖不应再列进 requirements.txt"