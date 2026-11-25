# wf-office

![办公文档工作流：内容、图表、排版与渲染验收](assets/readme/hero.svg)

办公文档工作流，当前优先做 Word。

它不是“Word 模板库”，而是一条可验收的流程：先确认读者和交付物，再组织内容、做图表、排版、渲染和校对。已有文档默认输出副本，不覆盖原稿。

## 适合

- 写报告、汇报、会议纪要、方案、说明书、通知或正式文件。
- 修改已有 Word 的内容、结构或格式。
- 把散乱材料整理成一份能交付的文档。
- 把文章、对话或资料整理成能读、能查的知识笔记。
- 把讲义、培训材料、教程或知识库文章做成有学习效果的材料。
- 用代码生成图表并插入 Word。
- 给长文补目录、页码、题注、交叉引用和最终 PDF。

## 不适合

- 网页、App、界面或品牌设计：`wf-design`。
- 写代码、修功能：`wf-vibecode`。
- 学科学习计划、教材定位、题目讲解和错题记录：`wf-study`。
- 只整理 Git 或发布仓库：`wf-github-ops`。

## 常用路径

```text
新建报告：
文档契约 → 章节地图 → 一段样章 → 全文 → 图表/表格 → 渲染验收

修改已有 Word：
备份原文 → 只读诊断 → 确认改动范围 → 局部修改 → 页面差异 → 交付副本

只改格式：
保留内容与对象 → 套项目模板 → 检查标题/目录/页码 → 渲染

插入图表：
确定数据与关系 → 生成 PNG → 插入 Word → 检查题注、来源和渲染

学习材料：
通用培训走本流程 + learning-material-design；
备考走 wf-study + learning-material-design，按需调用本流程做文件
```

## 关键文件

- `SKILL.md`：何时用、七个阶段、路径和边界。
- `references/playbook.md`：逐步执行手册。
- `references/content-design.md`：内容结构、信息呈现、图表与中文排版规则。
- `references/learning-materials.md`：学习材料入口；需要深做时读 `learning-material-design`。
- `references/note-organization.md`：知识笔记整理、云端写入与回读。
- `references/word.md`：Word 新建、修订、排版和验收。
- `references/charts.md`：图表选型、JSON 规格、代码生成和插入。
- `references/acceptance.md`：交付前最小质量线。

## 图表命令

```bash
py -3 scripts/render_chart.py --spec chart.json --out chart.png --html chart.html
py -3 scripts/insert_chart.py --docx report.docx --image chart.png --output report-with-chart.docx --caption "图 1 各渠道收入" --alt "柱状图：各渠道收入及数据来源" --width-cm 16
```

## 依赖

核心依赖、插件和本机技能见 `references/environment.md`。Word 的最终渲染门禁由 `documents` 提供；图表截图使用本机 Playwright。

思源写入使用 `scripts/siyuan_note.py`；它需要本机思源运行，端口和访问码从思源配置或环境变量读取，脚本不会打印访问码。笔记结构检查使用 `scripts/note_check.py`。

## Oil 能力边界

Oil 的 CLI 是 `npx github:oil-oil/oil-cli`，用于发现、安装和更新 Oil 商店技能；当前商店列表只有 Oil UI / Oil UI Pro，没有 Word、Office 或图表专门技能。本工作流使用的 Oil 能力是 `oil-tone`（文风）和 `vibehub`（术语提示），不把 Oil UI 误当办公文档能力。

## 安装与许可

```bash
npx skills add hayou2002/wf-office
```

[MIT](LICENSE)
