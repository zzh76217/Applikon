# 细胞培养接种与批次配置规划软件

为不懂代码的生物科研人员开发的单机软件：开机前计算接种量/体积/气体设定并校验硬件安全，
关机后做生长曲线与批次分析。唯一事实来源：`requirements.md`；协作约束：`AGENTS.md`。

## 当前状态
- [x] 第一轮：需求理解、技术选型（PySide6）、项目骨架、业务参数确认 ← 已完成（2026-11-11）
- [x] 第二轮（第一步）：安装步骤已交付；用户已装好 Python 3.12.10 + git 2.50.1（2026-11-11）
- [x] 第二轮（业务）：最小单页版已交付——三区界面 + 公式1–5 + R01–R13；用户已验收通过（2026-11-11，回复"无误"）
- [x] 第三轮：R14–R18 全部落地（校验器 18/18）+ 用户新增需求：②硬件配置页（可改体积上下限/MFC量程/推荐默认值，写回 config.yaml 保留注释）、开机配置单一键导出 CSV（utf-8-sig）+ 一键复制、参数配方保存/调用（data/recipes JSON）；pytest 79 passed；待用户验收（见 docs/第三轮验收说明.md）
- [x] 第四轮（2026-11-11，按用户指令 = 提示词文档第四轮"校验完善与防呆"）：补充公式展示（N_total、搅拌启动建议转速、γ≈k×N 剪切估算）、k/D 缺参数黄色防御、红色错误一律禁止导出配置单、非法输入全链路不崩溃、提示词文档 2.0 L 算例单元测试；pytest 113 passed；待用户验收（见 docs/第四轮验收说明.md）
- [x] 第五轮（2026-11-12，用户指令"已关闭，进行第五轮"）：模块 3 离线分析（③页 + CSV 解析器 + ④列名映射页）、模块 4 模板库与多批次对比（⑤页，SQLite）、模块 5 SOP 防呆引导（⑥页，4 阶段 23 项）；界面扩到 6 页；顺手修掉 6 个会让软件起不来/用不了的缺陷；pytest 266 passed；待用户验收（见 docs/第五轮验收说明.md）
- [x] 第六轮（2026-11-12，用户指令"1234 都按现有设定，确认进入第六轮"）：PyInstaller 打包成双击可用的单文件 .exe（72.6 MB，onefile，含自动释放出厂配置、运行日志、程序图标）+ 中文使用说明.txt；顺手修掉 3 个真机才暴露的缺陷（windowed 下 stderr=None 崩溃、启动失败无弹窗、1280x752 小屏窗口被撑出屏幕）；pytest 360 passed；待用户验收（见 docs/第六轮验收说明.md）
- [x] 第七轮（2026-11-20，用户指令：主界面重构为三大板块 + 整体视觉美化，零逻辑改动）：外层只剩 3 个大标签（配置与校验 / 分析与对比 / SOP 引导），原 6 页降为板块内子标签；新增 ui/theme.py 与 ui/icons.py（配色、边距、字号、图标全部读 config.app_info.theme）；③ 离线分析子页顶部加映射状态提示与「去「列名映射」」一键跳转；pytest 404 passed（新增 38 条界面结构测试，一条未删）；待用户验收（见 docs/第七轮验收说明.md）
- [x] 第七轮补充（2026-11-20，用户答复「1通过，2可以删除，4要word说明书」）：第七轮验收**通过**；删除根目录旧副本 txt；新增 Word 版中文说明书 `docs\使用说明.docx`（由 `tools\build_docx_manual.py` 从纯文本说明书排版生成，只用标准库，逐行核对不通过就拒绝出货），并随 exe 一起进交付包；pytest 423 passed（407 + 新增 16）；版本仍 1.1.0；**等你确认后才会进下一轮功能开发**（见 docs/第七轮验收说明.md 第 10 节）
- [ ] 待用户提供真实 my-Control 导出 CSV 后，在④列名映射页对齐列名并做一次真实数据回归；叶轮直径 D 与叶轮常数 k 待查设备铭牌后填入 config（现仍为 null，走黄色警告）

