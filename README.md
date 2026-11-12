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
- [ ] 下一轮（第六轮）：PyInstaller 打包成双击可用的 .exe + 中文使用说明；真实 my-Control CSV 到位后在④页对齐列名

## 目录结构
```
D:\Applikon\
├── requirements.md            # 需求文档（唯一事实来源）
├── AGENTS.md                  # 协作规范
├── README.md                  # 本文件
├── requirements.txt           # Python 依赖清单（第二轮起安装）
├── config/
│   └── config.yaml            # 全部工艺参数与硬件上下限（严禁代码硬编码）
├── src/
│   └── cell_planner/
│       ├── core/              # 计算公式、18 条校验、离线分析、列名映射、模板库、SOP
│       ├── ui/                # PySide6 界面：五大模块页面
│       └── io_/               # CSV 导入、配置单导出、模板库读写
├── tests/                     # pytest 单元测试（266 条：第三节公式 + 第五节 18 条规则 + 模块 3/4/5）
├── tools/                     # 辅助脚本（仅生成带 SIMULATED 标记的演示 CSV，不参与交付）
├── data/                      # 配方（recipes/）、模板库与用户导入文件存放处（运行时生成，不入 git）
└── docs/                      # 决策记录与使用说明
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
