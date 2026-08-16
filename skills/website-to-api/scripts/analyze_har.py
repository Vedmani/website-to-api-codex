#!/usr/bin/env python3
"""Analyze a HAR into a redacted, machine-readable API discovery report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)
from urllib.parse import parse_qsl, urlsplit

STATIC_EXTENSIONS = re.compile(
    r"\.(?:avif|css|gif|ico|jpe?g|js|map|mp4|png|svg|ttf|webm|webp|woff2?)$",
    re.IGNORECASE,
)
UUID_OR_ID_SEGMENT = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,})$",
    re.IGNORECASE,
)
SENSITIVE_NAME = re.compile(
    r"(?:^|[-_])(?:auth(?:orization)?|cookie|credential|csrf|jwt|password|passwd|secret|session|token|xsrf|x-api-key|api-key)(?:$|[-_])",
    re.IGNORECASE,
)
SENSITIVE_COMPACT_FRAGMENTS = {
    "apikey",
    "authorization",
    "credential",
    "csrf",
    "password",
    "passwd",
    "privatekey",
    "samlresponse",
    "secret",
    "session",
    "signature",
    "token",
    "xsrf",
}
BORING_HEADERS = {
    "accept-encoding",
    "accept-language",
    "cache-control",
    "connection",
    "content-length",
    "host",
    "pragma",
    "priority",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "te",
    "upgrade-insecure-requests",
}
PAGINATION_NAMES = {
    "after",
    "before",
    "continuation",
    "cursor",
    "limit",
    "offset",
    "page",
    "page_size",
    "pagesize",
    "per_page",
}


def is_sensitive_name(name: str) -> bool:
    normalized = name.lower().strip()
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    return (
        bool(SENSITIVE_NAME.search(normalized))
        or any(fragment in compact for fragment in SENSITIVE_COMPACT_FRAGMENTS)
        or normalized
        in {
            "authorization",
            "code",
            "key",
            "proxy-authorization",
            "set-cookie",
            "sid",
            "sig",
        }
    )


def redact_mapping(value: Any, key: str = "") -> Any:
    """Recursively redact values whose field names look credential-bearing."""
    if key and is_sensitive_name(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(k): redact_mapping(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    return value


def json_shape(value: Any, depth: int = 0) -> Any:
    """Return a bounded structural description without retaining response values."""
    if depth >= 6:
        return "..."
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if not value:
            return []
        shapes = []
        for item in value[:3]:
            shape = json_shape(item, depth + 1)
            if shape not in shapes:
                shapes.append(shape)
        return shapes
    if isinstance(value, Mapping):
        return {
            str(k): "<redacted>"
            if is_sensitive_name(str(k))
            else json_shape(v, depth + 1)
            for k, v in list(value.items())[:100]
        }
    return type(value).__name__


def path_template(path: str) -> str:
    return "/".join(
        "{id}" if UUID_OR_ID_SEGMENT.match(segment) else segment
        for segment in path.split("/")
    )


def header_pairs(headers: Any) -> Iterable[Tuple[str, str]]:
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            yield str(name), str(value)
        return
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, Mapping) and "name" in item:
                yield str(item["name"]), str(item.get("value", ""))


def parse_json_text(text: Any) -> Optional[Any]:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def request_body_shape(request: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    post_data = request.get("postData")
    if not isinstance(post_data, Mapping):
        return None
    mime_type = str(post_data.get("mimeType", ""))
    text = post_data.get("text")
    parsed = parse_json_text(text)
    if parsed is not None:
        return {"mime_type": mime_type, "shape": json_shape(parsed)}
    params = post_data.get("params")
    if isinstance(params, list):
        names = [
            str(item.get("name"))
            for item in params
            if isinstance(item, Mapping) and item.get("name")
        ]
        return {"mime_type": mime_type, "form_fields": sorted(set(names))}
    if isinstance(text, str) and text:
        return {"mime_type": mime_type, "shape": "opaque-text"}
    return None


def response_body_shape(response: Mapping[str, Any]) -> Optional[Any]:
    content = response.get("content")
    if not isinstance(content, Mapping):
        return None
    parsed = parse_json_text(content.get("text"))
    return json_shape(parsed) if parsed is not None else None


def query_pairs(request: Mapping[str, Any], url: Any) -> List[Tuple[str, str]]:
    raw_query = request.get("queryString")
    pairs: List[Tuple[str, str]] = []
    if isinstance(raw_query, list):
        for item in raw_query:
            if isinstance(item, Mapping) and item.get("name") is not None:
                pairs.append((str(item["name"]), str(item.get("value", ""))))
    if not pairs:
        pairs = [
            (name, value)
            for name, value in parse_qsl(url.query, keep_blank_values=True)
        ]
    return pairs


def host_matches(hostname: Optional[str], filters: Sequence[str]) -> bool:
    """Match a host exactly or as a subdomain, never as an arbitrary substring."""
    candidate = (hostname or "").lower().rstrip(".")
    for raw_filter in filters:
        expected = raw_filter.lower().strip().rstrip(".")
        if candidate == expected or candidate.endswith(f".{expected}"):
            return True
    return False


def is_api_entry(entry: Mapping[str, Any]) -> bool:
    request = entry.get("request")
    if not isinstance(request, Mapping):
        return False
    response = entry.get("response")
    response = response if isinstance(response, Mapping) else {}
    content = response.get("content")
    content = content if isinstance(content, Mapping) else {}
    resource_type = str(entry.get("_resourceType", "")).lower()
    mime_type = str(content.get("mimeType", "")).lower()
    method = str(request.get("method", "GET")).upper()
    path = urlsplit(str(request.get("url", ""))).path
    if STATIC_EXTENSIONS.search(path):
        return False
    return (
        resource_type in {"xhr", "fetch"}
        or "json" in mime_type
        or method not in {"GET", "HEAD"}
    )


def append_unique(target: List[Any], value: Any) -> None:
    if value not in target:
        target.append(value)


def analyze_har(
    har: Mapping[str, Any],
    hosts: Sequence[str] = (),
    include_static: bool = False,
    include_examples: bool = False,
) -> Dict[str, Any]:
    log = har.get("log")
    if not isinstance(log, Mapping) or not isinstance(log.get("entries"), list):
        raise ValueError("HAR must contain log.entries as a list")

    groups: "OrderedDict[Tuple[str, str, str, str], Dict[str, Any]]" = OrderedDict()
    auth_headers: set[str] = set()
    cookie_names: set[str] = set()

    for entry in log["entries"]:
        if not isinstance(entry, Mapping):
            continue
        request = entry.get("request")
        if not isinstance(request, Mapping):
            continue
        url = urlsplit(str(request.get("url", "")))
        if url.scheme not in {"http", "https"} or not url.netloc:
            continue
        if hosts and not host_matches(url.hostname, hosts):
            continue
        if not include_static and not is_api_entry(entry):
            continue

        method = str(request.get("method", "GET")).upper()
        key = (method, url.scheme, url.netloc, path_template(url.path))
        group = groups.setdefault(
            key,
            {
                "method": method,
                "scheme": url.scheme,
                "host": url.netloc,
                "path_template": path_template(url.path),
                "observations": 0,
                "query_parameters": OrderedDict(),
                "request_headers": OrderedDict(),
                "request_body": None,
                "response_statuses": [],
                "response_content_types": [],
                "response_shape": None,
                "pagination_parameters": [],
            },
        )
        group["observations"] += 1

        for name, value in query_pairs(request, url):
            parameter = group["query_parameters"].setdefault(
                name,
                {"secret": is_sensitive_name(name)},
            )
            if include_examples:
                shown = "<redacted>" if is_sensitive_name(name) else value[:200]
                examples = parameter.setdefault("examples", [])
                append_unique(examples, shown)
            if name.lower() in PAGINATION_NAMES:
                append_unique(group["pagination_parameters"], name)

        for name, value in header_pairs(request.get("headers", [])):
            normalized = name.lower().lstrip(":")
            if normalized in {"cookie", "set-cookie"}:
                for part in value.split(";"):
                    cookie_name = part.split("=", 1)[0].strip()
                    if cookie_name:
                        cookie_names.add(cookie_name)
                group["request_headers"][normalized] = {"present": True, "secret": True}
                continue
            if is_sensitive_name(normalized):
                auth_headers.add(normalized)
                group["request_headers"][normalized] = {"present": True, "secret": True}
                continue
            if normalized in BORING_HEADERS or normalized.startswith("sec-"):
                continue
            group["request_headers"][normalized] = {
                "present": True,
                "secret": False,
            }
            if include_examples:
                group["request_headers"][normalized]["example"] = value[:200]

        body_shape = request_body_shape(request)
        if body_shape is not None and group["request_body"] is None:
            group["request_body"] = body_shape

        response = entry.get("response")
        if not isinstance(response, Mapping):
            continue
        status = response.get("status")
        if isinstance(status, int):
            append_unique(group["response_statuses"], status)
        content = response.get("content")
        if isinstance(content, Mapping):
            mime_type = str(content.get("mimeType", ""))
            if mime_type:
                append_unique(group["response_content_types"], mime_type)
        shape = response_body_shape(response)
        if shape is not None and group["response_shape"] is None:
            group["response_shape"] = shape

    return {
        "format_version": 1,
        "endpoint_count": len(groups),
        "auth": {
            "header_names": sorted(auth_headers),
            "cookie_names": sorted(cookie_names),
            "values_redacted": True,
            "auth_required": "unknown-until-replayed",
        },
        "endpoints": list(groups.values()),
    }


def render_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"Discovered {report.get('endpoint_count', 0)} API-looking endpoint(s).",
        "Credential values are redacted; auth requirement remains unknown until replayed.",
    ]
    auth = report.get("auth", {})
    if isinstance(auth, Mapping):
        if auth.get("header_names"):
            lines.append(
                "Auth-like headers present: " + ", ".join(auth["header_names"])
            )
        if auth.get("cookie_names"):
            lines.append("Cookie names present: " + ", ".join(auth["cookie_names"]))
    for index, endpoint in enumerate(report.get("endpoints", []), start=1):
        if not isinstance(endpoint, Mapping):
            continue
        lines.append("")
        lines.append(
            f"[{index}] {endpoint['method']} {endpoint['scheme']}://{endpoint['host']}"
            f"{endpoint['path_template']} (x{endpoint['observations']})"
        )
        query = endpoint.get("query_parameters", {})
        if query:
            lines.append("    query: " + ", ".join(sorted(query)))
        statuses = endpoint.get("response_statuses", [])
        if statuses:
            lines.append("    statuses: " + ", ".join(str(item) for item in statuses))
        if endpoint.get("pagination_parameters"):
            lines.append(
                "    pagination: " + ", ".join(endpoint["pagination_parameters"])
            )
        if endpoint.get("request_body"):
            lines.append("    request body schema captured")
        if endpoint.get("response_shape"):
            lines.append("    response JSON schema captured")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Distill a HAR into a redacted website API discovery report."
    )
    parser.add_argument("har", help="Input HAR file")
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Keep this host and its subdomains; repeat for multiple hosts",
    )
    parser.add_argument(
        "--include-static", action="store_true", help="Include non-API traffic"
    )
    parser.add_argument(
        "--include-examples",
        action="store_true",
        help="Include redacted non-secret query/header examples in the report",
    )
    parser.add_argument(
        "--output", "-o", help="Write output to this path instead of stdout"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with Path(args.har).expanduser().open(encoding="utf-8") as handle:
            har = json.load(handle)
        report = analyze_har(
            har,
            hosts=args.host,
            include_static=args.include_static,
            include_examples=args.include_examples,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    rendered = (
        json.dumps(report, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_text(report)
    )
    if args.output:
        destination = Path(args.output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote redacted discovery report: {destination}")
    else:
        print(rendered)
    return 0 if report["endpoint_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
