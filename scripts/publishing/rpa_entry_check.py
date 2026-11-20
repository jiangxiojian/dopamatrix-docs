"""Read visible publishing controls without navigating, filling or submitting."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit


CAPABILITY_LABELS = {
    "cover": "封面入口",
    "schedule": "定时入口",
    "submit": "发布按钮",
    "upload": "素材上传入口",
}
LABEL_PATTERNS = {
    "cover": r"\b(?:edit cover|select cover|change cover|cover image|thumbnail)\b|封面|缩略图",
    "schedule": r"\b(?:schedule|scheduled|scheduling|publish later|set date and time)\b|定时|排期|预约发布|设置日期和时间",
    "submit": r"^(?:publish|post|schedule post|schedule|share now|发布|立即发布|定时发布|排期|分享)$",
    "upload": r"\b(?:upload|add video|add photos?|select video|select file)\b|上传|添加视频|添加照片|选择文件|选择视频",
}

CONTROL_SNAPSHOT_JS = r"""() => {
  const visible = (el) => Boolean(el.getClientRects().length) &&
    getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  const controls = [...document.querySelectorAll(
    'button, [role="button"], [role="radio"], [role="switch"], [role="spinbutton"], input[type="text"][placeholder], input[type="date"], input[type="time"], input[type="datetime-local"]'
  )].filter(visible).slice(0, 300).map((el) => ({
    label: (el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') ||
      (el.labels ? [...el.labels].map(label => label.innerText).join(' ') : '') || '').trim().slice(0, 180),
    type: el.getAttribute('type') || el.getAttribute('role') || el.tagName.toLowerCase(),
    role: el.getAttribute('role') || '',
    disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true')
  }));
  const bodyText = document.body ? document.body.innerText : '';
  const alerts = [];
  if (/verify (?:that )?you(?:'re| are) human|complete the captcha|安全验证|人脸验证|完成验证/i.test(bodyText)) alerts.push('VERIFICATION_PROMPT');
  if (/log in to (?:tiktok|facebook)|sign in to (?:tiktok|facebook)|登录以继续|请先登录/i.test(bodyText)) alerts.push('LOGIN_PROMPT');
  return {
    controls,
    file_inputs: Math.min(document.querySelectorAll('input[type="file"]').length, 20),
    enabled_file_inputs: [...document.querySelectorAll('input[type="file"]')].filter(el => !el.disabled).length,
    alerts
  };
}"""


def page_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))[:300]
    except ValueError:
        return ""


def matches_platform(url: str, platform: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    domain = {"tiktok": "tiktok.com", "facebook": "facebook.com"}.get(platform)
    return bool(domain and parsed.scheme in {"http", "https"} and (host == domain or host.endswith("." + domain)))


def classify_page(url: str, snapshot: dict[str, Any], tab_index: int) -> dict[str, Any]:
    capabilities = {}
    controls = snapshot.get("controls") or []
    for key, pattern in LABEL_PATTERNS.items():
        evidence = [{"label": str(control.get("label") or "")[:180],
                     "disabled": bool(control.get("disabled"))}
                    for control in controls if re.search(pattern, str(control.get("label") or ""), re.I)]
        if key == "schedule":
            evidence.extend({"label": f"{control['type']} input", "disabled": bool(control.get("disabled"))}
                            for control in controls if control.get("type") in {"date", "time", "datetime-local"})
        if key == "upload" and snapshot.get("file_inputs"):
            evidence.append({"label": "file input attached", "disabled": snapshot.get("enabled_file_inputs", 0) == 0})
        state = "NOT_OBSERVED"
        if evidence:
            state = "OBSERVED_DISABLED" if all(item["disabled"] for item in evidence) else "OBSERVED"
        capabilities[key] = {"state": state, "evidence": evidence[:8]}
    safe_url = page_url(url)
    path = urlsplit(safe_url).path.lower()
    composer_path = any(part in path for part in ("/upload", "/composer", "/reels/create", "/reel/create"))
    has_upload = capabilities["upload"]["state"] != "NOT_OBSERVED"
    has_submit = capabilities["submit"]["state"] != "NOT_OBSERVED"
    # A button label alone on a profile/feed is not proof of a publishing composer.
    composer = composer_path or (has_upload and has_submit)
    alerts = list(snapshot.get("alerts") or [])
    identity = {"state": "UNVERIFIED", "page_id_candidate": ""}
    query = parse_qs(urlsplit(url).query)
    candidate = (query.get("asset_id") or [""])[0]
    if candidate.isdigit():
        identity["page_id_candidate"] = candidate
    return {
        "tab_index": tab_index, "url": safe_url, "composer_observed": composer,
        "identity": identity, "alerts": alerts,
        "capabilities": capabilities,
    }


def inspect_context(context: Any, platform: str, pages: list[Any] | None = None) -> dict[str, Any]:
    if platform not in {"tiktok", "facebook"}:
        raise ValueError("Unsupported publishing platform")
    tabs = []
    errors = []
    matching_count = 0
    # Bound the scan so a profile with many tabs does not monopolize the worker.
    for index, page in enumerate(list(context.pages) if pages is None else pages, 1):
        try:
            url = page.url
            if not matches_platform(url, platform):
                continue
            matching_count += 1
            if matching_count > 10:
                errors.append({"tab_index": index, "error_type": "TAB_LIMIT"})
                break
            snapshot = page.locator("html").evaluate(CONTROL_SNAPSHOT_JS, timeout=4000)
            tabs.append(classify_page(url, snapshot, index))
        except Exception as exc:
            errors.append({"tab_index": index, "error_type": type(exc).__name__})
    composers = [tab for tab in tabs if tab["composer_observed"]]
    summary = {}
    for key in CAPABILITY_LABELS:
        states = [tab["capabilities"][key]["state"] for tab in composers]
        summary[key] = "OBSERVED" if "OBSERVED" in states else "OBSERVED_DISABLED" if "OBSERVED_DISABLED" in states else "NOT_OBSERVED"
    status = "ENTRY_OBSERVED" if composers else "ENTRY_NOT_OPEN" if tabs else "NO_PLATFORM_TAB"
    page_ids = sorted({tab["identity"]["page_id_candidate"] for tab in tabs if tab["identity"]["page_id_candidate"]})
    if len(composers) > 1 or len(page_ids) > 1:
        status = "AMBIGUOUS_ENTRIES"
    if any(tab["alerts"] for tab in tabs):
        status = "ACCOUNT_ACTION_REQUIRED"
    if errors and not tabs:
        status = "SCAN_FAILED"
    elif errors and status == "ENTRY_OBSERVED":
        status = "PARTIAL_SCAN"
    return {"checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": status, "platform": platform, "tabs": tabs, "errors": errors,
            "scope": "existing_platform_tabs", "composer_count": len(composers), "page_id_candidates": page_ids,
            "capabilities": summary, "identity_verified": False, "automation_verified": False}


def report_path(plan_path: Path, task: dict[str, Any]) -> Path:
    binding = [task.get(key, "") for key in (
        "publish_id", "platform", "account_key", "profile_id", "content_type", "facebook_content_mode", "composer_url",
    )]
    digest = hashlib.sha256(json.dumps(binding, ensure_ascii=True).encode("utf-8")).hexdigest()[:24]
    return plan_path.parent / "entry_checks" / (digest + ".json")


def save_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as fh:
            temporary = Path(fh.name)
            json.dump(report, fh, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def load_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect existing BitBrowser publishing tabs without submitting content")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--bit-api", default="http://127.0.0.1:54345")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--open-entries", action="store_true", help="Open empty TK/FB composers in new tabs; never upload or submit")
    parser.add_argument("--capture-pages", action="store_true", help="Save local screenshots and visible control labels for composer diagnostics")
    args = parser.parse_args()
    from bitbrowser_rpa_example import (
        DEFAULT_FACEBOOK_COMPOSER_URL, DEFAULT_TIKTOK_UPLOAD_URL, BitBrowserClient, configure_utf8_stdio, connect_browser_context,
    )

    configure_utf8_stdio()
    client = BitBrowserClient(args.bit_api, timeout=8)
    client.health()
    opened = client.open_profile(args.profile_id)
    pw, browser, context = connect_browser_context(opened.cdp_url, timeout_ms=10_000, allow_new_context=False)
    try:
        if args.open_entries:
            page_ids = set()
            for tab in context.pages:
                if matches_platform(tab.url, "facebook"):
                    candidate = (parse_qs(urlsplit(tab.url).query).get("asset_id") or [""])[0]
                    if candidate.isdigit():
                        page_ids.add(candidate)
            targets = [DEFAULT_TIKTOK_UPLOAD_URL]
            if len(page_ids) == 1:
                targets.append(DEFAULT_FACEBOOK_COMPOSER_URL + "?asset_id=" + next(iter(page_ids)))
            else:
                print("Facebook composer not opened: the target Page is not unique in existing tabs.")
            for url in targets:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
        for platform in ("tiktok", "facebook"):
            pages = list(context.pages)
            report = inspect_context(context, platform, pages=pages)
            report["profile_id"] = args.profile_id
            save_report(args.output_dir / (platform + ".json"), report)
            if args.capture_pages:
                for tab in report["tabs"]:
                    if not tab["composer_observed"]:
                        continue
                    page = pages[tab["tab_index"] - 1]
                    if page_url(page.url) != tab["url"]:
                        continue
                    stem = f"{platform}-{tab['tab_index']}"
                    page.screenshot(path=str(args.output_dir / (stem + ".png")), full_page=True)
                    controls = page.locator("html").evaluate(CONTROL_SNAPSHOT_JS, timeout=4000)
                    save_report(args.output_dir / (stem + "-controls.json"), controls)
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        pw.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
