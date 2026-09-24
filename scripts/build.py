#!/usr/bin/env python3
"""AI Tech Report 站点构建脚本。

将 content/weekly/YYYY-Www.md（YAML frontmatter + Markdown 正文）
全量渲染为 site/ 下的静态站点：

  site/index.html                  报告列表（新→旧）
  site/weekly/YYYY-Www/index.html  周报（含目录、上下篇导航）

构建前自动对全部报告执行发布合法性校验：frontmatter、
周次与收集时间、模板占位残留，以及速览和外部来源等最低内容契约。
内容质量由写作阶段负责。

用法:
    python3 scripts/build.py           # lint 校验 + 全量构建
    python3 scripts/build.py --lint    # 仅校验，不构建
"""

import argparse
import html
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
from pathlib import Path
from string import Template

try:
    import markdown
    import yaml
except ImportError:
    sys.exit("缺少构建依赖，请先执行: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "weekly"
SITE_DIR = ROOT / "site"
TEMPLATES_DIR = ROOT / "templates"

# ── lint：只校验文件是否可发布，不编码编辑偏好 ──

# 模板中未替换即构成「占位残留」的标记。所有待填占位与待删说明统一用「【待填】」，
# 周编号占位用 YYYY-Www；检测只匹配这些标记，
# 不与模板注释的具体措辞逐字耦合。
TEMPLATE_PLACEHOLDERS = [
    "【待填】",
    "YYYY-Www",
]

QUICK_VIEW_RE = re.compile(
    r"^##\s+速览\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL
)
QUICK_VIEW_ITEM_RE = re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE)
QUICK_VIEW_ITEM_NAME_RE = re.compile(
    r"^\s*[-*+]\s+\*\*(.+?)\*\*", re.MULTILINE
)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
EXTERNAL_LINK_RE = re.compile(r'href=["\']https?://', re.IGNORECASE)
ANY_LINK_RE = re.compile(r'href=["\']', re.IGNORECASE)


