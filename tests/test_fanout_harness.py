from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FANOUT = ROOT / "scripts" / "fanout"
if str(FANOUT) not in sys.path:
    sys.path.insert(0, str(FANOUT))

from fanout_common import extract_json_object, normalize_docstring_keys  # noqa: E402
from insert_docstrings import insert_docstrings  # noqa: E402
from verify_item import verify  # noqa: E402

WORKER_SPEC = importlib.util.spec_from_loader(
    "fanout_worker", importlib.machinery.SourceFileLoader("fanout_worker", str(FANOUT / "fanout-worker"))
)
assert WORKER_SPEC is not None and WORKER_SPEC.loader is not None
fanout_worker = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(fanout_worker)


def test_normalize_docstring_keys_exact() -> None:
    assert normalize_docstring_keys({"Foo.bar": "doc"}, ["Foo.bar"]) == {"Foo.bar": "doc"}


def test_normalize_docstring_keys_dotted_prefix() -> None:
    assert normalize_docstring_keys({"pkg.module.Foo.bar": "doc"}, ["Foo.bar"]) == {"Foo.bar": "doc"}


def test_normalize_docstring_keys_ambiguous_suffix_errors() -> None:
    with pytest.raises(ValueError, match="ambiguous docstring key"):
        normalize_docstring_keys({"pkg.Foo.bar": "doc"}, ["bar", "Foo.bar"])


def test_extract_json_object_accepts_prose_fences_and_direct_map() -> None:
    text = 'Here is the JSON:\n```json\n{"Foo": "documents Foo"}\n```\nDone.'
    assert extract_json_object(text) == {"docstrings": {"Foo": "documents Foo"}}


def test_item_28_dotted_response_inserts_after_normalization() -> None:
    response_path = ROOT / "tests" / "fixtures" / "fanout" / "item-28-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))["docstrings"]
    item = {
        "path": "scrapy/core/downloader/handlers/ftp.py",
        "targets": [
            "FTPDownloadHandler",
            "FTPDownloadHandler.download_request",
            "ReceivedDataProtocol",
            "ReceivedDataProtocol.close",
            "ReceivedDataProtocol.dataReceived",
            "ReceivedDataProtocol.filename",
        ],
    }
    source = """
class FTPDownloadHandler:
    def download_request(self, request, spider):
        return request, spider


class ReceivedDataProtocol:
    @property
    def filename(self):
        return None

    def dataReceived(self, data):
        return data

    def close(self):
        return None
"""

    modified = insert_docstrings(source, item, response)
    tree = ast.parse(modified)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    ftp_method = classes["FTPDownloadHandler"].body[1]
    received = classes["ReceivedDataProtocol"]

    assert ast.get_docstring(classes["FTPDownloadHandler"]) == response["scrapy.core.downloader.handlers.ftp.FTPDownloadHandler"]
    assert ast.get_docstring(ftp_method) == response["scrapy.core.downloader.handlers.ftp.FTPDownloadHandler.download_request"]
    assert ast.get_docstring(received) == response["scrapy.core.downloader.handlers.ftp.ReceivedDataProtocol"]
    assert ast.get_docstring(received.body[1]) == response["scrapy.core.downloader.handlers.ftp.ReceivedDataProtocol.filename"]
    assert ast.get_docstring(received.body[2]) == response["scrapy.core.downloader.handlers.ftp.ReceivedDataProtocol.dataReceived"]
    assert ast.get_docstring(received.body[3]) == response["scrapy.core.downloader.handlers.ftp.ReceivedDataProtocol.close"]


def test_prompt_discloses_non_placeholder_threshold() -> None:
    item = {
        "path": "scrapy/utils/_download_handlers.py",
        "targets": ["NullCookieJar.set_cookie"],
    }
    source = """
class NullCookieJar:
    def set_cookie(self, cookie):
        pass
"""

    prompt = fanout_worker.prompt_for(
        item,
        source,
        "failed_check: non_placeholder\nreason: NullCookieJar.set_cookie docstring is too short or placeholder-like",
    )

    assert "at least 20 non-whitespace characters" in fanout_worker.SYSTEM
    assert "at least 20 non-whitespace characters" in prompt
    assert "- NullCookieJar.set_cookie  (docstring MUST contain each of these words: cookie)" in prompt


