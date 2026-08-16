#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.45"]
# ///
"""Capture a sanitized HAR from a local Playwright browser or a CDP session."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from analyze_har import is_sensitive_name, redact_mapping


def _redact_header_value(name: str, value: str) -> str:
    normalized = name.lower()
    if normalized == "cookie":
        names = [
            part.split("=", 1)[0].strip() for part in value.split(";") if "=" in part
        ]
        return "; ".join(f"{cookie_name}=<redacted>" for cookie_name in names)
    if normalized == "set-cookie":
        first = value.split(";", 1)[0]
        cookie_name = first.split("=", 1)[0].strip() if "=" in first else "cookie"
        return f"{cookie_name}=<redacted>"
    return "<redacted>" if is_sensitive_name(name) else value


def _header_items(headers: Any) -> Iterable[Dict[str, str]]:
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            yield {
                "name": str(name),
                "value": _redact_header_value(str(name), str(value)),
            }
    elif isinstance(headers, list):
        for item in headers:
            if not isinstance(item, Mapping) or "name" not in item:
                continue
            name = str(item["name"])
            yield {
                "name": name,
                "value": _redact_header_value(name, str(item.get("value", ""))),
            }


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [
        (name, "<redacted>" if is_sensitive_name(name) else value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    fragment = "<redacted>" if parsed.fragment else ""
    netloc = parsed.netloc
    if parsed.username is not None or parsed.password is not None:
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), fragment))


def _redact_body(text: Any, mime_type: str = "") -> Any:
    if not isinstance(text, str) or not text:
        return text
    if "json" in mime_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return json.dumps(redact_mapping(json.loads(text)), separators=(",", ":"))
        except (TypeError, ValueError):
            return "<opaque-redacted>"
    if "x-www-form-urlencoded" in mime_type.lower():
        return urlencode(
            [
                (name, "<redacted>" if is_sensitive_name(name) else value)
                for name, value in parse_qsl(text, keep_blank_values=True)
            ]
        )
    return "<opaque-redacted>"


def sanitize_har(har: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of the HAR with credential-bearing values removed."""
    clean = json.loads(json.dumps(har))
    entries = clean.get("log", {}).get("entries", [])
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        request = entry.get("request")
        if isinstance(request, dict):
            request["url"] = _redact_url(str(request.get("url", "")))
            request["headers"] = list(_header_items(request.get("headers", [])))
            for cookie in (
                request.get("cookies", [])
                if isinstance(request.get("cookies"), list)
                else []
            ):
                if isinstance(cookie, dict) and "value" in cookie:
                    cookie["value"] = "<redacted>"
            query = request.get("queryString")
            if isinstance(query, list):
                for item in query:
                    if isinstance(item, dict) and is_sensitive_name(
                        str(item.get("name", ""))
                    ):
                        item["value"] = "<redacted>"
            post_data = request.get("postData")
            if isinstance(post_data, dict):
                mime_type = str(post_data.get("mimeType", ""))
                if "text" in post_data:
                    post_data["text"] = _redact_body(post_data.get("text"), mime_type)
                params = post_data.get("params")
                if isinstance(params, list):
                    for item in params:
                        if isinstance(item, dict) and is_sensitive_name(
                            str(item.get("name", ""))
                        ):
                            item["value"] = "<redacted>"
        response = entry.get("response")
        if isinstance(response, dict):
            response["headers"] = list(_header_items(response.get("headers", [])))
            for cookie in (
                response.get("cookies", [])
                if isinstance(response.get("cookies"), list)
                else []
            ):
                if isinstance(cookie, dict) and "value" in cookie:
                    cookie["value"] = "<redacted>"
            content = response.get("content")
            if isinstance(content, dict) and "text" in content:
                content["text"] = _redact_body(
                    content.get("text"), str(content.get("mimeType", ""))
                )
    return clean


