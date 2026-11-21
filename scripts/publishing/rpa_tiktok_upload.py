"""Open a working TikTok video uploader before attaching any media."""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit


DEFAULT_TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"
TIKTOK_VIDEO_UPLOAD_URLS = (
    DEFAULT_TIKTOK_UPLOAD_URL,
    "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video",
    "https://www.tiktok.com/upload?lang=en",
)


class TikTokUploadEntryError(RuntimeError):
    def __init__(self, code: str, message: str, attempts: list[dict[str, Any]]):
        self.code = code
        self.attempts = list(attempts)
        super().__init__(f"{code}: {message}")


UPLOAD_STATE_JS = r"""() => {
  const visible = el => Boolean(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const path = location.pathname.toLowerCase();
  const text = document.body ? document.body.innerText : '';
  if (/\/(?:captcha|verify|verification|challenge|security)(?:\/|$)/.test(path) ||
      /verify (?:that )?you(?:'re| are) human|complete the captcha|安全验证|人脸验证|完成验证/i.test(text)) {
    return {state: 'ACCOUNT_VERIFICATION'};
  }
  if (/\/(?:login|signin)(?:\/|$)/.test(path) ||
      [...document.querySelectorAll('input[type="password"]')].some(visible) ||
      /log in to (?:upload|post)|sign in to (?:upload|post)|登录以(?:上传|发布)|请先登录/i.test(text)) {
    return {state: 'LOGIN_REQUIRED'};
  }
  if (/too many requests|temporarily blocked|操作过于频繁|访问受限/i.test(text)) {
    return {state: 'PLATFORM_RATE_LIMIT_OR_RESTRICTION'};
  }
  if (!['/upload', '/tiktokstudio/upload'].includes(path.replace(/\/$/, ''))) return {state: 'WRONG_PAGE'};
  const tab = new URL(location.href).searchParams.get('tab');
  if (tab && tab !== 'video') return {state: 'WRONG_MEDIA_TAB'};
  const inputs = [...document.querySelectorAll('input[type="file"]')];
  if (inputs.some(el => el.files && el.files.length)) return {state: 'TIKTOK_UPLOAD_DRAFT_PRESENT'};
  const explicit = [];
  const neutral = [];
  inputs.forEach((el, index) => {
    if (el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true') return;
    const accepts = (el.getAttribute('accept') || '').toLowerCase().split(',').map(s => s.trim());
    if (accepts.some(s => s.startsWith('video/') || /^\.(mp4|mov|m4v|webm)$/.test(s))) explicit.push(index);
    else if (accepts.every(s => !s || s === '*/*' || s === '*')) neutral.push(index);
  });
  const candidates = explicit.length ? explicit : neutral;
  if (candidates.length > 1) return {state: 'TIKTOK_UPLOAD_INPUT_AMBIGUOUS'};
  if (candidates.length === 1) return {state: 'READY', input_index: candidates[0]};
  return {state: 'WAITING'};
}"""

WAIT_FOR_UPLOAD_JS = "() => { const result = (" + UPLOAD_STATE_JS + ")(); return result.state === 'WAITING' ? false : result; }"
STOP_STATES = {"LOGIN_REQUIRED", "ACCOUNT_VERIFICATION", "PLATFORM_RATE_LIMIT_OR_RESTRICTION",
               "TIKTOK_UPLOAD_DRAFT_PRESENT", "TIKTOK_UPLOAD_INPUT_AMBIGUOUS", "UNEXPECTED_ORIGIN"}


def _trusted_origin(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == "tiktok.com" or host.endswith(".tiktok.com"))
    except ValueError:
        return False


def read_upload_state(page: Any) -> dict[str, Any]:
    if not _trusted_origin(page.url):
        return {"state": "UNEXPECTED_ORIGIN"}
    return page.locator("html").evaluate(UPLOAD_STATE_JS, timeout=3000)


def open_tiktok_video_upload(
    page: Any, ready_timeout_ms: int = 15_000, progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Try known routes only before upload; never click a page control."""
    attempts: list[dict[str, Any]] = []
    # Protect a caller's existing task tab if media has already been attached.
    if _trusted_origin(page.url):
        state = read_upload_state(page)
        if state["state"] in STOP_STATES:
            raise TikTokUploadEntryError(state["state"], "当前页面需要人工检查，未切换入口或上传素材。", attempts)
    for index, url in enumerate(TIKTOK_VIDEO_UPLOAD_URLS, 1):
        if progress:
            progress(f"正在检查 TikTok 视频上传入口（{index}/{len(TIKTOK_VIDEO_UPLOAD_URLS)}）")
        attempt: dict[str, Any] = {"requested_url": url}
        attempts.append(attempt)
        response = None
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as exc:
            # Browser/proxy/connection errors cannot be fixed by changing routes.
            if "timeout" not in type(exc).__name__.lower():
                raise
            attempt["navigation_timeout"] = True
        status = response.status if response is not None else None
        if status in {401, 403, 429}:
            code = "LOGIN_REQUIRED" if status == 401 else "PLATFORM_RATE_LIMIT_OR_RESTRICTION"
            attempt.update(state=code, http_status=status)
            raise TikTokUploadEntryError(code, "TikTok 返回登录或访问限制，请人工检查。", attempts)
        state = read_upload_state(page)
        if state["state"] in STOP_STATES:
            attempt["state"] = state["state"]
            raise TikTokUploadEntryError(state["state"], "当前页面需要人工检查，未继续切换入口。", attempts)
        if status is not None and status >= 400:
            attempt.update(state="HTTP_ERROR", http_status=status)
            continue
        if state["state"] == "WAITING":
            try:
                handle = page.wait_for_function(WAIT_FOR_UPLOAD_JS, timeout=max(1, min(ready_timeout_ms, 30_000)))
                handle.dispose()
            except Exception as exc:
                if "timeout" not in type(exc).__name__.lower():
                    raise
            state = read_upload_state(page)
        attempt["state"] = state["state"]
        if state["state"] in STOP_STATES:
            raise TikTokUploadEntryError(state["state"], "当前页面需要人工检查，未继续切换入口。", attempts)
        if state["state"] == "READY":
            return {"requested_url": url, "input_index": state["input_index"], "attempts": attempts}
    raise TikTokUploadEntryError(
        "TIKTOK_UPLOAD_ENTRY_UNAVAILABLE",
        "三个入口均未找到唯一可用的视频上传控件，请检查页面、网络或平台界面变化。", attempts,
    )


def attach_tiktok_video(page: Any, media_path: Any, entry: dict[str, Any], timeout_ms: int) -> None:
    state = read_upload_state(page)
    if state["state"] != "READY" or state["input_index"] != entry["input_index"]:
        raise TikTokUploadEntryError("TIKTOK_UPLOAD_ENTRY_CHANGED", "视频上传控件发生变化，请人工检查当前页面。", entry["attempts"])
    # Never switch routes after this call, even when the upload outcome is unknown.
    page.locator("input[type='file']").nth(state["input_index"]).set_input_files(str(media_path), timeout=timeout_ms)
