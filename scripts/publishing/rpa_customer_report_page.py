"""Generate a static customer report HTML page from RPA report CSVs.

The page is intentionally local and read-only. It turns the bridge files from
``rpa_report_export.py`` into a customer-facing report preview without requiring
the main DopaMatrix application, a database, or a web server.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DETAIL = "customer_report_seed.csv"
DEFAULT_OVERVIEW = "customer_report_overview.csv"
DEFAULT_OUTPUT = "customer_report.html"

DETAIL_FIELDS = [
    "report_snapshot_at",
    "client_id",
    "product_id",
    "platform",
    "content_type",
    "publish_id",
    "status",
    "status_group",
    "is_published",
    "needs_post_url",
    "metrics_status",
    "lead_status",
    "post_url",
    "platform_post_id",
    "published_at",
    "account_key",
    "profile_name",
    "profile_id",
    "media_path",
    "title",
    "tracking_url",
    "attribution_token",
    "scheduled_at",
    "screenshot",
    "duration_seconds",
    "started_at",
    "finished_at",
    "manual_operator",
    "manual_checked_at",
    "manual_note",
    "error_type",
    "error_action",
    "error_message",
    "views",
    "impressions",
    "likes",
    "comments",
    "shares",
    "saves",
    "profile_visits",
    "link_clicks",
    "raw_inquiries",
    "valid_inquiries",
    "quote_count",
    "deal_count",
    "deal_amount",
    "data_source",
    "report_note",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{str(k): clean_text(v) for k, v in row.items()} for row in reader]


def to_int(value: str) -> int:
    text = clean_text(value)
    if not text:
        return 0
    try:
        return int(float(text.strip("%")))
    except ValueError:
        return 0


def parse_time(value: str) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def latest_time(rows: list[dict[str, str]]) -> str:
    best_text = ""
    best_dt: datetime | None = None
    for row in rows:
        for key in ("published_at", "finished_at", "started_at", "manual_checked_at", "report_snapshot_at"):
            value = row.get(key, "")
            dt = parse_time(value)
            if dt is not None and (best_dt is None or dt >= best_dt):
                best_dt = dt
                best_text = value
    return best_text


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{(numerator / denominator) * 100:.2f}%"


def status_label(status: str, group: str = "") -> str:
    key = clean_text(status).upper()
    group_key = clean_text(group).upper()
    if key == "PUBLISHED_MANUAL" or group_key == "PUBLISHED":
        return "已发布"
    if key == "PREPARED" or group_key == "DRAFT_PREPARED":
        return "待人工发布"
    if key in {"FAILED", "PARTIAL"} or group_key == "NEEDS_OPERATOR":
        return "需处理"
    if key in {"REJECTED_MANUAL", "SKIPPED"} or group_key == "NOT_PUBLISHED":
        return "未发布"
    if key in {"READY", "PLANNED", "RUNNING"} or group_key == "PENDING":
        return "待执行"
    return key or "未知"


def status_class(status: str, group: str = "") -> str:
    key = clean_text(status).upper()
    group_key = clean_text(group).upper()
    if key == "PUBLISHED_MANUAL" or group_key == "PUBLISHED":
        return "published"
    if key == "PREPARED" or group_key == "DRAFT_PREPARED":
        return "prepared"
    if key in {"FAILED", "PARTIAL"} or group_key == "NEEDS_OPERATOR":
        return "attention"
    if key in {"REJECTED_MANUAL", "SKIPPED"} or group_key == "NOT_PUBLISHED":
        return "muted"
    return "pending"


def file_uri(path_text: str, base_dir: Path) -> str:
    text = clean_text(path_text)
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    try:
        return path.as_uri()
    except ValueError:
        return ""


def normalized_detail_rows(rows: list[dict[str, str]], base_dir: Path) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for raw in rows:
        row = {field: raw.get(field, "") for field in DETAIL_FIELDS}
        row["status_label"] = status_label(row.get("status", ""), row.get("status_group", ""))
        row["status_class"] = status_class(row.get("status", ""), row.get("status_group", ""))
        row["post_url_present"] = "true" if row.get("post_url") else "false"
        row["screenshot_uri"] = file_uri(row.get("screenshot", ""), base_dir)
        row["media_uri"] = file_uri(row.get("media_path", ""), base_dir)
        row["search_blob"] = " ".join(
            row.get(key, "")
            for key in (
                "client_id",
                "product_id",
                "platform",
                "content_type",
                "publish_id",
                "status",
                "account_key",
                "profile_name",
                "title",
                "media_path",
                "post_url",
                "tracking_url",
                "error_type",
                "error_action",
                "error_message",
            )
        ).lower()
        normalized.append(row)
    return sorted(
        normalized,
        key=lambda item: (
            item.get("client_id", ""),
            item.get("product_id", ""),
            item.get("platform", ""),
            item.get("published_at") or item.get("finished_at") or item.get("started_at") or "",
            item.get("publish_id", ""),
        ),
    )


def build_summary(detail_rows: list[dict[str, str]], overview_rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(detail_rows)
    published = sum(1 for row in detail_rows if row.get("status_class") == "published")
    prepared = sum(1 for row in detail_rows if row.get("status_class") == "prepared")
    attention = sum(1 for row in detail_rows if row.get("status_class") == "attention")
    rejected = sum(1 for row in detail_rows if row.get("status_class") == "muted")
    post_url_count = sum(1 for row in detail_rows if row.get("post_url"))
    metrics_pending = sum(1 for row in detail_rows if row.get("metrics_status") == "PENDING_METRICS")
    lead_pending = sum(1 for row in detail_rows if row.get("lead_status") == "PENDING_LEADS")
    platforms = sorted({row.get("platform", "") for row in detail_rows if row.get("platform", "")})
    clients = sorted({row.get("client_id", "") for row in detail_rows if row.get("client_id", "")})
    products = sorted({row.get("product_id", "") for row in detail_rows if row.get("product_id", "")})
    accounts = sorted({row.get("account_key", "") for row in detail_rows if row.get("account_key", "")})
    by_status = Counter(row.get("status_label", "未知") for row in detail_rows)

    return {
        "total_tasks": total,
        "published_count": published,
        "prepared_count": prepared,
        "attention_count": attention,
        "rejected_count": rejected,
        "post_url_count": post_url_count,
        "metrics_pending_count": metrics_pending,
        "lead_pending_count": lead_pending,
        "publish_success_rate": pct(published, total),
        "latest_activity_at": latest_time(detail_rows),
        "platforms": platforms,
        "clients": clients,
        "products": products,
        "accounts": accounts,
        "status_counts": dict(by_status),
        "overview_count": len(overview_rows),
    }


def options(values: list[str]) -> str:
    parts = ['<option value="ALL">全部</option>']
    for value in values:
        safe = html.escape(value, quote=True)
        parts.append(f'<option value="{safe}">{safe}</option>')
    return "\n".join(parts)


def json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_html(
    detail_rows: list[dict[str, str]],
    overview_rows: list[dict[str, str]],
    source_info: dict[str, str],
) -> str:
    summary = build_summary(detail_rows, overview_rows)
    generated_at = datetime.now().isoformat(timespec="seconds")
    clients = summary["clients"]
    products = summary["products"]
    platforms = summary["platforms"]
    status_values = sorted({row.get("status_label", "未知") for row in detail_rows})

    detail_json = json_for_script(detail_rows)
    overview_json = json_for_script(overview_rows)
    summary_json = json_for_script(summary)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DopaMatrix 客户发布报告</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --line: #d9e1ec;
      --text: #1b2430;
      --muted: #667085;
      --blue: #1f5fbf;
      --green: #16794c;
      --amber: #a15c00;
      --red: #b42318;
      --gray: #6b7280;
      --shadow: 0 1px 2px rgba(15, 23, 42, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.45;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    .wrap {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      padding: 18px 0 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.2;
      font-weight: 720;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .source-list {{
      display: grid;
      gap: 3px;
      max-width: 640px;
      color: var(--muted);
      font-size: 12px;
      text-align: right;
      overflow-wrap: anywhere;
    }}
    main {{ padding: 18px 0 28px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .metric {{
      min-height: 86px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
      padding: 12px;
    }}
    .metric label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      display: block;
      font-size: 26px;
      line-height: 1.1;
      letter-spacing: 0;
    }}
    .metric small {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .filters {{
      display: grid;
      grid-template-columns: 1.5fr repeat(4, minmax(128px, .7fr));
      gap: 10px;
      margin: 12px 0;
      align-items: end;
    }}
    .field label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    input, select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 7px 9px;
      font: inherit;
      font-size: 14px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 12px;
      align-items: start;
    }}
    .overview-panel {{
      margin-bottom: 12px;
    }}
    .overview-table-wrap {{
      overflow: auto;
      max-height: 260px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
      overflow: hidden;
    }}
    .panel h2 {{
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
      letter-spacing: 0;
    }}
    .table-wrap {{ overflow: auto; max-height: 72vh; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #edf1f6;
      padding: 10px 9px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f8fafc;
      color: #344054;
      font-size: 12px;
      font-weight: 650;
    }}
    td.title-cell {{
      min-width: 220px;
      max-width: 300px;
      white-space: normal;
    }}
    td.note-cell {{
      min-width: 220px;
      max-width: 320px;
      white-space: normal;
      color: var(--muted);
    }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 650;
      border: 1px solid transparent;
    }}
    .published {{ color: var(--green); background: #eaf7ef; border-color: #b8e4c8; }}
    .prepared {{ color: var(--amber); background: #fff4df; border-color: #ffdda2; }}
    .attention {{ color: var(--red); background: #fff1f0; border-color: #ffd0cc; }}
    .muted {{ color: var(--gray); background: #f1f3f6; border-color: #d8dde6; }}
    .pending {{ color: var(--blue); background: #eef5ff; border-color: #c9ddff; }}
    .side-section {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .side-section:last-child {{ border-bottom: 0; }}
    .side-section h3 {{
      margin: 0 0 9px;
      font-size: 14px;
      letter-spacing: 0;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 88px 1fr 42px;
      gap: 8px;
      align-items: center;
      margin: 7px 0;
      color: var(--muted);
      font-size: 12px;
    }}
    .bar {{
      height: 8px;
      background: #e8edf5;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar > span {{
      display: block;
      height: 100%;
      background: var(--blue);
      border-radius: inherit;
    }}
    .empty {{
      padding: 18px;
      color: var(--muted);
      font-size: 14px;
    }}
    .mini {{
      color: var(--muted);
      font-size: 12px;
    }}
    .footnote {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 1180px) {{
      .metrics {{ grid-template-columns: repeat(3, minmax(140px, 1fr)); }}
      .layout {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 760px) {{
      .wrap {{ width: min(100vw - 20px, 720px); }}
      .topbar {{ display: block; }}
      .source-list {{ text-align: left; margin-top: 10px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .filters {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 21px; }}
      .metric strong {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>DopaMatrix 客户发布报告</h1>
        <div class="subtitle">生成时间：{html.escape(generated_at)} · 最近活动：{html.escape(summary.get("latest_activity_at") or "暂无")}</div>
      </div>
      <div class="source-list">
        <span>明细：{html.escape(source_info.get("detail_csv", ""))}</span>
        <span>总览：{html.escape(source_info.get("overview_csv", ""))}</span>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="metrics" aria-label="概览指标">
      <div class="metric"><label>发布任务</label><strong id="metric-total">0</strong><small>当前筛选内任务数</small></div>
      <div class="metric"><label>已发布</label><strong id="metric-published">0</strong><small id="metric-rate">成功率 0.00%</small></div>
      <div class="metric"><label>帖子链接</label><strong id="metric-post-url">0</strong><small>已回收公开链接</small></div>
      <div class="metric"><label>待人工发布</label><strong id="metric-prepared">0</strong><small>草稿已准备</small></div>
      <div class="metric"><label>需处理</label><strong id="metric-attention">0</strong><small>失败或部分成功</small></div>
      <div class="metric"><label>待补指标</label><strong id="metric-pending">0</strong><small>播放/询盘未同步</small></div>
    </section>

    <section class="filters" aria-label="筛选">
      <div class="field">
        <label for="search">搜索</label>
        <input id="search" type="search" placeholder="publish_id / 客户 / 产品 / 账号 / 标题 / 链接">
      </div>
      <div class="field">
        <label for="client-filter">客户</label>
        <select id="client-filter">{options(clients)}</select>
      </div>
      <div class="field">
        <label for="product-filter">产品</label>
        <select id="product-filter">{options(products)}</select>
      </div>
      <div class="field">
        <label for="platform-filter">平台</label>
        <select id="platform-filter">{options(platforms)}</select>
      </div>
      <div class="field">
        <label for="status-filter">状态</label>
        <select id="status-filter">{options(status_values)}</select>
      </div>
    </section>

    <section class="panel overview-panel">
      <h2>客户与平台概览</h2>
      <div class="overview-table-wrap">
        <table>
          <thead>
            <tr>
              <th>客户</th>
              <th>产品</th>
              <th>平台</th>
              <th>内容类型</th>
              <th>任务</th>
              <th>已发布</th>
              <th>成功率</th>
              <th>帖子链接</th>
              <th>最新发布</th>
              <th>最新活动</th>
            </tr>
          </thead>
          <tbody id="overview-body"></tbody>
        </table>
      </div>
      <div id="overview-empty" class="empty" hidden>没有符合筛选条件的概览记录。</div>
    </section>

    <section class="layout">
      <div class="panel">
        <h2>内容与发布明细</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>状态</th>
                <th>平台</th>
                <th>客户</th>
                <th>产品</th>
                <th>内容</th>
                <th>帖子</th>
                <th>追踪</th>
                <th>账号</th>
                <th>时间</th>
                <th>证据</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody id="detail-body"></tbody>
          </table>
          <div id="empty-state" class="empty" hidden>没有符合筛选条件的发布记录。</div>
        </div>
      </div>

      <aside class="panel">
        <h2>报告侧栏</h2>
        <div class="side-section">
          <h3>状态分布</h3>
          <div id="status-bars"></div>
        </div>
        <div class="side-section">
          <h3>平台与账号</h3>
          <div id="platform-bars"></div>
          <p class="footnote" id="account-list"></p>
        </div>
        <div class="side-section">
          <h3>待补数据</h3>
          <p class="footnote">播放、互动、询盘、成交等指标当前只做占位。V1 先保证发布证据和链接真实可靠。</p>
        </div>
      </aside>
    </section>
  </main>

  <script>
    const detailRows = {detail_json};
    const overviewRows = {overview_json};
    const initialSummary = {summary_json};

    const search = document.getElementById('search');
    const clientFilter = document.getElementById('client-filter');
    const productFilter = document.getElementById('product-filter');
    const platformFilter = document.getElementById('platform-filter');
    const statusFilter = document.getElementById('status-filter');
    const tbody = document.getElementById('detail-body');
    const emptyState = document.getElementById('empty-state');
    const overviewBody = document.getElementById('overview-body');
    const overviewEmpty = document.getElementById('overview-empty');

    function esc(value) {{
      return String(value || '').replace(/[&<>"']/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }}[ch]));
    }}

    function link(url, label) {{
      if (!url) return '<span class="muted">-</span>';
      return `<a href="${{esc(url)}}" target="_blank" rel="noreferrer">${{esc(label || '打开')}}</a>`;
    }}

    function matches(row) {{
      const term = (search.value || '').trim().toLowerCase();
      if (term && !(row.search_blob || '').includes(term)) return false;
      if (clientFilter.value !== 'ALL' && row.client_id !== clientFilter.value) return false;
      if (productFilter.value !== 'ALL' && row.product_id !== productFilter.value) return false;
      if (platformFilter.value !== 'ALL' && row.platform !== platformFilter.value) return false;
      if (statusFilter.value !== 'ALL' && row.status_label !== statusFilter.value) return false;
      return true;
    }}

    function overviewMatches(row) {{
      if (clientFilter.value !== 'ALL' && row.client_id !== clientFilter.value) return false;
      if (productFilter.value !== 'ALL' && row.product_id !== productFilter.value) return false;
      if (platformFilter.value !== 'ALL' && row.platform !== platformFilter.value) return false;
      return true;
    }}

    function count(rows, predicate) {{
      return rows.filter(predicate).length;
    }}

    function setText(id, value) {{
      document.getElementById(id).textContent = value;
    }}

    function rate(published, total) {{
      return total ? `${{((published / total) * 100).toFixed(2)}}%` : '0.00%';
    }}

    function updateMetrics(rows) {{
      const total = rows.length;
      const published = count(rows, (row) => row.status_class === 'published');
      const prepared = count(rows, (row) => row.status_class === 'prepared');
      const attention = count(rows, (row) => row.status_class === 'attention');
      const postUrls = count(rows, (row) => !!row.post_url);
      const pending = count(rows, (row) => row.metrics_status === 'PENDING_METRICS' || row.lead_status === 'PENDING_LEADS');
      setText('metric-total', total);
      setText('metric-published', published);
      setText('metric-rate', `成功率 ${{rate(published, total)}}`);
      setText('metric-post-url', postUrls);
      setText('metric-prepared', prepared);
      setText('metric-attention', attention);
      setText('metric-pending', pending);
      renderBars(rows);
    }}

    function renderRows(rows) {{
      tbody.innerHTML = rows.map((row) => {{
        const post = row.post_url ? link(row.post_url, row.platform_post_id || '帖子链接') : '<span class="muted">待回收</span>';
        const tracking = row.tracking_url ? link(row.tracking_url, '短链') : '<span class="muted">-</span>';
        const screenshot = row.screenshot_uri ? link(row.screenshot_uri, '截图') : '<span class="muted">-</span>';
        const media = row.media_uri ? link(row.media_uri, '素材') : esc(row.media_path || '-');
        const note = row.report_note || row.error_message || row.manual_note || '';
        const action = row.error_action ? `<br><small>建议：${{esc(row.error_action)}}</small>` : '';
        return `<tr>
          <td><span class="pill ${{esc(row.status_class)}}">${{esc(row.status_label)}}</span><br><small>${{esc(row.status)}}</small></td>
          <td>${{esc(row.platform)}}<br><small>${{esc(row.content_type)}}</small></td>
          <td>${{esc(row.client_id || '-')}}</td>
          <td>${{esc(row.product_id || '-')}}</td>
          <td class="title-cell"><strong>${{esc(row.title || row.publish_id)}}</strong><br><small>${{esc(row.publish_id)}}</small><br>${{media}}</td>
          <td>${{post}}</td>
          <td>${{tracking}}<br><small>${{esc(row.attribution_token)}}</small></td>
          <td>${{esc(row.account_key || '-')}}<br><small>${{esc(row.profile_name || row.profile_id)}}</small></td>
          <td>${{esc(row.published_at || row.finished_at || row.started_at || '-')}}</td>
          <td>${{screenshot}}</td>
          <td class="note-cell">${{esc(note || '-')}}${{action}}</td>
        </tr>`;
      }}).join('');
      emptyState.hidden = rows.length !== 0;
    }}

    function renderOverview(rows) {{
      overviewBody.innerHTML = rows.map((row) => {{
        return `<tr>
          <td>${{esc(row.client_id || '-')}}</td>
          <td>${{esc(row.product_id || '-')}}</td>
          <td>${{esc(row.platform || '-')}}</td>
          <td>${{esc(row.content_type || '-')}}</td>
          <td>${{esc(row.total_tasks || '0')}}</td>
          <td>${{esc(row.published_count || '0')}}</td>
          <td>${{esc(row.publish_success_rate || '0.00%')}}</td>
          <td>${{esc(row.post_url_count || '0')}}</td>
          <td>${{esc(row.latest_published_at || '-')}}</td>
          <td class="mini">${{esc(row.latest_activity_at || '-')}}</td>
        </tr>`;
      }}).join('');
      overviewEmpty.hidden = rows.length !== 0;
    }}

    function groupCounts(rows, key) {{
      const map = new Map();
      rows.forEach((row) => {{
        const value = row[key] || '未填写';
        map.set(value, (map.get(value) || 0) + 1);
      }});
      return Array.from(map.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    }}

    function barsHtml(items, total) {{
      if (!items.length) return '<p class="footnote">暂无数据</p>';
      return items.map(([label, value]) => {{
        const width = total ? Math.max(4, Math.round((value / total) * 100)) : 0;
        return `<div class="bar-row"><span>${{esc(label)}}</span><div class="bar"><span style="width:${{width}}%"></span></div><strong>${{value}}</strong></div>`;
      }}).join('');
    }}

    function renderBars(rows) {{
      document.getElementById('status-bars').innerHTML = barsHtml(groupCounts(rows, 'status_label'), rows.length);
      document.getElementById('platform-bars').innerHTML = barsHtml(groupCounts(rows, 'platform'), rows.length);
      const accounts = Array.from(new Set(rows.map((row) => row.account_key).filter(Boolean))).sort();
      document.getElementById('account-list').textContent = accounts.length ? `账号：${{accounts.join(', ')}}` : '账号：暂无';
    }}

    function applyFilters() {{
      const rows = detailRows.filter(matches);
      const overviewFiltered = overviewRows.filter(overviewMatches);
      updateMetrics(rows);
      renderRows(rows);
      renderOverview(overviewFiltered);
    }}

    [search, clientFilter, productFilter, platformFilter, statusFilter].forEach((node) => {{
      node.addEventListener('input', applyFilters);
      node.addEventListener('change', applyFilters);
    }});

    applyFilters();
  </script>
</body>
</html>
"""


