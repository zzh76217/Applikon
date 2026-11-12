# -*- coding: utf-8 -*-
r"""第六轮：把软件打包成 Windows 桌面版（.exe）。

用法（在工程根目录）：
    python tools/build_exe.py            # 单文件 onefile（推荐：拷 U 盘、双击即用）
    python tools/build_exe.py --onedir   # 文件夹版（启动更快、便于查看依赖）

产物：
    dist\细胞培养接种与批次配置规划软件.exe        ← 双击即用，目标电脑不需要装 Python
    dist\config\config.yaml                        ← 出厂默认参数（可直接编辑，改完重启软件生效）
    dist\使用说明.txt                               ← 中文说明书
    dist\data\README.txt                           ← 数据目录说明
    dist\本版本信息.txt                             ← 版本号、大小、SHA256、构建时间
    dist\<同名>.zip                                ← 上面几件一起打包，便于拷到实验电脑

设计要点（为什么这样打）：
1) 配置文件用 --add-data 打进 exe，同时程序首次启动会把默认配置"释放"到 exe 同目录的
   config 文件夹，用户改那一份即可，不必重新打包（见 core/config_loader.py）。
2) 所有可写文件（模板库、列名映射、配方、开机配置单、日志）都落在 exe 所在目录，
   而不是 onefile 的临时解包目录——临时目录一关程序就没了，存东西进去等于丢数据。
3) 严禁把模拟数据（文件名含 SIMULATED）放进 dist，脚本末尾会主动检查并报错。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# 这些库本机装了但软件根本没用（代码里只 import PySide6 / matplotlib / yaml / sqlite3），
# 排除掉可以把 exe 从几百 MB 压到一百多 MB。numpy 必须留着，matplotlib 依赖它。
EXCLUDES = [
    "pandas", "scipy", "IPython", "tkinter", "pytest", "_pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtNetwork", "PySide6.QtPositioning",
    "PySide6.QtRemoteObjects", "PySide6.QtQuickWidgets", "PySide6.QtVirtualKeyboard",
    "PySide6.QtSensors", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSerialPort",
    "PySide6.QtTest", "PySide6.QtTextToSpeech",
]


def _run(cmd, cwd=None) -> None:
    print("$ " + " ".join(str(c) for c in cmd))
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd or ROOT))
    if proc.returncode != 0:
        raise SystemExit("命令失败，退出码 %d：%s" % (proc.returncode, cmd[0]))


def build(onefile: bool) -> int:
    import yaml  # noqa: WPS433  只为读配置，不引入新依赖
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    info = cfg.get("app_info") or {}
    exe_name = str(info.get("exe_name") or "细胞培养接种与批次配置规划软件")
    version = str(info.get("version") or "0.0.0")
    manual_name = str(info.get("manual_file") or "使用说明.txt")
    icon_rel = str(info.get("icon_file") or "")
    icon_path = (ROOT / icon_rel) if icon_rel else None

    if not (ROOT / "run.py").is_file():
        raise SystemExit("找不到入口 run.py，无法打包。")
    if not (SRC / "cell_planner").is_dir():
        raise SystemExit("找不到 src\\cell_planner 包，无法打包。")

    # 1) 清干净上一次的产物
    for folder in (BUILD, DIST):
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)

    # 2) 调 PyInstaller（命令行方式，不往仓库里留 .spec 文件）
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",                       # 不弹黑色控制台窗口
        "--name", exe_name,
        "--paths", str(SRC),
        str(ROOT / "run.py"),
    ]
    args += ["--onefile"] if onefile else ["--onedir"]
    args += ["--add-data", "%s;config" % (ROOT / "config" / "config.yaml")]
    if icon_path and icon_path.is_file():
        args += ["--icon", str(icon_path)]
        args += ["--add-data", "%s;assets" % icon_path]
    else:
        print("提示：没有 %s，本次生成的 exe 用系统默认图标。" % icon_path)
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    args += ["--hidden-import", "matplotlib.backends.backend_agg"]

    _run(args)

    # 3) 找到 PyInstaller 的产物
    if onefile:
        produced = DIST / (exe_name + ".exe")
    else:
        produced = DIST / exe_name
    if not produced.exists():
        raise SystemExit("打包结束但找不到产物：%s" % produced)

    # 4) 组装发布内容：说明书、默认配置、数据目录说明、版本信息
    (DIST / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "config" / "config.yaml", DIST / "config" / "config.yaml")
    manual_src = ROOT / "docs" / manual_name
    if not manual_src.is_file():
        raise SystemExit("缺少中文说明书：%s（第六轮交付物，不能没有）" % manual_src)
    shutil.copyfile(manual_src, DIST / manual_name)
    if (ROOT / "data" / "README.txt").is_file():
        (DIST / "data").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data" / "README.txt", DIST / "data" / "README.txt")

    sha = hashlib.sha256(produced.read_bytes()).hexdigest() if produced.is_file() else "（文件夹版无单一文件）"
    size_mb = ("%.1f MB" % (produced.stat().st_size / 1048576.0)) if produced.is_file() else "（多文件）"
    pyi = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                         capture_output=True, text=True).stdout.strip()
    info_lines = [
        "细胞培养接种与批次配置规划软件 — 本次构建信息",
        "=" * 60,
        "版本号：%s" % version,
        "产物：%s（%s，%s）" % (produced.name, size_mb, "onefile 单文件" if onefile else "onedir 文件夹"),
        "构建时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "SHA256：%s" % sha,
        "Python：%s" % sys.version.split()[0],
        "PyInstaller：%s" % pyi,
        "",
        "怎么用：把整个 dist 文件夹拷到实验电脑任意位置（建议 D 盘新建文件夹，"
        "不要放 C:\\Program Files，也不要放桌面以外的只读位置），双击 exe 即可。",
        "改参数：编辑 exe 同目录的 config\\config.yaml，保存后重启软件生效。",
        "出问题：把 logs\\软件运行日志.txt 和 使用说明.txt 一起发给开发者。",
    ]
    (DIST / "本版本信息.txt").write_text("\n".join(info_lines) + "\n", encoding="utf-8-sig")

    # 5) 安全检查：模拟数据绝不允许混进交付物（用户答复#8 的硬要求）
    leaked = [p.name for p in DIST.rglob("*") if p.is_file() and "SIMULATED" in p.name.upper()]
    if leaked:
        raise SystemExit("严重：交付目录里混入了模拟数据，必须删除：%s" % ", ".join(leaked))

    # 6) 顺手压一个 zip，方便拷给实验室电脑
    zip_file = DIST / ("%s_V%s_Win64.zip" % (exe_name, version))
    # 逐个写入而不是 shutil.make_archive：避免把 zip 自己打进去
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(DIST.iterdir()):
            if item.name == zip_file.name or item.name == "build":
                continue
            if item.is_file():
                zf.write(item, item.name)
            elif item.name in ("config", "data"):
                for sub in sorted(item.rglob("*")):
                    if sub.is_file():
                        zf.write(sub, sub.relative_to(DIST).as_posix())
            elif item.is_dir():                       # onedir 模式：整个程序文件夹
                for sub in sorted(item.rglob("*")):
                    if sub.is_file():
                        zf.write(sub, sub.relative_to(DIST).as_posix())
    print("\n=== 打包完成 ===")
    print("产物目录：%s" % DIST)
    for item in sorted(DIST.iterdir()):
        if item.is_file():
            print("  %10.1f MB  %s" % (item.stat().st_size / 1048576.0, item.name))
        else:
            print("  <目录>      %s" % item.name)
    print("zip：%s（%.1f MB）" % (zip_file, zip_file.stat().st_size / 1048576.0))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打包 Windows 桌面版 .exe")
    ap.add_argument("--onedir", action="store_true", help="生成文件夹版（默认单文件 onefile）")
    ns = ap.parse_args(argv)
    return build(onefile=not ns.onedir)


if __name__ == "__main__":
    raise SystemExit(main())