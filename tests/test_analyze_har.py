import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "website-to-api" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load_module(SCRIPTS / "analyze_har.py", "website_to_api_analyze_har")
capture = load_module(SCRIPTS / "capture_har.py", "website_to_api_capture_har")


def sample_har():
    return {
        "log": {
            "entries": [
                {
                    "_resourceType": "fetch",
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com/v1/items/12345?q=dune&limit=5&token=TOP_SECRET_QUERY",
                        "queryString": [],
                        "headers": [
                            {"name": "User-Agent", "value": "Mozilla/5.0 Example"},
                            {"name": "Authorization", "value": "Bearer TOP_SECRET_AUTH"},
                            {"name": "X-CSRF-Token", "value": "TOP_SECRET_CSRF"},
                            {"name": "Cookie", "value": "sessionid=TOP_SECRET_COOKIE; theme=dark"},
                            {"name": "Accept", "value": "application/json"},
                        ],
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "Content-Type", "value": "application/json"}],
                        "content": {
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "items": [{"id": 1, "title": "Dune"}],
                                    "access_token": "TOP_SECRET_RESPONSE",
                                    "apiKey": "TOP_SECRET_CAMEL_CASE",
                                }
                            ),
                        },
                    },
                },
                {
                    "_resourceType": "script",
                    "request": {
                        "method": "GET",
                        "url": "https://cdn.example.com/app.js",
                        "queryString": [],
                        "headers": [],
                    },
                    "response": {
                        "status": 200,
                        "content": {"mimeType": "application/javascript", "text": "alert(1)"},
                    },
                },
            ]
        }
    }


def test_analyzer_extracts_url_query_and_redacts_by_default():
    report = analyzer.analyze_har(sample_har(), hosts=["example.com"])
    assert report["endpoint_count"] == 1
    endpoint = report["endpoints"][0]
    assert endpoint["path_template"] == "/v1/items/{id}"
    assert set(endpoint["query_parameters"]) == {"q", "limit", "token"}
    assert "examples" not in endpoint["query_parameters"]["q"]
    assert endpoint["query_parameters"]["token"]["secret"] is True
    assert endpoint["pagination_parameters"] == ["limit"]
    assert report["auth"]["header_names"] == ["authorization", "x-csrf-token"]
    assert report["auth"]["cookie_names"] == ["sessionid", "theme"]
    assert endpoint["response_shape"]["access_token"] == "<redacted>"
    assert endpoint["response_shape"]["apiKey"] == "<redacted>"
    serialized = json.dumps(report)
    assert "TOP_SECRET" not in serialized
    assert "app.js" not in serialized


def test_examples_are_opt_in_and_secrets_remain_redacted():
    report = analyzer.analyze_har(sample_har(), include_examples=True)
    query = report["endpoints"][0]["query_parameters"]
    assert query["q"]["examples"] == ["dune"]
    assert query["token"]["examples"] == ["<redacted>"]
    headers = report["endpoints"][0]["request_headers"]
    assert headers["authorization"] == {"present": True, "secret": True}
    assert "TOP_SECRET" not in json.dumps(report)


def test_capture_sanitizer_preserves_names_not_values():
    sanitized = capture.sanitize_har(sample_har())
    serialized = json.dumps(sanitized)
    assert "TOP_SECRET" not in serialized
    request = sanitized["log"]["entries"][0]["request"]
    headers = {item["name"].lower(): item["value"] for item in request["headers"]}
    assert headers["authorization"] == "<redacted>"
    assert headers["cookie"] == "sessionid=<redacted>; theme=<redacted>"
    assert "token=%3Credacted%3E" in request["url"]
    response = sanitized["log"]["entries"][0]["response"]
    assert json.loads(response["content"]["text"])["access_token"] == "<redacted>"


def test_local_browser_launch_falls_back_to_system_chrome():
    class Chromium:
        def __init__(self):
            self.calls = []

        def launch(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RuntimeError("Executable doesn't exist")
            return "browser"

    class Playwright:
        chromium = Chromium()

    playwright = Playwright()
    assert capture.launch_local_browser(playwright, headed=False, channel=None) == "browser"
    assert playwright.chromium.calls == [
        {"headless": True},
        {"headless": True, "channel": "chrome"},
    ]
