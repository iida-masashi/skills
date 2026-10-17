import argparse
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gemini_parallel
import gemini_webfetch
import gemini_websearch
import pytest


class TestHostAndFetchValidation:
    def test_registrable_domain_and_hosts_match(self) -> None:
        assert gemini_webfetch._registrable_domain("www.nikkei.com") == "nikkei.com"
        assert gemini_webfetch._registrable_domain("ir.company.co.jp") == "company.co.jp"
        assert gemini_webfetch._hosts_match("company.co.jp", "ir.company.co.jp") is True
        assert gemini_webfetch._hosts_match("docs.github.com", "github.com") is True
        assert gemini_webfetch._hosts_match("alpha.co.jp", "beta.co.jp") is False
        assert gemini_webfetch._hosts_match("example.com", "login.other.com") is False

    def test_is_fetch_ok_subdomain_redirect_accepted(self) -> None:
        statuses = [
            {
                "status": "URL_RETRIEVAL_STATUS_SUCCESS",
                "retrieved_url": "https://ir.example.co.jp/news/2026.html",
            }
        ]
        ok, reason = gemini_webfetch._is_fetch_ok(statuses, requested_url="https://www.example.co.jp/news")
        assert ok is True
        assert reason is None

    def test_is_fetch_ok_unresolved_grounding_redirect_accepted(self) -> None:
        redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ_test"
        statuses = [
            {
                "status": "URL_RETRIEVAL_STATUS_SUCCESS",
                "retrieved_url": "https://www.example.co.jp/fact",
            }
        ]
        ok, reason = gemini_webfetch._is_fetch_ok(statuses, requested_url=redirect_url)
        assert ok is True
        assert reason is None

    def test_is_fetch_ok_different_domain_rejected(self) -> None:
        statuses = [
            {
                "status": "URL_RETRIEVAL_STATUS_SUCCESS",
                "retrieved_url": "https://auth.login-provider.com/login",
            }
        ]
        ok, reason = gemini_webfetch._is_fetch_ok(statuses, requested_url="https://www.example.co.jp/secret")
        assert ok is False
        assert reason is not None
        assert "ホスト不一致" in reason


class TestEmptyQuoteAndCheckClaim:
    @pytest.mark.parametrize(
        "quote",
        ["", "   ", "なし", "該当なし", "記載なし", "N/A", "none", "null", "-", "「なし」"],
    )
    def test_is_empty_quote_placeholders(self, quote: str) -> None:
        assert gemini_webfetch._is_empty_quote(quote) is True

    def test_is_empty_quote_valid_text(self) -> None:
        assert gemini_webfetch._is_empty_quote("売上高は1,200億円であった。") is False

    def test_check_claim_raw_downgrades_placeholder_quote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_json = gemini_webfetch.CheckResult(
            items=[
                gemini_webfetch.CheckItem(
                    claim="売上高は100億円",
                    verdict="裏付けあり",
                    quote="該当なし",
                    detail="本文より確認",
                )
            ]
        ).model_dump_json()

        monkeypatch.setattr(
            gemini_webfetch,
            "fetch_raw",
            lambda *args, **kwargs: {
                "text": fake_json,
                "statuses": [{"status": "URL_RETRIEVAL_STATUS_SUCCESS", "retrieved_url": "https://example.com/ir"}],
                "fetch_ok": True,
                "fetch_ng_reason": None,
                "requested_url": "https://example.com/ir",
            },
        )
        res = gemini_webfetch.check_claim_raw("https://example.com/ir", "売上高は100億円", client=MagicMock())
        assert res["items"][0]["verdict"] == "不明"
        assert res["items"][0]["quote"] == ""
        assert "自動格下げ" in res["items"][0]["detail"]


class TestResolveRedirectAndRetry:
    def test_resolve_redirect_passthrough(self) -> None:
        url = "https://example.com/page"
        assert gemini_webfetch.resolve_redirect(url) == url

    def test_resolve_redirect_handles_relative_location(self) -> None:
        redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        headers = {"Location": "https://target.example.com/final"}
        http_err = urllib.error.HTTPError(redirect_url, 302, "Found", headers, None)

        mock_opener = MagicMock()
        mock_opener.open.side_effect = http_err

        with patch("urllib.request.build_opener", return_value=mock_opener):
            resolved = gemini_webfetch.resolve_redirect(redirect_url)
        assert resolved == "https://target.example.com/final"

    def test_generate_with_retry_recovers_from_429(self) -> None:
        client = MagicMock()
        err = Exception("429 RESOURCE_EXHAUSTED")
        expected_resp = SimpleNamespace(text="ok")
        client.models.generate_content.side_effect = [err, expected_resp]

        resp = gemini_webfetch.generate_with_retry(
            client,
            model="gemini-3.8-flash",
            contents="hello",
            config=MagicMock(),
            max_retries=3,
            base_delay=0.01,
        )
        assert resp is expected_resp
        assert client.models.generate_content.call_count == 2


