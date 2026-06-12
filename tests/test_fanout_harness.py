from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FANOUT = ROOT / "scripts" / "fanout"
if str(FANOUT) not in sys.path:
    sys.path.insert(0, str(FANOUT))

from fanout_common import normalize_docstring_keys  # noqa: E402
from insert_docstrings import insert_docstrings  # noqa: E402


def test_normalize_docstring_keys_exact() -> None:
    assert normalize_docstring_keys({"Foo.bar": "doc"}, ["Foo.bar"]) == {"Foo.bar": "doc"}


def test_normalize_docstring_keys_dotted_prefix() -> None:
    assert normalize_docstring_keys({"pkg.module.Foo.bar": "doc"}, ["Foo.bar"]) == {"Foo.bar": "doc"}


def test_normalize_docstring_keys_ambiguous_suffix_errors() -> None:
    with pytest.raises(ValueError, match="ambiguous docstring key"):
        normalize_docstring_keys({"pkg.Foo.bar": "doc"}, ["bar", "Foo.bar"])


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
