# -*- coding: utf-8 -*-
"""config.yaml 原位回写工具测试（第三轮）：改值必须保留注释与其余行；异常必须拒写。"""
import yaml

from cell_planner.core.config_writer import set_yaml_values, update_config_file

SAMPLE = """# 顶部注释不能丢
hardware:
  min_working_volume_ml: 600        # 规则 R01 下限
  mfc_max_ml_min:
    air: 1500
    co2: 800
process_defaults:
  temp_growth_c:
    set: 37.0
    min: 36.5
    max: 37.0
"""


def test_scalar_update_keeps_comments():
    out = set_yaml_values(SAMPLE, {("hardware", "min_working_volume_ml"): 800})
    assert "min_working_volume_ml: 800" in out
    assert "# 规则 R01 下限" in out
    assert "# 顶部注释不能丢" in out
    data = yaml.safe_load(out)
    assert data["hardware"]["min_working_volume_ml"] == 800
    assert data["hardware"]["mfc_max_ml_min"]["co2"] == 800      # 兄弟键不受影响
    assert data["process_defaults"]["temp_growth_c"]["max"] == 37.0


def test_nested_paths_and_types():
    out = set_yaml_values(SAMPLE, {
        ("process_defaults", "temp_growth_c", "set"): 36.8,
        ("hardware", "mfc_max_ml_min", "air"): 2000,
    })
    data = yaml.safe_load(out)
    assert data["process_defaults"]["temp_growth_c"]["set"] == 36.8
    assert data["hardware"]["mfc_max_ml_min"]["air"] == 2000


def test_identical_when_no_updates():
    assert set_yaml_values(SAMPLE, {}) == SAMPLE


def test_unknown_path_refuses_write():
    try:
        set_yaml_values(SAMPLE, {("hardware", "不存在的键"): 1})
    except ValueError as exc:
        assert "找不到" in str(exc)
    else:
        raise AssertionError("未知路径必须抛中文 ValueError 拒写")


def test_flow_style_refused():
    text = "metabolite_limits:\n  glucose_g_l: { yellow_below: 2.0 }\n"
    try:
        set_yaml_values(text, {("metabolite_limits", "glucose_g_l"): 1.0})
    except ValueError as exc:
        assert "行内写法" in str(exc)
    else:
        raise AssertionError("行内映射必须拒写而不是损坏文件")


def test_update_config_file_roundtrip(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(SAMPLE, encoding="utf-8")
    update_config_file({("hardware", "min_working_volume_ml"): 700}, config_path=cfg_file)
    assert yaml.safe_load(cfg_file.read_text(encoding="utf-8"))["hardware"]["min_working_volume_ml"] == 700
    assert "# 规则 R01 下限" in cfg_file.read_text(encoding="utf-8")
    assert (tmp_path / "config.yaml.bak").is_file()   # 保存前自动备份


def test_real_project_config_still_parses():
    """回归护栏：真实 config.yaml 必须保持块状标量写法，能被 safe_load 且关键键存在。"""
    from cell_planner.core.config_loader import CONFIG_FILE
    data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    for path in (("hardware", "min_working_volume_ml"),
                 ("process_defaults", "temp_growth_c", "set"),
                 ("liquid_additives", "base_fraction_of_working", "default"),
                 ("recipes", "dir"),
                 ("ui_defaults", "sampling_total_ml")):
        node = data
        for key in path:
            node = node[key]