## 目录结构
```
D:\Applikon\
├── requirements.md            # 需求文档（唯一事实来源）
├── AGENTS.md                  # 协作规范
├── README.md                  # 本文件
├── requirements.txt           # Python 依赖清单（第二轮起安装；第六轮放开 PyInstaller，移除未使用的 pandas/scipy）
├── run.py                     # 源码版入口（python run.py）；打包时作为 PyInstaller 主脚本
├── 启动软件.bat               # 源码版双击启动脚本
├── assets/
│   └── app.ico                # 程序图标（tools/make_icon.py 生成，随 exe 内嵌）
├── config/
│   └── config.yaml            # 全部工艺参数与硬件上下限（严禁代码硬编码）
├── src/
│   └── cell_planner/
│       ├── core/              # 计算公式、18 条校验、离线分析、列名映射、模板库、SOP
│       ├── ui/                # PySide6 界面：3 大板块 + 6 个子页 + theme/icons（只管外观，不碰算法）
│       └── io_/               # CSV 导入、配置单导出、模板库读写
├── tests/                     # pytest 单元测试（423 条：第三节公式 + 第五节 18 条规则 + 模块 3/4/5 + 第六轮打包/诊断/整窗冒烟 + 第七轮板块结构与 Word 说明书）
├── tools/                     # 辅助脚本：make_icon.py 生成图标、build_exe.py 打包 exe、build_docx_manual.py 从使用说明.txt 生成 Word 版说明书、make_simulated_csv.py 生成带 SIMULATED 标记的演示 CSV（均不参与交付）
├── data/                      # 配方（recipes/）、模板库与用户导入文件存放处（运行时生成，不入 git）
├── logs/                      # 运行日志 软件运行日志.txt（运行时生成，不入 git）
├── build/  dist/              # 打包中间产物与成品（不入 git，dist 里的 zip 就是发给实验电脑的交付包）
└── docs/                      # 决策记录、各轮验收说明、使用说明.txt（唯一事实来源）与使用说明.docx（Word 版，随交付包一起发）
```

## 第一轮决策记录（2026-11-11，用户答复已全部写入 config.yaml）

| 编号 | 决策 | config 落点 |
|------|------|-------------|
| 选型 | PySide6（弃 Streamlit），理由见 docs/技术选型决议.md | — |
| #1 | 碱液（7.5% NaHCO3）默认预留工作体积 2%、消泡剂 0.1%，界面可改、不硬编码 | liquid_additives |
| #2 | Np=0.35；R06 红线由 ε≤1 收紧为 **ε>0.1 W/kg 报红禁止**；推荐区 0.02–0.04；**ε>0.05 报黄**（依据 CHO 剪切应激与工业 P/V 22–35 W/m3） | mixing_physics |
| #3 | 公式 8 γ≈k×N 本轮暂缓：界面不展示、代码留接口，不算违约；shear_gamma_enabled=false | mixing_physics |
| #4 | ρ 按 1000 kg/m3 近似，作为 config 参数 | mixing_physics.broth_density_kg_m3 |
| #5 | 界面单位统一 ×10⁶ cells/mL。CD_seed=种子罐收获浓度（常见 1–5，>10 报红）；"接种后反应器内起始密度"合理区间 0.5–5.0、输入上限 20 并报黄。两个字段的绑定归属第二轮开工时再核对一次 | density_input |
| #6 | 碱泵系数 = 每分钟每升培养体积允许补碱 mL 数，默认建议 0.05 mL/min/L，标注"仅供参考、以 my-Control 实际 PID 整定为准" | alkali_pump |
| #7 | DO 报警调灵敏：低于设定点 10 个百分点持续 15 分钟报黄、30 分钟报红；绝对红线 DO<20% 立即报红；设定点默认 50%（最低 40%） | do_alarm / process_defaults.do_percent |
| #8 | 暂无法提供真实 CSV：先按通用格式解析（UTF-8、逗号、首行列名、ISO 时间），第四轮做"列名映射配置页"；模拟 CSV 脚本输出必须显著标注 SIMULATED 且不混入交付物；等用户上机导出真实文件后替换 | csv_import |
| #9 | 不做 PDF 导出（省掉 reportlab），只做一键复制 + 导出 .txt | setup_sheet_export |
| #10 | 葡萄糖：黄 <2 g/L（提示补糖）、红 <0.5 g/L（耗竭）、补糖目标 2–4 g/L；乳酸：黄 >2、红 >4 g/L；界面同显 g/L 与 mmol/L（MW 90.08） | metabolite_limits |
| #11 | 模板库用 SQLite（标准库 sqlite3），库文件放 data/templates.db | storage |

### 遗留待确认（不阻塞第二轮）
1. **Marine 叶轮直径 D（米）**：用户决定暂保留 null。防御性处理（2026-11-11 定案）：D 为 null 时不计算 ε，R06 不判红绿，界面与日志输出黄色警告"⚠️ 缺少叶轮直径参数，无法计算剪切力，请后续在配置中补充"，不得报错崩溃；将来在 config 补 D 即自动启用 ε 计算。
2. ~~答复 #5 区间绑定~~ 第三轮已定案：CD_seed>10/≤CD_inoc → R15 红；CD_inoc 超出 0.5–5.0 → R15 黄（0.3–0.5 推荐范围例外通过）；输入上限 20 由界面数字框封顶。（2026-11-11）
3. my-Control 真实导出 CSV（等用户上机后提供，届时重跑第四轮解析相关测试）。