def load_actions(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("actions file must be a JSON array of objects")
    return data


def run_actions(page: Any, actions: Sequence[Mapping[str, Any]]) -> None:
    for action in actions:
        kind = str(action.get("type", ""))
        if kind == "fill":
            page.fill(str(action["selector"]), str(action.get("value", "")))
        elif kind == "click":
            page.click(str(action["selector"]))
        elif kind == "press":
            page.press(str(action["selector"]), str(action["key"]))
        elif kind == "goto":
            page.goto(str(action["url"]), wait_until="domcontentloaded")
        elif kind == "sleep":
            time.sleep(float(action.get("seconds", 1)))
        elif kind == "wait_for_selector":
            page.wait_for_selector(
                str(action["selector"]), timeout=int(action.get("timeout_ms", 15000))
            )
        else:
            raise ValueError(f"unsupported action type: {kind!r}")


def write_sanitized_har(har: Mapping[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(sanitize_har(har), ensure_ascii=False), encoding="utf-8"
    )
    os.chmod(destination, 0o600)


def launch_local_browser(playwright: Any, headed: bool, channel: Optional[str]) -> Any:
    """Launch a bundled browser, falling back to system Chrome when available."""
    launch_args: Dict[str, Any] = {"headless": not headed}
    if channel:
        launch_args["channel"] = channel
    try:
        return playwright.chromium.launch(**launch_args)
    except Exception as first_error:
        if channel or "Executable doesn't exist" not in str(first_error):
            raise
        try:
            return playwright.chromium.launch(headless=not headed, channel="chrome")
        except Exception as chrome_error:
            raise RuntimeError(
                "No compatible local browser was found. Run "
                "`uv run --with playwright playwright install chromium` or pass "
                "`--channel chrome`/`--channel msedge` for an installed browser."
            ) from chrome_error


def capture_local(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    destination = Path(args.output).expanduser().resolve()
    actions = load_actions(args.actions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".website-to-api-raw-", dir=destination.parent
    ) as raw_directory:
        raw_path = Path(raw_directory) / "capture.har"
        with sync_playwright() as playwright:
            browser = launch_local_browser(playwright, args.headed, args.channel)
            try:
                context_args: Dict[str, Any] = {
                    "record_har_path": str(raw_path),
                    "record_har_content": "embed",
                    "record_har_mode": "minimal",
                }
                if args.url_filter:
                    context_args["record_har_url_filter"] = args.url_filter
                context = browser.new_context(**context_args)
                try:
                    page = context.new_page()
                    page.goto(args.url, wait_until="domcontentloaded")
                    run_actions(page, actions)
                    time.sleep(args.wait)
                finally:
                    context.close()
            finally:
                browser.close()
        with raw_path.open(encoding="utf-8") as handle:
            write_sanitized_har(json.load(handle), destination)
    print(f"Wrote sanitized HAR: {destination}")
    print(
        "The HAR may still contain personal response data; keep it private and delete it when done."
    )
    return 0


def _all_headers(message: Any) -> Mapping[str, str]:
    try:
        return message.all_headers()
    except Exception:
        return message.headers


def _cdp_entry(request: Any, response: Any) -> Dict[str, Any]:
    response_headers = _all_headers(response) if response is not None else {}
    body_text = ""
    if response is not None:
        try:
            body_text = response.text()
        except Exception:
            body_text = ""
    request_headers = _all_headers(request)
    post_data = request.post_data
    parsed_url = urlsplit(request.url)
    return {
        "_resourceType": request.resource_type,
        "request": {
            "method": request.method,
            "url": request.url,
            "headers": list(_header_items(request_headers)),
            "queryString": [
                {"name": name, "value": value}
                for name, value in parse_qsl(parsed_url.query, keep_blank_values=True)
            ],
            "postData": (
                {
                    "mimeType": str(request_headers.get("content-type", "")),
                    "text": post_data,
                }
                if post_data
                else {}
            ),
        },
        "response": {
            "status": response.status if response is not None else 0,
            "headers": list(_header_items(response_headers)),
            "content": {
                "mimeType": str(response_headers.get("content-type", "")),
                "text": body_text,
            },
        },
    }


def capture_cdp(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    destination = Path(args.output).expanduser().resolve()
    actions = load_actions(args.actions)
    entries: List[Dict[str, Any]] = []
    attached_pages: set[int] = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        def attach(page: Any) -> None:
            identity = id(page)
            if identity in attached_pages:
                return
            attached_pages.add(identity)
            page.on(
                "response",
                lambda response: entries.append(_cdp_entry(response.request, response)),
            )

        for current_page in context.pages:
            attach(current_page)
        context.on("page", attach)
        page = context.pages[0] if context.pages else context.new_page()
        attach(page)
        if args.goto:
            page.goto(args.goto, wait_until="domcontentloaded")
        run_actions(page, actions)
        time.sleep(args.wait)
        # Do not close a browser owned by the CDP provider or user.

    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "website-to-api", "version": "1"},
            "entries": entries,
        }
    }
    write_sanitized_har(har, destination)
    print(f"Wrote sanitized HAR: {destination} ({len(entries)} entries)")
    print(
        "The HAR may still contain personal response data; keep it private and delete it when done."
    )
    return 0


def common_capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("output", help="Destination HAR path")
    parser.add_argument(
        "--actions", help="JSON file containing an ordered array of browser actions"
    )
    parser.add_argument(
        "--wait", type=float, default=3.0, help="Seconds to wait for late responses"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture a sanitized HAR for website API discovery."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    local = subparsers.add_parser(
        "local", help="Launch an isolated local Chromium browser"
    )
    local.add_argument("url")
    common_capture_arguments(local)
    local.add_argument("--headed", action="store_true")
    local.add_argument(
        "--channel", help="Installed Playwright channel, such as chrome or msedge"
    )
    local.add_argument("--url-filter", help="Playwright HAR URL filter pattern")
    local.set_defaults(handler=capture_local)

    cdp = subparsers.add_parser(
        "cdp", help="Attach to an explicitly authorized CDP browser"
    )
    cdp.add_argument("cdp_url")
    common_capture_arguments(cdp)
    cdp.add_argument("--goto", help="Navigate after attaching")
    cdp.set_defaults(handler=capture_cdp)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