def test_item_01_failed_response_replays_non_placeholder_failure(tmp_path: pathlib.Path) -> None:
    response_path = ROOT / "tests" / "fixtures" / "fanout" / "item-01-attempt-2-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))["docstrings"]
    item = {
        "path": "scrapy/http/cookies.py",
        "targets": [
            "CookieJar",
            "CookieJar.add_cookie_header",
            "CookieJar.clear",
            "CookieJar.clear_session_cookies",
            "CookieJar.extract_cookies",
            "CookieJar.make_cookies",
            "CookieJar.set_cookie",
            "CookieJar.set_cookie_if_ok",
            "CookieJar.set_policy",
            "WrappedRequest.add_unredirected_header",
            "WrappedRequest.full_url",
            "WrappedRequest.get_full_url",
            "WrappedRequest.get_header",
            "WrappedRequest.get_host",
            "WrappedRequest.get_type",
            "WrappedRequest.has_header",
            "WrappedRequest.header_items",
            "WrappedRequest.host",
            "WrappedRequest.origin_req_host",
            "WrappedRequest.type",
            "WrappedRequest.unverifiable",
            "WrappedResponse",
            "WrappedResponse.get_all",
            "WrappedResponse.info",
            "_DummyLock.acquire",
            "_DummyLock.release",
        ],
    }
    source = """
class CookieJar:
    def extract_cookies(self, response, request):
        pass

    def add_cookie_header(self, request):
        pass

    def clear_session_cookies(self):
        pass

    def clear(self, domain=None, path=None, name=None):
        pass

    def set_policy(self, pol):
        pass

    def make_cookies(self, response, request):
        pass

    def set_cookie(self, cookie):
        pass

    def set_cookie_if_ok(self, cookie, request):
        pass


class _DummyLock:
    def acquire(self):
        pass

    def release(self):
        pass


class WrappedRequest:
    @property
    def full_url(self):
        pass

    def get_full_url(self):
        pass

    def get_host(self):
        pass

    def get_type(self):
        pass

    @property
    def host(self):
        pass

    @property
    def type(self):
        pass

    @property
    def unverifiable(self):
        pass

    @property
    def origin_req_host(self):
        pass

    def has_header(self, name):
        pass

    def get_header(self, name, default=None):
        pass

    def header_items(self):
        pass

    def add_unredirected_header(self, name, value):
        pass


class WrappedResponse:
    def info(self):
        pass

    def get_all(self, name, default=None):
        pass
"""

    result = _verify_response_against_source(tmp_path, item, source, response)

    assert result == {
        "passed": False,
        "failed_check": "non_placeholder",
        "reason": "CookieJar.set_cookie docstring is too short or placeholder-like",
    }


def test_item_24_failed_response_replays_non_placeholder_failure(tmp_path: pathlib.Path) -> None:
    response_path = ROOT / "tests" / "fixtures" / "fanout" / "item-24-attempt-2-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))["docstrings"]
    item = {
        "path": "scrapy/utils/_download_handlers.py",
        "targets": [
            "NullCookieJar.extract_cookies",
            "NullCookieJar.set_cookie",
            "get_dataloss_msg",
            "get_maxsize_msg",
            "get_warnsize_msg",
            "make_response",
            "normalize_bind_address",
        ],
    }
    source = """
class NullCookieJar:
    def extract_cookies(self, response, request):
        pass

    def set_cookie(self, cookie):
        pass


def make_response(
    url,
    status,
    headers,
    body=b"",
    flags=None,
    certificate=None,
    ip_address=None,
    protocol=None,
    stop_download=None,
):
    pass


def get_maxsize_msg(size, limit, request, *, expected):
    pass


def get_warnsize_msg(size, limit, request, *, expected):
    pass


def get_dataloss_msg(url):
    pass


def normalize_bind_address(value):
    pass
"""

    result = _verify_response_against_source(tmp_path, item, source, response)

    assert result == {
        "passed": False,
        "failed_check": "non_placeholder",
        "reason": "NullCookieJar.set_cookie docstring is too short or placeholder-like",
    }


def _verify_response_against_source(
    tmp_path: pathlib.Path, item: dict[str, object], source: str, response: dict[str, str]
) -> dict[str, object]:
    corpus = tmp_path / "corpus"
    source_path = corpus / pathlib.Path(str(item["path"]))
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    modified_path = tmp_path / "modified.py"
    modified_path.write_text(insert_docstrings(source, item, response), encoding="utf-8")
    return verify(corpus, item, modified_path)
