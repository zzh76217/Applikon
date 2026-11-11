# -*- coding: utf-8 -*-
"""配方存取测试（第三轮）：保存/列表/调用/删除 + 非法名防护。全部写进 tmp_path，不碰真实 data/。"""
import json

import pytest

from cell_planner.core import recipe_store

PARAMS = {
    "cell_line": "CHO-DG44",
    "v_work": 2000.0,
    "cd_seed": 3.0,
    "cd_inoc": 0.4,
    "expr_check": False,
}


class TestRoundTrip:
    def test_save_list_load_delete(self, tmp_path):
        assert recipe_store.list_recipes(directory=tmp_path) == []
        path = recipe_store.save_recipe("CHO 默认配方", PARAMS, directory=tmp_path)
        assert path.is_file()
        assert recipe_store.list_recipes(directory=tmp_path) == ["CHO 默认配方"]
        loaded = recipe_store.load_recipe("CHO 默认配方", directory=tmp_path)
        assert loaded == PARAMS
        recipe_store.delete_recipe("CHO 默认配方", directory=tmp_path)
        assert recipe_store.list_recipes(directory=tmp_path) == []

    def test_save_overwrites_same_name(self, tmp_path):
        recipe_store.save_recipe("A 配方", dict(PARAMS, v_work=2000.0), directory=tmp_path)
        recipe_store.save_recipe("A 配方", dict(PARAMS, v_work=1000.0), directory=tmp_path)
        assert recipe_store.list_recipes(directory=tmp_path) == ["A 配方"]
        assert recipe_store.load_recipe("A 配方", directory=tmp_path)["v_work"] == 1000.0

    def test_file_is_readable_json_with_metadata(self, tmp_path):
        path = recipe_store.save_recipe("留档测试", PARAMS, directory=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["配方"] == "留档测试"
        assert "保存时间" in data and "版本" in data
        assert data["参数"]["cell_line"] == "CHO-DG44"


class TestGuards:
    @pytest.mark.parametrize("bad_name", ["", "   ", "a/b", "a\\b", 'a"b', "a?b", "a*b", ".", ".."])
    def test_invalid_names_rejected_in_chinese(self, tmp_path, bad_name):
        with pytest.raises(ValueError, match="配方名称"):
            recipe_store.save_recipe(bad_name, PARAMS, directory=tmp_path)

    def test_load_missing_recipe_raises(self, tmp_path):
        with pytest.raises(ValueError, match="找不到"):
            recipe_store.load_recipe("不存在的配方", directory=tmp_path)

    def test_delete_missing_recipe_raises(self, tmp_path):
        with pytest.raises(ValueError, match="找不到"):
            recipe_store.delete_recipe("不存在的配方", directory=tmp_path)

    def test_corrupted_file_raises(self, tmp_path):
        (tmp_path / "坏配方.json").write_text("{ 这不是合法 JSON", encoding="utf-8")
        with pytest.raises(ValueError, match="损坏"):
            recipe_store.load_recipe("坏配方", directory=tmp_path)