class TestGroundingAuditAndVerifyClaim:
    def test_clean_for_match_strips_list_markers_and_links(self) -> None:
        raw = "  - **売上高**は[1,200億円](https://example.com/ir)に達した。 "
        assert gemini_websearch._clean_for_match(raw) == "売上高は1,200億円に達した"

        numbered = "1. 営業利益は前年比15%増となった。"
        assert gemini_websearch._clean_for_match(numbered) == "営業利益は前年比15%増となった"

    def test_audit_grounding_bullet_and_multi_segment(self) -> None:
        text = (
            "- A社の2025年度売上高は1,200億円に達した。\n"
            "- 前半の事実記述であり、後半の補足説明も出典にある。\n"
            "- 未裏付けの推測では2,500億円になる見込みだ。\n"
        )
        supports = [
            SimpleNamespace(
                segment=SimpleNamespace(text="A社の2025年度売上高は1,200億円に達した"),
                grounding_chunk_indices=[0],
            ),
            SimpleNamespace(
                segment=SimpleNamespace(text="前半の事実記述であり"),
                grounding_chunk_indices=[0],
            ),
            SimpleNamespace(
                segment=SimpleNamespace(text="後半の補足説明も出典にある"),
                grounding_chunk_indices=[0],
            ),
        ]
        sources = [{"title": "Example IR", "url": "https://example.com/ir", "resolved": True}]
        audit = gemini_websearch.audit_grounding(text, supports, sources, {0: 0})
        assert audit["is_fully_grounded"] is False
        assert audit["ungrounded_snippets"] == ["未裏付けの推測では2,500億円になる見込みだ"]

    def test_verify_claim_handles_missing_id_and_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        raw_supports = [
            SimpleNamespace(
                segment=SimpleNamespace(text="事実1のテキスト"),
                grounding_chunk_indices=[0],
            ),
            SimpleNamespace(
                segment=SimpleNamespace(text="事実2のテキスト"),
                grounding_chunk_indices=[0, 1],
            ),
        ]
        sources = [
            {"title": "Site A", "url": "https://a.example.com/doc", "resolved": True},
            {"title": "Site B", "url": "https://b.example.com/doc", "resolved": True},
        ]
        chunk_map = {0: 0, 1: 1}

        def fake_fetch_raw(url: str, **kwargs):
            if "b.example.com" in url:
                raise RuntimeError("network timeout")
            # Site A returns only id=0 and omits id=1
            payload = gemini_websearch.SegmentCheckResult(
                items=[
                    gemini_websearch.SegmentCheckItem(
                        id=0,
                        verdict="裏付けあり",
                        quote="事実1のテキストの原文引用",
                        detail="一致",
                    )
                ]
            ).model_dump_json()
            return {
                "text": payload,
                "statuses": [{"status": "URL_RETRIEVAL_STATUS_SUCCESS", "retrieved_url": url}],
                "fetch_ok": True,
                "fetch_ng_reason": None,
                "requested_url": url,
            }

        monkeypatch.setattr(gemini_websearch, "fetch_raw", fake_fetch_raw)
        res = gemini_websearch.verify_claim(raw_supports, sources, chunk_map, client=MagicMock())
        per_claim = {c["id"]: c["verdict"] for c in res["per_claim"]}
        assert per_claim[0] == "裏付けあり"
        assert per_claim[1] == "不明"


class TestGeminiParallel:
    def test_run_one_uses_ascii_prompt_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_parallel.shutil, "which", lambda _: "gemini")
        captured_cmd: list[str] = []
        captured_input: bytes = b""

        def fake_run(cmd, *, input, capture_output, timeout, cwd, check=False):
            nonlocal captured_cmd, captured_input
            captured_cmd = list(cmd)
            captured_input = input
            return SimpleNamespace(stdout="調査結果テキスト".encode(), stderr=b"", returncode=0)

        monkeypatch.setattr(gemini_parallel.subprocess, "run", fake_run)
        args = argparse.Namespace(max_lines=10, model="gemini-3.8-flash", timeout=30)
        res = gemini_parallel.run_one(1, "日本語の調査クエリ", tmp_path, args)

        assert res["ec"] == 0
        p_idx = captured_cmd.index("-p")
        assert captured_cmd[p_idx + 1].isascii()
        assert "日本語の調査クエリ" in captured_input.decode("utf-8")
