# wf-office 环境清单

> 由 wf-maker 生成，请勿手改；要改就改 `sources.json` 后重跑 `wf.py env`。

更新时间：2026-11-25

## 技能依赖

| 技能 | 版本 | 关系 | 来源 | 安装方式 |
| --- | --- | --- | --- | --- |
| create-viz | — | 引用 | 本机目录 | 随本机技能目录同步（无上游仓库） |
| data-visualization | — | 引用 | 本机目录 | 随本机技能目录同步（无上游仓库） |
| documents | — | 只写步骤 | 插件 documents | 安装插件 documents |
| learning-material-design | 1.1.0 | 引用 | 本机目录 | 随本机技能目录同步（无上游仓库） |
| oil-tone | — | 引用 | GitHub oil-oil/oil-tone › skills/oil-tone | npx skills add oil-oil/oil-tone --skill oil-tone |
| pdf | — | 只写步骤 | 插件 pdf | 安装插件 pdf |
| public-document-layout-master | — | 引用 | 本机目录 | 随本机技能目录同步（无上游仓库） |
| vibehub | — | 引用 | GitHub oil-oil/vibe-hub-skill › skills/vibehub | npx skills add oil-oil/vibe-hub-skill --skill vibehub |

## 自定义配置

第一次用到下面这些技能或工作流时,先问用户一次,再把结果记到对应位置;不改技能文件,不记密钥值。

- 暂无登记。需要用户本人配置时,用 `wf.py config <工作流> --needs "要定什么" --where "记在哪"`(工作流级)或 `wf.py link ... --config ...`(技能级)登记。

## 凭据与配置

本清单不记录任何密钥值。需要你自行准备的项目：

- 暂无登记；如果用到了需要密钥的步骤，用 `wf.py link <工作流> <技能> --credentials "需要什么、放在哪"` 补上。

## 恢复步骤

1. 按上表逐项安装或确认技能已就位。
2. 用 `wf.py check <工作流>` 核对每个技能的版本是否和登记时一致。
3. 按「自定义配置」逐项确认；待配置的先问用户，不要替用户选。
4. 凭据按「凭据与配置」一节自行准备，不要写进本目录。
