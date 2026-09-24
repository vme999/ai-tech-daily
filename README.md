# AI Tech Report

有来源、有判断的中文 AI 行业周报。[查看线上站点](https://vme999.github.io/ai-tech-report/)。

## 生成与预览

对 Agent 说“生成本周周报”。报告使用 `Asia/Shanghai` 的当前 ISO 周，覆盖周一至运行时已公开的动态；同周重跑会重新扫描完整窗口。跨周去重只参考上期“速览”。

生成过程和内容要求见 [AGENTS.md](AGENTS.md) 与 [周报 skill](.trae/skills/weekly-report/SKILL.md)。`sources.yml` 是种子信源，Agent 还会进行开放网络检索。

```bash
pip install -r requirements.txt
python3 scripts/build.py --current-week  # 查看当前 ISO 周
python3 scripts/build.py --lint          # 校验所有报告
python3 scripts/build.py                 # 校验并构建 site/
python3 -m http.server -d site 8000     # 本地预览
```

周报保存在 `content/weekly/YYYY-Www.md`。生成时使用 `research/YYYY-Www.md` 汇总发现与证据，成稿复核和构建通过后清理；`research/` 与 `site/` 均不提交。

## 提交与发布

“生成周报”默认只生成并验证。明确要求提交或发布时才 commit；明确要求发布或 push 时才推送。推送前须完成构建并检查目标远程分支。`main` 的 push 会触发 [GitHub Actions](.github/workflows/deploy.yml) 构建并部署 GitHub Pages。

报告结构可参考 [模板](.trae/skills/weekly-report/assets/report-template.md)；调整跟踪入口请编辑 [sources.yml](sources.yml)，调整站点外观请编辑 `templates/`。
