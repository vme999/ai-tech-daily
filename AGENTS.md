# AGENTS.md — AI Tech Report 项目指南

## 项目目标

生成有来源、有判断的中文 AI 行业周报，而不是机械罗列新闻。基本工作流为：收集素材 → 撰写 `content/weekly/YYYY-Www.md` → 构建站点 → 按需发布。

周报的完整执行方式见 `.trae/skills/weekly-report/SKILL.md`；种子信源见 `sources.yml`。两者都提供起点，不限制 Agent 根据本周情况调整方法。

## 收集周期

- 以 `Asia/Shanghai` 的当前日期确定 ISO 年与周编号；每期覆盖当前周周一至周日。
- 普通生成每次重新收集本周截至运行时已公开的信息，更新同周报告；不改为上一周，也不因断更扩大到其他周。只有用户明确要求处理历史周时才处理其他周；报告不标记或展示是否为历史补写。
- 不把尚未发生的信息当作事实。

## 内容红线

1. 事实、数字和引述必须来自本次实际访问过的来源，并至少在对应详细正文中首次出现时提供可点击链接；速览不重复放置链接；禁止凭记忆补全。
2. 不确定的信息不写，素材不足时宁缺毋滥。
3. 区分窗口内新进展与旧闻延续；上一期已报道且没有实质新增的事件不重复展开。
4. 厂商自述、客户案例和未经独立验证的指标必须说明性质。
5. 同一事件不重复计入多个板块。

在构建脚本要求的格式内，选题、篇幅、其他章节、分类方式和信源扩展由 Agent 根据素材自行决定。使用简体中文，保持克制、有洞察的表达。

## 文件与构建

- 周报路径：`content/weekly/YYYY-Www.md`。
- frontmatter 必须包含与文件名一致的字符串 `week`（ISO 周编号，如 `"2026-W01"`）、非空 `title` 和带时区的 `collected_at`；周一至周日的日期由构建脚本推导。
- `research/` 是本地工作目录，不提交版本库；底稿的使用与清理见周报 skill。
- `.trae/skills/weekly-report/assets/report-template.md` 是建议骨架；“速览”及其与重点事件标题的对应关系须保留，其他章节可根据素材调整。
- `site/` 是本地构建产物，不提交版本库。

```bash
python3 scripts/build.py          # 校验并构建
python3 scripts/build.py --lint   # 仅校验
python3 -m http.server -d site 8000
```

构建脚本检查最低发布格式、收集时间与周次、速览与重点事件标题的对应，以及详细正文是否包含外部来源链接；它无法判断来源是否真的支持陈述。内容红线仍由 Agent 在写作和逐条复核阶段负责。

## Git 与发布

- “生成周报”默认只生成并验证文件；仅在用户明确要求提交或发布时 commit，仅在明确要求 push 或发布时 push。
- commit message 使用 Conventional Commits；周报推荐 `docs: weekly report for YYYY-Www`。
- 提交前检查变更范围，只包含本次相关文件。
- push 前必须完成构建，并确认 `site/weekly/<周编号>/index.html` 存在。
- 如果目标远程分支不存在，先告知用户会创建新分支并等待明确确认。
- push `main` 后由 `.github/workflows/deploy.yml` 构建并部署 GitHub Pages。