### 第二轮开工前置条件
本机未安装 Python 与 git；第二轮第一步交付傻瓜式安装步骤，装完再写业务代码。

## 运行提示
所有计算结果仅供规划参考，正式上机前必须由操作人员人工复核（requirements.md 第八节）。
## 第三轮决策记录（2026-11-11，按用户指令扩充范围）

| 决策 | 说明 |
|------|------|
| 范围扩充 | 用户在启动第三轮时新增：硬件配置页、开机配置单 CSV 导出、配方保存/调用 |
| 配方存储 | 轻量配方用 JSON 文件（data/recipes/*.json，可读可拷贝）；第五轮 SQLite 模板库职责不同（实验方案模板+批次对比），互不替代 |
| 配置回写 | 硬件配置页通过 config_writer 原位行级替换写回 config.yaml：保留全部注释、先备份 .bak、异常拒写不损坏文件；config 的 {set,min,max} 行内写法因此改为块状写法 |
| CSV 编码 | utf-8-sig（带 BOM），Excel/WPS 双击打开中文不乱码；答复 #9 的"复制+txt"升级为"复制+CSV"（用户点名要 CSV） |
| R16 常黄 | 曝气方式为界面强制提示，任何配置下均显示 🟡（属设计，需求第五节原文"界面强制提示"） |
| 默认值联动 | 硬件配置页保存后阈值即时生效；①页"恢复默认值"读取的是当前 config 而非程序启动时快照 |

## 第四轮决策记录（2026-11-11，用户指令："补齐 R14–R18 与剪切力估算、红黄绿三档、非法输入不崩溃、2.0 L 算例测试"）

| 事项 | 决策 | 落点 |
|------|------|------|
| 范围说明 | R14–R18 与红黄绿三档显示第三轮已交付（18/18）。本轮实际增量 = 剪切估算 + 补充公式 + 导出红线收紧 + 防崩溃强化 | — |
| γ 剪切估算 | 答复#3 的"暂缓"由本轮指令解除：shear_gamma_enabled=true。k 仍无参考值（impeller_constant_k: null），界面显示黄色警告"缺少叶轮常数 k…"而不是崩溃（与叶轮直径 D 缺参数同一防御模式）；用户日后在 config 填入 k 即自动显示 γ = k × (rpm÷60)，备注"经验估算，仅供相对比较" | mixing_physics / formulas.shear_gamma_per_s |
| N_total 单位笔误 | 提示词文档算例把 N_total 写成 "8.0 × 10⁶ cells"，属单位笔误：2000 mL × 0.4×10⁶ cells/mL = **800 ×10⁶ cells = 8.0×10⁸**。软件按物理正确值实现并以此为测试断言（界面/配置单显示 800 ×10⁶ cells，括注 8.0×10⁸）；请用户修改文档 | total_cells / formulas.total_cells_millions |
| 搅拌启动建议 | 按 docx 公式6 分段（≤1.0 L→80；1.0–1.8 L→100；>1.8 L→120 rpm），分段表放 config（bands_ml），仅"建议"，最终仍受 R05 校验 | agitation_start_suggestion |
| 红色禁止导出 | docx §五(二)"红色必须阻止生成配置单"：block_export_on_error=true 时，只要存在 🔴，导出 CSV 与一键复制均被拒绝并列出错误规则；第三轮"确认后可导出"的旧行为仅在该开关为 false 时保留 | setup_sheet_strict |
| 防崩溃强化 | ① R06：D 已填但工作体积 ≤0 → 🔴（杜绝除零）；D ≤0 → 🟡；② 补充公式展示与配置单行均包 try/except，配置被手改坏只出警告行；③ 全 0/负数/超大输入下 run_validation 恒返回 18 条结果（新增测试覆盖） | validators / main_window / sheet_export |
| 规则编号差异 | 提示词文档 §六 的 18 条与 requirements.md 第五节 18 条**编号和内容都不同**（docx 另有：总气体≤排气能力、DO-搅拌冲突、pH-CO2 冲突、温度红线 30–40/≥37.5 提示、预留≤10%、每日取样≤5% 等）。按 AGENTS.md，requirements.md 为唯一事实来源，本轮未把 docx 独有规则并入；是否替换/追加待用户拍板（已写进验收说明文末） | — |
| 测试 | 期望值全部取自 requirements.md 3.3 与提示词文档 §四(四) 算例及 config 推导，无自编工艺数值；113 passed（第三轮 79 → 本轮 +34） | tests/ |

## 勘误登记（2026-11-11，第四轮后由用户指令追加）

| 项目 | 内容 |
|------|------|
| 日期 | 2026-11-11 |
| 目标文件 | 细胞培养接种与批次配置规划软件_Codex开发提示词.docx（word/document.xml，第三节算例段） |
| 原值 | N_total = 8.0 × 10⁶ cells |
| 新值 | N_total = 8.0 × 10⁸ cells（= 800 × 10⁶ cells） |
| 原因 | 单位笔误：2000 mL × 0.4 × 10⁶ cells/mL = 800 × 10⁶ cells = 8.0 × 10⁸ cells，原文少写两个数量级 |
| 改动处数 | 全文检索后确认仅 1 处（表格及其余 XML 无命中）；N_total = V_work × CD_inoc 无单位不改；其余 × 10⁶ 为浓度单位正确不改 |
| 执行方式 | run 级文本替换（要求①）：逐条目校验确认 15 个 zip 条目中仅 word/document.xml 字节变化，其余样式/字体/设置条目原样；替换后回代自检可逐字节还原原文 |
| 备份 | 细胞培养接种与批次配置规划软件_Codex开发提示词_备份_原笔误.docx（写回前生成，与原文件 SHA-256 一致，要求②） |
| 代码与测试 | 未改动任何代码与测试期望值，维持 800 × 10⁶ cells 的物理正确实现（要求③） |
| 备注 | 写回曾因 Word 占用被安全拒绝（脚本检测到占用即放弃写入），用户关闭 Word 后重试成功；临时脚本已删除 |

## 第五轮决策记录（2026-11-12）

| 项目 | 决策 | 依据 / 备注 |
|------|------|-------------|
| 本轮范围 | ③离线分析 + ④列名映射 + ⑤模板库与批次对比 + ⑥SOP 引导，界面由 2 页扩到 6 页 | 需求文档模块 3/4/5；打包留到第六轮 |
| ②页联动 | 硬件配置"保存并生效"后，③④⑤⑥ 页跟随刷新（量程、上限、默认值、SOP 条目、对比字段） | 保证"阈值只在 config"这条硬约束真的生效 |
| 缺陷修复 1 | `core/template_store.py` 三条建表 SQL 缺分号 → `executescript` 语法错，⑤页首次使用即失败 | 已补分号并加测试 |
| 缺陷修复 2 | `ui/common.py` 误用 `setEditBehavior()`（Qt 无此方法）→ 任何表格创建即 AttributeError | 改为 `setEditTriggers(QAbstractItemView.NoEditTriggers)` |
| 缺陷修复 3 | `ui/chart_view.py` 向 `QLabel.setAlignment()` / `QPixmap.scaled()` 传裸整数 | 改用 `Qt.AlignHCenter|Qt.AlignVCenter`、`Qt.KeepAspectRatio`、`Qt.SmoothTransformation` |
| 缺陷修复 4 | `ui/main_window.py` 缺 `main()` → `run.py` 与 `启动软件.bat` 必 ImportError | 已补 `main()` 与全局异常钩子（未捕获异常弹中文窗口，不闪退） |
| 缺陷修复 5 | `core/sop_checklist.py` 的 `_cfg()` 空值回退写反 → ②页改配置不反映到 SOP 页 | 改为仅在 `cfg is None` 时回退全局 |
| 模拟数据 | 生成器移入包内 `io_/simulator.py`，`tools/make_simulated_csv.py` 改为薄壳；输出目录 `data/simulated/` 已加入 `.gitignore` | 答复#8：必须显著标注 SIMULATED 且不得混入交付物 |
| 新增 config 键 | `analysis.report_title`、`analysis.report_export.csv_encoding`、`column_mapping.*`、`unit_constants.glucose_mw_g_mol=180.16`、`metabolite_limits.lactate_mw_g_mol=90.08`、`template_library.*`、`sop.*` | 全部阈值/字段/SOP 文字集中于此，代码零硬编码 |
| SOP 闸门默认值 | `sop.require_all_checked_for_export: false` —— 未勾满仍可导出确认单，但未勾条目逐条标"未确认"并弹窗提示 | 若你要"必须 23 项全勾"，把该值改 true 即可（无需改代码） |
| 图表方案 | matplotlib 仅用 Agg 后端出 PNG 字节交给 QLabel，失败降级为一行中文提示 | 不引入第二套 GUI 后端，不与 PySide6 抢事件循环；坐标轴用英文避免中文字形缺失 |
| 模板库 | SQLite（标准库 sqlite3），库文件 `data/templates.db`，首次使用自动建表，不入 git | 答复#11 |
| 批次对比 | 10 项指标（清单在 `template_library.compare_fields`），<2 个批次给中文提示不崩溃；SIMULATED 批次行标黄并附警示 | 答复#8 |
| 测试 | 新增 153 条（analysis 52 / csv_reader 40 / column_mapping 25 / sop 12 / template_store 12 / simulated 12），合计 266 passed | 期望值全部来自 requirements.md 第三节算例与 config.yaml；浮点比较用 `pytest.approx` |
| 冒烟 | 一次性离屏整窗冒烟脚本（6 页 + 关键动作）通过后已删除，未入库 | 与第二~四轮做法一致，避免仓库里留临时件 |
| 仍为 null 的参数 | `mixing_physics.impeller_diameter_m`、`impeller_constant_k` | ε 与 γ≈k×N 继续走"缺参数→黄色警告"（答复#2、#3），代码接口已留 |
| 缺陷修复 6 | `core/analysis.py` DO 断档判定写死 0.5 / 1.5 → 外移为 `config.do_alarm.gap_default_hours` / `gap_max_factor`，补 3 条测试；外移前后 ③ 页指标逐位一致 | 满足 AGENTS.md「严禁硬编码」 |
| 事故登记 | 给 config.yaml 插新键的临时脚本一度误删 `metabolite_limits:` 段头 → 按 `git show HEAD` 逐段比对恢复并回归测试，顶层段与子键零丢失 | 教训：改 config 必须带结构比对，不靠行号 |
| 新增依赖 | 无（第三方仍只有 PySide6 / PyYAML / pytest / matplotlib，见 requirements.txt） | — |

## 第六轮决策记录（2026-11-12）

| 项目 | 决策 | 依据 / 备注 |
|------|------|-------------|
| 打包方式 | PyInstaller **onefile 单文件**（72.6 MB），启动 4–7 秒 | 用户第 5 项拍板"1234 都按现有设定"，onefile 最傻瓜：拷一个 exe + config + 说明书即可；嫌启动慢可 `python tools/build_exe.py --onedir` 改文件夹版 |
| 配置/数据位置 | 打包版 APP_ROOT = **exe 所在目录**（不是临时解包目录 _MEIPASS） | 否则用户改的 config 会被每次启动的临时解包覆盖，②页"保存并生效"也白做 |
| 缺配置自愈 | exe 内嵌出厂 config；启动时若同目录 `config\config.yaml` 不存在则**自动释放一份**（实测释放后 SHA256 与工程默认一致）；释放失败（只读目录）退回内置副本继续运行；两者都没有才弹中文"找不到配置文件" | 用户误删 config 也能开机；已实测删除 config 目录后启动成功 |
| 运行日志 | `logs\软件运行日志.txt`，追加写、超过 5 MB 轮转为 `.old`；文件名/目录名/上限都在 config.app_info | 实验人员排障只需发这一个文件 |
| 踩坑 1 | `--windowed` 打包后 `sys.stdout/sys.stderr` 为 **None**，任何 `print`/`sys.stderr.write` 直接崩 | 新增 `core/diagnostics.py`：写日志前先判 None；日志设置读 config，读不到才用兜底文件名 |
| 踩坑 2 | 启动阶段异常原来只写 stderr → 用户看不到任何提示（双击"没反应"） | `main()` 补启动失败弹窗，并把日志路径写进弹窗文字；实测坏 config 会弹「软件启动失败」+ 生成中文堆栈日志 |
| 踩坑 3 | 真机 1280x752 可用区（3K 屏 225% 缩放）下窗口被撑到 1200x1009，底部按钮和第 6 页签跑到屏幕外 | 三处改动：① `_fit_to_screen()` 按 availableGeometry 收缩；② ② 硬件配置页整体装进 QScrollArea（原来单页 minimumSizeHint 高 918 px）；③ ① 页左侧参数表单也装进 QScrollArea（show 后 minimumSizeHint 高 742 px）+ 底部路径标签开启自动折行（原来一行长路径把最小宽顶到 926 px）。现在整窗 1200x728、最小 693x358，实测 FITS=True |
| 界面文案入 config | 新增 `app_info.tab_titles`（6 个页签名）与 `title_template`、`locations_template` 等 12 个键；代码里只留兜底默认 | AGENTS.md「严禁硬编码」延伸到界面文字；窄屏可自己改短页签名 |
| 图标 | `tools/make_icon.py` 用 QPainter 画烧瓶生成 `assets/app.ico`（7 个尺寸），随 exe 内嵌 | 曾踩 `os._exit` 提前退出、`QPolygonF` 点位错误两个坑，已修 |
| 依赖瘦身 | 打包排除 pandas / scipy / IPython / tkinter / pytest + 20+ 未用 Qt 模块；requirements.txt 移除 pandas、scipy（全项目确认无 import） | exe 从 ~110 MB 降到 72.6 MB |
| 交付包内容 | `dist\` = exe + `config\config.yaml` + `使用说明.txt` + `data\README.txt` + `本版本信息.txt`（版本号/SHA256/构建时间/用法四行）+ 同名 zip | 打包脚本内置 **SIMULATED 泄漏检查**：交付目录里出现任何含 SIMULATED 的文件即中止 |
| 中文使用说明 | `docs/使用说明.txt`（274 行 / 10 节：怎么打开、六页干什么、①页照着做、18 项校验颜色含义、③页分析、改配置、数据备份、常见问题 Q1–Q10、术语词典、责任声明） | 纯文本，U+3000 缩进，记事本即开；不做 PDF（答复#9） |
| 全新解压复验 + 说明书补注 | 从交付 zip 解压到临时目录 → 删 `config\`、`logs\` → 双击 exe：6.1 秒出窗口、config 自动释放且 SHA256 与工程默认一致、`data\templates.db` 自动新建、窗口 2728x1670 六页签全可见；据此在说明书第 7 节与 Q1 补两句（运行日志只在警告/报错时创建，平时没有该文件属正常），并重建 zip | exe 未重新编译，SHA256 不变 `003e5c3d…b9173`；复验细节见 `docs/第六轮验收说明.md` 第 4.4 节 |
| 测试 | 新增 94 条（app_info 21 / config_loader 26 / diagnostics 18 / 交付物结构 18 / 整窗冒烟 11），合计 **360 passed** | 期望值仍全部来自 requirements.md 第三节算例与 config.yaml；浮点比较用 pytest.approx |
| 新增依赖 | PyInstaller 6.22.3（仅开发机用于打包，运行期不需要） | 用户实验电脑无需装 Python |


## 第七轮决策记录（2026-11-20，主界面三大板块重构 + 视觉美化，零逻辑改动）

| 项目 | 决策 | 依据 / 备注 |
|------|------|-------------|
| 导航结构 | 外层 QTabWidget 只留 3 个大板块（配置与校验 / 分析与对比 / SOP 引导），原 6 页降为板块内子标签；板块②子页按使用顺序排为 ④列名映射 → ③离线分析 → ⑤模板库对比 | 用户本轮指令；`main_window._PAGE_GROUPS` 定义分组，`_PAGE_ORDER` 定义取页顺序 |
| 子页命名 | `app_info.tab_titles` 六项**保留 ①–⑥ 前缀不删** | ①–⑥ 已写进大量既有界面文案与说明书（如"请到④「列名映射」页"），删前缀会制造死链；本轮要求"不允许死链接"，所以只挪位置不改名 |
| 跨页跳转 | 本轮唯一新增跳转：③ 离线分析子页顶部「去「列名映射」」按钮 → `main_window.goto_page("mapping")`；原 ① 页从来没有"去硬件配置"按钮，④↔③ 之间仍是文字提示，因此不存在指向已删除旧标签的死链 | 跳页统一走 `goto_page(key)`，任何页面都不再记 tab 序号；非法键返回 False 且不移动页面 |
| 映射状态提示 | ③ 页顶部一行状态条：必需字段全映射=绿、缺项=黄并计数（"还差 4 项（控制数据 2 项、离线取样 2 项）"）、映射文件读不了=黄并给出原因；`showEvent` 自动刷新，任何异常降级为提示、绝不抛错 | 文案集中在 `app_info.ui_texts`（mapping_goto / mapping_ok / mapping_missing / mapping_unreadable），代码只按键取值，不写死句子 |
| 主题 | 新增 `ui/theme.py`（纯函数、不 import Qt）：主色 #2E7D8C、窗口底 #F4F6F7、外边距 16px、分组内 10px、控件等高、数字区等宽字体、红黄绿语义色与 `common.LEVEL_BG` 同源；全部读 `config.app_info.theme`，缺段或坏值自动兜底，样式表生成异常返回空串（宁可不美化，也不能因为样式写错打不开软件） | 用户要求蓝绿冷色调 + 语义色全局统一；改配色/改边距不用动代码 |
| 图标 | 新增 `ui/icons.py`：用 QPainter 现画齿轮 / 折线图 / 清单等图标，不引入图片资源、不新增第三方依赖；尺寸非法返回 None、由调用方兜底 | 3 个大板块各一个图标，6 个子页各一个小图标 |
| 分组标题留白 | QGroupBox 的 `margin-top` 改为由标题字号推导（`title_pt×96÷72+5` px），不再用固定 10px | 225% 缩放下实测模板库页加粗标题压住表格第一行，改后标题独占一条"标题带" |
| 顶部与底部 | 标题栏（软件名 / 版本 / 轮次）与底部红字免责声明 + 文件路径行原样保留，样式不变 | 用户本轮明确要求 |
| 逻辑改动 | **零改动**：第三节公式、R01–R18 校验、CSV 导入、列名映射存储、模板库对比、SOP 文本、config.yaml 结构均未动；`impeller_diameter_m` 仍为 null（R06 继续走黄色警告） | 本轮只挪位置 + 改外观 |
| 测试 | 新增 `tests/test_ui_round7.py` 38 条（板块数与标题来自 config / 6 页各出现一次 / 分组顺序 / `goto_page` 全键可达且非法键不崩 / 旧属性无死链 / 图标兜底 / theme 兜底 / 语义色一致 / 映射提示四态 / 点按钮真的跳转）；`tests/test_main_window_round6.py` 只改控件定位方式（`win.page("hardware")`），断言逻辑未改；合计 **404 passed**（基线 366 + 本轮 38，一条未删） | 期望值仍全部来自 requirements.md 第三节算例与 config.yaml，浮点比较用 pytest.approx |
| 版本号 | `app_info.version` 1.0.0 → 1.1.0，`round_label` 改为第七轮；`docs/使用说明.txt` 第 1/2/3/5/10 节同步（第 2 节改成"3 大板块 + 6 个子页"导航图） | 窗口标题、交付包 `本版本信息.txt` 与 zip 文件名随之更新 |
| 新增依赖 | 无（运行期仍是 PySide6 / PyYAML / matplotlib；开发期 pytest / PyInstaller） | 符合"不引入新第三方依赖" |

## 第七轮补充决策记录（2026-11-20，用户答复「1通过，2可以删除，4要word说明书」）

| 项目 | 决策 | 依据 / 备注 |
|------|------|-------------|
| 第七轮验收 | **通过**；本轮只做补充交付，不开启新功能开发 | AGENTS.md「每轮结束等我确认后再进下一轮」，下一轮仍需你点头 |
| 根目录旧副本 | 删除 `requirements_旧副本_已弃用_20261112.txt.txt` | 你答复「2可以删除」；该文件原本未被 git 跟踪，删除不影响提交历史 |
| Word 说明书 | 新增 `docs\使用说明.docx`；**纯文本 `docs\使用说明.txt` 仍是唯一事实来源**，docx 由 `tools\build_docx_manual.py` 从 txt 排版生成，每次打包都重新生成 | 你答复「4要 Word 说明书」；杜绝 txt 与 docx 各说各话 |
| 生成器实现 | **只用标准库**（zipfile + 手写 WordprocessingML），不引入 python-docx；产物 16.5 KB / 181 块 / 3 张真表格（18 条校验、6 个数据文件、10 条术语）/ 223 行逐行核对；A4 竖版、每节另起一页、页脚「第 X 页 / 共 Y 页」 | 符合「不引入新第三方依赖」；txt 里用全角空格对齐的伪表格在 Word 里转成真正的表格 |
| 安全闸门 | `build()` 生成后逐行核对（txt 每一行都必须原样出现在 docx 里），不通过就**删掉半成品并中止**；`tools\build_exe.py` 4b 步捕获该中止并停止打包 | 用测试锁死（故意让渲染器漏内容，闸门必须拦住） |
| 踩坑（已全部修掉并有回归测试） | ① 正则 `<w:t[^>]*>` 误吞 `<w:tbl>/<w:tc>`；② 非法空标签 `<vAlign/>` 让 Word 判定文件损坏；③ `R06 　能量耗散率…` 表格行被误认成小标题；④ 术语「词 + 1 个全角空格 + 释义」漏识别；⑤ 生成器只接受 str 路径，测试传 `Path` 报 TypeError | ⑤ 在 `build()` / `write_docx()` 入口用 `os.fspath()` 归一化；其余四条已记录在生成器注释里，别再犯 |
| 打包链路 | `config.app_info` 新增 `manual_docx_file: "使用说明.docx"`（顶层 25 段结构不变）；交付目录同时放 txt 与 docx，`本版本信息.txt` 同步说明 | 版本号仍 1.1.0（本轮无功能变更，只补说明书） |
| 测试 | 新增 `tests/test_docx_manual.py` 16 条（包完整性 / 每个 XML 部件可解析 / 无非法标签 / 段落样式全部有定义 / 页脚页码域 / txt 逐行一致 / 无伪表格残留 / 3 张表形状与列宽 / R01–R18 编号齐全 / 板块与子页名+版本号+「人工复核」「SIMULATED」关键词 / 安全闸门真的会拦 / 两次生成正文一致 / `build_exe.py` 已接线）；合计 **423 passed**（第七轮 407 + 本轮 16，一条未删未跳过） | 期望值来自 `docs\使用说明.txt`、`config.yaml` 与 requirements.md，未自编 |
| 新增依赖 | **无**（docx 生成只用 Python 标准库；本机 Word 2016 仅用于人工验证，不参与构建） | 符合「不引入新第三方依赖」 |
| 未附 PDF | 本机 Word 的 PDF 导出（`ExportAsFixedFormat` 与 `SaveAs2` 两种写法）均挂死 >2 分钟，已放弃，故未附 PDF 与页面截图 | 排版请你在 Word 里目视确认；需要 PDF 时请在 Word 内「另存为 PDF」 |

## 第八轮决策记录（2026-11-20，用户四项拍板：onefile 定案 + 叶轮直径 D 落地）

| 项目 | 决策 | 依据 / 备注 |
|------|------|-------------|
| 打包方式 | **维持 onefile 单文件，不改 onedir**（用户拍板#1） | 理由：单机使用、启动时长（4–6 秒）可接受、组内少数机器使用、无频繁更新分发需求；`tools\build_exe.py` 与交付包结构**一行没改** |
| 真实数据 | 真实 my-Control CSV 由用户后续单独提供，届时做导入回归（拍板#2） | 本轮仍只用带 SIMULATED 标记的演示数据自测，交付包内无任何模拟数据 |
| 叶轮直径 D | `mixing_physics.impeller_diameter_m`：null → **0.052**（= 52 mm，用户拍板#3「叶直径 0.052 m」） | 单位按 config 键名 `_m`（米）写入；数值来源已写进该行注释 |
| 功率准数 Np / 叶轮常数 k | **都不动**（拍板#3）：`power_number_np: 0.35` 保持；`impeller_constant_k` 保持 null，γ≈k×N 仍只在代码里留接口、界面不显示 | 与第一轮答复#2/#3 一致 |
| R06 行为变化 | D 填入后 R06 从"缺参数固定黄"变成**真实 ε 判定**；防御分支（D=null → 黄色警告不崩溃）保留并有测试 | 出厂算例（2000 mL、100 rpm）ε ≈ **0.0764 W/kg** → 仍🟡黄，校验汇总仍是 **红 0 / 黄 2 / 绿 16**，与第七轮一致（黄的"原因"变了） |
| ε 反解分档（D=0.052、2.0 L） | 推荐区 0.02–0.04 ≈ **64–81 rpm**；黄线 0.05 ≈ **86.8 rpm**；红线 0.10 ≈ **109.4 rpm**（ε ∝ N³） | 手算过程与逐体积对照表见 `docs/第八轮验收说明.md`，测试里用同一公式独立复算锚定 |
| ⚠️ 发现冲突（待拍板） | `agitation_start_suggestion.bands_ml` 的旧经验起步转速（≤1000→80、≤1800→100、其余→120 rpm）**与 ε 红线不一致**：1500 mL/100 rpm = 0.102 🔴、2000 mL/120 rpm = 0.132 🔴、2400 mL/120 rpm = 0.110 🔴、900 mL/80 rpm = 0.087 🟡 | 本轮**未擅自改**这组业务参数（改它就是改工艺建议值）；已在说明书里写明"两处不一致时以 R06 实际判定为准"，等你决定是把分档下调（建议 55/65/75 rpm 量级）还是保留原值 |
| ⚠️ 发现校验口径冲突（待拍板） | `process_defaults.agitation_rpm` 允许下限 **80 rpm**，但 D=0.052 m 下 600 mL 的 ε 红线转速只有 **73.2 rpm**——即「合规的最低转速」仍超红线，600～1000 mL 工况 R05 与 R06 互相夹住 | 本轮**未擅自改**下限（改它等于改工艺允许范围）；两个选项：①把下限放宽到 40–50 rpm（②硬件配置页与 config 一起改），②确认小体积就是不允许高速（则 R06 报红即为正确行为）。详见 `docs/第八轮验收说明.md` 第 4 节 |
| ⚠️ 发现文案歧义（待拍板） | `validators.rule_r06` 在 ε 落在 **0.04–0.05** 之间时判"通过"，但提示文字写成"低于推荐区"（实际是高于推荐区上限） | 属于校验文字分支的小缺陷；因为改它等于改校验输出，本轮**只报告未修改**，等你点头再改 |
| 说明书同步 | `docs\使用说明.txt` 第 4 节 R06 段改写（D 已填、ε 实算、分档数字、与起步建议转速不一致的提醒、D 只能在 config 改因为②页没有该项），并重新生成 Word 版 `docs\使用说明.docx` | 说明书仍由 `tools\build_docx_manual.py` 单一来源生成，逐行核对通过 |
| 测试 | `tests\test_validators.py`：缺 D 防御分支改为**显式注入 null** 复现（不再依赖出厂值为 null）；新增出厂 D 值断言、出厂算例 ε 独立复算锚定、110 rpm 必须报红；出厂汇总断言 `["R06","R16"]` **未改**（仍然成立） | 本轮没有删除或放宽任何断言 |
| 新增依赖 | 无 | — |