class PlainText(HTMLParser):
    """提取已渲染 Markdown 的可见文字，不把标签带到首页。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_markdown(value: str) -> str:
    parser = PlainText()
    parser.feed(render_markdown(value))
    return " ".join("".join(parser.parts).split())

def parse_frontmatter(raw: str):
    """拆分 YAML frontmatter 与 Markdown 正文。"""
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", raw, re.DOTALL)
    if not match:
        sys.exit("报告必须以 YAML frontmatter 开头（参见 .trae/skills/weekly-report/assets/report-template.md）")
    meta = yaml.safe_load(match.group(1)) or {}
    return meta, match.group(2)


def render_markdown(body: str) -> str:
    """Markdown → HTML；toc 扩展为中文标题生成锚点。"""
    try:
        from markdown.extensions.toc import slugify_unicode
        toc_config = {"slugify": slugify_unicode}
    except ImportError:  # 兼容旧版 markdown
        toc_config = {}
    md = markdown.Markdown(
        extensions=["extra", "toc"], extension_configs={"toc": toc_config}
    )
    return md.convert(body)


def extract_toc(rendered_html: str) -> str:
    """从渲染后的 HTML 提取 h2，生成单层目录。"""
    items = []
    for m in re.finditer(r"<h2 id=\"([^\"]+)\">(.*?)</h2>", rendered_html):
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        items.append((m.group(1), text))
    if not items:
        return ""
    lines = ["<ul>"]
    for anchor, text in items:
        lines.append(
            f'<li><a href="#{html.escape(anchor, quote=True)}">'
            f'{html.escape(html.unescape(text))}</a></li>'
        )
    lines.append("</ul>")
    return "".join(lines)


def week_range(week: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError("周编号格式应为 YYYY-Www，例如 2026-W01")
    year, number = week.split("-W")
    start = date.fromisocalendar(int(year), int(number), 1)
    return start, start + timedelta(days=6)


def date_cn(d: str) -> str:
    start, end = week_range(d)
    return f"{d} · {start.isoformat()} 至 {end.isoformat()}"


def estimate_reading_minutes(body: str, override) -> int:
    if override:
        try:
            return max(1, int(override))
        except (TypeError, ValueError):
            pass
    plain = re.sub(r"[#*`\[\]()!>-]", "", body)
    return max(1, min(60, round(len(plain) / 500)))


def load_template(name: str) -> Template:
    path = TEMPLATES_DIR / name
    return Template(path.read_text(encoding="utf-8"))


def lint_report(path: Path) -> list:
    """校验单篇报告源文件，返回错误列表（空列表 = 通过）。"""
    raw = path.read_text(encoding="utf-8")
    try:
        meta, body = parse_frontmatter(raw)
    except SystemExit:
        return ["缺少或无法解析 YAML frontmatter（参见 .trae/skills/weekly-report/assets/report-template.md）"]
    except yaml.YAMLError as e:
        return [f"frontmatter YAML 语法错误: {e}"]

    errors = []

    d = meta.get("week")
    bounds = None
    if not isinstance(d, str):
        errors.append("week 必须是加引号的字符串")
    else:
        try:
            bounds = week_range(d)
        except ValueError as e:
            errors.append(f"week 无效: {e}")
        if d != path.stem:
            errors.append(f"week（{d}）与文件名（{path.stem}.md）不一致")

    for field in ("title",):
        value = meta.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"frontmatter 缺少 {field} 或为空")

    cutoff = None
    collected_at = meta.get("collected_at")
    if not isinstance(collected_at, str):
        errors.append("collected_at 必须是带时区的 ISO 时间字符串")
    else:
        try:
            cutoff = datetime.fromisoformat(collected_at)
        except ValueError:
            errors.append("collected_at 不是有效 ISO 时间")
        if cutoff is not None:
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                errors.append("collected_at 必须包含时区")
                cutoff = None
            else:
                cutoff = cutoff.astimezone(ZoneInfo("Asia/Shanghai"))

    if cutoff is not None and bounds is not None:
        start, _ = bounds
        if cutoff.date() < start:
            errors.append("collected_at 早于统计周")
    for ph in TEMPLATE_PLACEHOLDERS:
        if ph in raw:
            errors.append(f"存在模板占位残留: {ph!r}")

    if not body.strip():
        errors.append("正文为空")
    else:
        quick_view = QUICK_VIEW_RE.search(body)
        if not quick_view:
            errors.append("缺少必备章节 ## 速览")
        elif not QUICK_VIEW_ITEM_RE.search(quick_view.group(1)):
            errors.append("## 速览 至少需要一条列表项")
        else:
            quick_body = quick_view.group(1)
            quick_lines = [
                line for line in quick_body.splitlines()
                if re.match(r"^\s*[-*+]\s+", line)
            ]
            quick_names = QUICK_VIEW_ITEM_NAME_RE.findall(quick_body)
            if len(quick_names) != len(quick_lines):
                errors.append("速览每条必须以加粗的事件名开头")
            try:
                if ANY_LINK_RE.search(render_markdown(quick_body)):
                    errors.append("速览不应包含内部或外部链接")
            except Exception as e:
                errors.append(f"速览 Markdown 渲染失败: {e}")

            feature_body = body[quick_view.end():]
            trailing_section = re.search(r"^##\s+(?:其他动态|简讯|后续观察)\s*$", feature_body, re.MULTILINE)
            if trailing_section:
                feature_body = feature_body[:trailing_section.start()]
            feature_names = [
                re.sub(r"\s+\{#[^}]+\}\s*$", "", heading).strip()
                for heading in H2_RE.findall(feature_body)
            ]
            if quick_names != feature_names:
                errors.append("速览事件名与正文二级标题未按顺序一一对应")

        try:
            detail_body = (
                body[:quick_view.start()] + body[quick_view.end():]
                if quick_view else body
            )
            detail_html = render_markdown(detail_body)
            if not EXTERNAL_LINK_RE.search(detail_html):
                errors.append("详细正文至少需要一个可点击的外部来源链接")
        except Exception as e:
            errors.append(f"Markdown 渲染失败: {e}")

    return errors


def build_report_pages(dates) -> None:
    tpl = load_template("report.html")
    for i, d in enumerate(dates):
        meta, body = parse_frontmatter(
            (CONTENT_DIR / f"{d}.md").read_text(encoding="utf-8")
        )
        rendered_html = render_markdown(body)
        title = html.escape(meta.get("title", f"AI 行业动态 ({d})"))
        prev_html = next_html = ""
        if i > 0:  # dates 升序，前一篇是更早日期
            p = dates[i - 1]
            prev_html = f'<a href="../{p}/">← 上一篇 · {p}</a>'
        if i < len(dates) - 1:
            n = dates[i + 1]
            next_html = f'<a href="../{n}/">下一篇 · {n} →</a>'
        nav_html = "" if not (prev_html or next_html) else (
            '<div class="nav">'
            f'<span>{prev_html}</span>'
            f'<span>{next_html}</span>'
            '</div>'
        )
        page = tpl.substitute(
            title=title,
            date_cn=date_cn(d),
            reading=estimate_reading_minutes(body, meta.get("reading_minutes")),
            toc_html=extract_toc(rendered_html),
            body=rendered_html,
            nav_html=nav_html,
        )
        out = SITE_DIR / "weekly" / d / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")


def extract_lead(body: str) -> str:
    """抽取 ## 速览 前最后一个非标题段落，作为首页导语。"""
    quick_view = re.search(r"^##\s+速览\s*$", body, re.MULTILINE)
    if not quick_view:
        return ""

    preface = body[:quick_view.start()].strip()
    for paragraph in reversed(re.split(r"\n\s*\n", preface)):
        candidate = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if not candidate or candidate.startswith(("#", "统计周期：")):
            continue
        return plain_markdown(candidate)
    return ""