def generate_report_page(args: argparse.Namespace) -> Path:
    detail_path = Path(args.detail_csv).expanduser().resolve()
    overview_path = Path(args.overview_csv).expanduser().resolve()
    output_path = Path(args.output_html).expanduser().resolve() if args.output_html else detail_path.parent / DEFAULT_OUTPUT

    detail_rows = normalized_detail_rows(read_csv_rows(detail_path), detail_path.parent)
    overview_rows = read_csv_rows(overview_path)
    if args.client_id:
        detail_rows = [row for row in detail_rows if row.get("client_id") == args.client_id]
        overview_rows = [row for row in overview_rows if row.get("client_id") == args.client_id]
    if not detail_rows:
        raise SystemExit(f"No detail rows found for report: {detail_path}")

    source_info = {
        "detail_csv": str(detail_path),
        "overview_csv": str(overview_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(detail_rows, overview_rows, source_info), encoding="utf-8")
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static customer report HTML")
    parser.add_argument("--detail-csv", default=DEFAULT_DETAIL, help="customer_report_seed.csv path")
    parser.add_argument("--overview-csv", default=DEFAULT_OVERVIEW, help="customer_report_overview.csv path")
    parser.add_argument("--output-html", help="Output HTML path")
    parser.add_argument("--client-id", help="Optional client_id filter for one client report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = generate_report_page(args)
    print(f"Customer report page written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