def build_index(dates) -> None:
    tpl = load_template("index.html")
    years = {}
    for d in reversed(dates):  # 新 → 旧
        meta, body = parse_frontmatter(
            (CONTENT_DIR / f"{d}.md").read_text(encoding="utf-8")
        )
        reading = estimate_reading_minutes(body, meta.get("reading_minutes"))
        title = html.escape(meta.get("title", f"AI 行业动态 ({d})"))
        lead = extract_lead(body)
        lead_html = f'<p class="report-lead">{html.escape(lead)}</p>' if lead else ""
        years.setdefault(d[:4], []).append(
            '<article class="report-item">\n'
            f'  <p class="date">{date_cn(d)} · {reading} 分钟阅读</p>\n'
            f'  <h2><a href="weekly/{d}/">{title}</a></h2>\n'
            f'  {lead_html}\n'
            "</article>"
        )
    if years:
        year_nav = '<nav class="year-nav" aria-label="按年份浏览">' + "".join(
            f'<a href="#year-{year}">{year} 年</a>' for year in years
        ) + '</nav>'
        report_list = "\n".join(
            f'<section class="year-group" id="year-{year}" aria-labelledby="heading-{year}">\n'
            f'  <h2 class="year-heading" id="heading-{year}">{year} 年</h2>\n'
            f'  <div class="timeline">{"".join(items)}</div>\n'
            '</section>'
            for year, items in years.items()
        )
    else:
        year_nav = ""
        report_list = '<p class="empty">暂无报告。生成方式见 README.md。</p>'
    page = tpl.substitute(
        report_count=len(dates),
        year_nav=year_nav,
        report_list=report_list,
    )
    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Tech Report 站点构建与报告校验")
    parser.add_argument("--lint", action="store_true", help="仅执行报告校验，不构建站点")
    parser.add_argument("--current-week", action="store_true", help="输出当前 ISO 周及收集窗口，不构建站点")
    args = parser.parse_args()

    if args.current_week:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        year, number, _ = now.isocalendar()
        week = f"{year}-W{number:02d}"
        start, end = week_range(week)
        print(f"{week}: {start} 至 {end}（周一至周日）")
        print(f"收集截至: {now.isoformat(timespec='seconds')}（Asia/Shanghai）")
        return

    if not CONTENT_DIR.exists():
        sys.exit(f"缺少目录: {CONTENT_DIR}")

    paths = sorted(CONTENT_DIR.glob("*.md"))

    # 发布前校验（红线工具化）：lint 未通过即中止
    ok = True
    for path in paths:
        errors = lint_report(path)
        print(f"lint: {path.relative_to(ROOT)} {'未通过' if errors else '通过'}")
        for error in errors:
            print(f"  - {error}")
        ok = ok and not errors
    if not ok:
        hint = "" if args.lint else "，已中止构建；请修复 content/ 下的问题后重试"
        sys.exit(f"lint 未通过{hint}")
    dates = sorted(p.stem for p in paths)
    if args.lint:
        if dates:
            print(f"lint: {len(dates)} 篇报告全部通过")
        return

    if not dates:
        print("暂无报告，仅生成首页骨架。")

    # site/ 为纯构建产物：全量重建，保持幂等
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "weekly").mkdir(parents=True)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    build_report_pages(dates)
    build_index(dates)

    print(f"构建完成: {len(dates)} 篇报告")
    for d in dates:
        print(f"  site/weekly/{d}/index.html")
    print("本地预览: python3 -m http.server -d site 8000")


if __name__ == "__main__":
    main()
