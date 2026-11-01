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
    def test_run_one_uses_ascii_prompt_flag_and_writes_frontmatter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        md_content = (tmp_path / "q01.md").read_text(encoding="utf-8")
        assert md_content.startswith("---\n")
        assert 'query: "日本語の調査クエリ"' in md_content
        assert 'status: "OK"' in md_content
        assert "dead_links: 0" in md_content
        assert "unreachable_links: 0" in md_content
        assert "unverified_lines: 0" in md_content
        assert "> [検証サマリ] URL 0件 / 生存 0 / 404 0 / 確認不能 0 / 低品質 0 / 未検証行 0" in md_content

    def test_run_one_timeout_writes_stderr_log(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        monkeypatch.setattr(gemini_parallel.shutil, "which", lambda _: "gemini")

        def fake_run(cmd, *, input, capture_output, timeout, cwd, check=False):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout, stderr=b"partial stderr output")

        monkeypatch.setattr(gemini_parallel.subprocess, "run", fake_run)
        args = argparse.Namespace(max_lines=10, model="gemini-3.8-flash", timeout=5)
        res = gemini_parallel.run_one(2, "タイムアウト調査", tmp_path, args)

        assert res["ec"] == "timeout"
        err_log = (tmp_path / "q02.stderr.log").read_text(encoding="utf-8")
        assert "partial stderr output" in err_log

    def test_redirect_re_matches_base64_padding_and_postprocess_annotations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        redirect_with_padding = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ_token=="
        raw_text = (
            f"- 事実A | {redirect_with_padding} | 引用A\n"
            "- 事実B | https://www.ajinomoto.co.jp/ir/missing.pdf== | 引用B\n"
            "- 事実C | https://foo.blog.shinobi.jp/Entry/745/ | 引用C"
        )
        monkeypatch.setattr(
            gemini_parallel,
            "resolve_redirect",
            lambda u: "https://www.ajinomoto.co.jp/ir/valid.pdf" if u == redirect_with_padding else None,
        )

        def fake_alive(url: str, timeout: float = 5.0) -> tuple[bool, int | str]:
            if "missing.pdf" in url:
                return False, 404
            return True, 200

        monkeypatch.setattr(gemini_parallel, "check_url_alive", fake_alive)
        processed, dead_count, lq_count = gemini_parallel._postprocess_urls(raw_text)

        assert "https://www.ajinomoto.co.jp/ir/valid.pdf |" in processed
        assert "valid.pdf==" not in processed
        assert "https://www.ajinomoto.co.jp/ir/missing.pdf [DEAD-LINK: 404]" in processed
        assert "- [UNVERIFIED] 事実B |" in processed
        assert "https://foo.blog.shinobi.jp/Entry/745/ [LOW-QUALITY-DOMAIN]" in processed
        assert dead_count == 1
        assert lq_count == 1

    def test_p0_prefix_urls_and_repeated_urls_not_corrupted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        alive = {
            "https://x.test/a": (False, 404),
            "https://x.test/a/b": (False, 404),
            "https://x.test/ab": (False, 404),
            "https://ok.test/p": (True, 200),
        }
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: alive.get(u, (True, 200)))

        # 1. Exact reproduction case from FIX_REQUEST_round2.md
        text1 = "A https://x.test/a と B https://x.test/a/b と (https://ok.test/p) と https://x.test/a=="
        out1, dead1, lq1 = gemini_parallel._postprocess_urls(text1)
        assert out1 == (
            "A https://x.test/a [DEAD-LINK: 404] と "
            "B https://x.test/a/b [DEAD-LINK: 404] と "
            "(https://ok.test/p) と "
            "https://x.test/a [DEAD-LINK: 404]"
        )
        assert dead1 == 2
        assert lq1 == 0

        # 2. Non-slash prefix (/a vs /ab), Markdown link (R3-2: tag after ')'), Japanese period, and 3x repetition
        text2 = (
            "[link](https://x.test/a) と https://x.test/ab と "
            "文末https://x.test/a。さらに https://x.test/a"
        )
        out2, dead2, _ = gemini_parallel._postprocess_urls(text2)
        assert "[link](https://x.test/a) [DEAD-LINK: 404]" in out2
        assert "https://x.test/ab [DEAD-LINK: 404]" in out2
        assert "文末https://x.test/a [DEAD-LINK: 404]。" in out2
        assert out2.count("[DEAD-LINK: 404]") == 4
        assert dead2 == 2

    def test_p1_unverified_line_downgrade_and_unchecked_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        alive = {
            "https://x.test/dead": (False, 404),
            "https://x.test/ok": (True, 200),
            "https://x.test/waf": (True, 403),
            "https://x.test/down": (False, "UNREACHABLE"),
        }
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: alive.get(u, (True, 200)))

        text = (
            "- 死んだURLのみの行 | https://x.test/dead | 引用1\n"
            "- 404と200が併記された行 | https://x.test/dead https://x.test/ok | 引用2\n"
            "- WAF遮断の行 | https://x.test/waf | 引用3\n"
            "- 到達不能の行 | https://x.test/down | 引用4"
        )
        out, stats = gemini_parallel._postprocess_urls(text, return_stats=True)
        lines = out.splitlines()
        assert lines[0].startswith("- [UNVERIFIED] 死んだURLのみの行")
        assert "[UNVERIFIED]" not in lines[1]
        assert "https://x.test/waf [UNCHECKED: 403]" in lines[2]
        assert "https://x.test/down [UNCHECKED: UNREACHABLE]" in lines[3]
        assert stats["total_urls"] == 4
        assert stats["ok_links"] == 1
        assert stats["dead_links"] == 1
        assert stats["unreachable_links"] == 2
        assert stats["unverified_lines"] == 1

        # --no-unchecked-tags suppresses [UNCHECKED: ...]
        out_no_uchk, _ = gemini_parallel._postprocess_urls(text, no_unchecked_tags=True, return_stats=True)
        assert "[UNCHECKED:" not in out_no_uchk

    def test_p2_verify_quotes_and_p3_off_topic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))

        pages = {
            "https://ajinomoto.test/ir": {
                "status": "OK",
                "title": "味の素株式会社 2026年3月期 決算短信",
                "text": "当社の2024年1月29日付の事業譲渡において、売上高は1,200億円となりました。",
            },
            "https://subaru.test/news": {
                "status": "OK",
                "title": "SUBARU 新型車発表",
                "text": "アイサイト搭載モデルの販売が好調に推移しています。",
            },
        }
        monkeypatch.setattr(gemini_parallel, "_fetch_page_content", lambda u, timeout=10.0: pages[u])

        text = (
            "- 一致する行（全角半角揺れ） | https://ajinomoto.test/ir | ２０２４年１月２９日付の事業譲渡において\n"
            "- パラフレーズ不一致の行 | https://ajinomoto.test/ir | 2024年1月末に事業を売却した\n"
            "- 引用なしの行 | https://ajinomoto.test/ir | 該当なし\n"
            "- 無関係企業の行 | https://subaru.test/news | アイサイト搭載モデルの販売"
        )
        out, stats = gemini_parallel._postprocess_urls(
            text,
            verify_quotes=True,
            subjects=["味の素", "Ajinomoto"],
            return_stats=True,
        )
        lines = out.splitlines()
        assert "[QUOTE-MISMATCH]" not in lines[0] and "[NO-QUOTE]" not in lines[0]
        assert lines[1].startswith("- [QUOTE-MISMATCH] パラフレーズ不一致の行")
        assert lines[2].startswith("- [NO-QUOTE] 引用なしの行")
        assert "https://subaru.test/news [OFF-TOPIC]" in lines[3]
        assert stats["quote_mismatch"] == 1
        assert stats["no_quote"] == 1
        assert stats["off_topic_links"] == 1

    def test_p2_relative_file_and_out_dir_resolved_from_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        qfile = tmp_path / "rel_queries.txt"
        qfile.write_text("相対パスのテスト質問\n", encoding="utf-8")

        monkeypatch.setattr(gemini_parallel.shutil, "which", lambda _: "gemini")
        monkeypatch.setattr(
            gemini_parallel,
            "run_one",
            lambda idx, q, out_dir, args: {
                "idx": idx,
                "query": q,
                "ec": 0,
                "text": "回答テキスト",
                "path": out_dir / f"q{idx:02d}.md",
                "sec": 1,
                "dead_links": 1,
                "unverified_lines": 1,
            },
        )
        monkeypatch.setattr("sys.argv", ["gemini_parallel.py", "-f", "rel_queries.txt", "-o", "rel_out", "--preview", "0"])

        with pytest.raises(SystemExit) as exc_info:
            gemini_parallel.main()

        assert exc_info.value.code == 0
        assert (tmp_path / "rel_out").is_dir()
        stdout = capsys.readouterr().out
        assert "[WARN] dead=1 unverified=1" in stdout
        assert "WARN: 1件の調査に死んだURLを含む" in stdout


class TestUrlQualityAndLiveness:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.reddit.com/r/investing/comments/123", True),
            ("https://note.com/someuser/n/n12345", True),
            ("https://ameblo.jp/user/entry-1.html", True),
            ("https://foo.blog.shinobi.jp/Entry/745/", True),
            ("https://warnscan.com/article/1", True),
            ("https://sub.warn-news.com/post", True),
            ("https://chiebukuro.yahoo.co.jp/detail/q123", True),
            ("https://www.ajinomoto.co.jp/ir/library/", False),
            ("https://www.nikkei.com/article/DGXZQO", False),
        ],
    )
    def test_is_low_quality_url(self, url: str, expected: bool) -> None:
        assert gemini_webfetch.is_low_quality_url(url) is expected

    def test_clean_extracted_url_strips_trailing_garbage(self) -> None:
        assert (
            gemini_webfetch.clean_extracted_url("https://www.tradingkey.com/analysis/stocks/abc==")
            == "https://www.tradingkey.com/analysis/stocks/abc"
        )
        assert (
            gemini_webfetch.clean_extracted_url("https://example.com/report.pdf).")
            == "https://example.com/report.pdf"
        )

    def test_check_url_alive_detects_404_and_allows_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_urlopen(req, timeout=5.0):
            url = req.full_url
            if "dead404" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            if "forbidden403" in url:
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            return MagicMock(__enter__=lambda s: SimpleNamespace(status=200), __exit__=lambda *a: False)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert gemini_webfetch.check_url_alive("https://example.com/dead404") == (False, 404)
        assert gemini_webfetch.check_url_alive("https://example.com/forbidden403") == (True, 403)
        assert gemini_webfetch.check_url_alive("https://example.com/ok") == (True, 200)


class TestClientAndThinkingConfig:
    def test_normalize_thinking_level_minimal_fallback(self, capsys: pytest.CaptureFixture[str]) -> None:
        from google.genai import types

        lvl_flash = gemini_webfetch.normalize_thinking_level("minimal", "gemini-3.8-flash")
        assert lvl_flash == types.ThinkingLevel.LOW
        assert "フォールバック" in capsys.readouterr().err

        lvl_argon = gemini_webfetch.normalize_thinking_level("minimal", "gemini-4-argon")
        assert lvl_argon == types.ThinkingLevel.LOW
        assert "フォールバック" in capsys.readouterr().err

        lvl_lite = gemini_webfetch.normalize_thinking_level("minimal", "gemini-3.5-flash-lite")
        assert lvl_lite == types.ThinkingLevel.MINIMAL
        assert capsys.readouterr().err == ""

    def test_make_client_missing_creds_falls_back_to_api_key(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gemini_webfetch, "load_env", lambda _: None)
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "C:/nonexistent/missing-creds-12345.json")
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "dummy-api-key")
        monkeypatch.delenv("GEMINI_SKILL_FORCE_VERTEX", raising=False)

        captured_kwargs: dict = {}

        def fake_client(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(gemini_webfetch.genai, "Client", fake_client)
        gemini_webfetch.make_client()

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "GOOGLE_APPLICATION_CREDENTIALS file missing" in captured.err
        assert "creds file missing, falling back to API key" in captured.err
        assert "GOOGLE_APPLICATION_CREDENTIALS" not in gemini_webfetch.os.environ
        assert captured_kwargs == {"api_key": "dummy-api-key", "vertexai": False}

    def test_make_client_missing_creds_without_api_key_exits_cleanly(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(gemini_webfetch, "load_env", lambda _: None)
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "C:/nonexistent/missing-creds-12345.json")
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            gemini_webfetch.make_client()

        assert exc_info.value.code == 1
        err_out = capsys.readouterr().err
        assert "ERROR:" in err_out
        assert "GOOGLE_APPLICATION_CREDENTIALS" in err_out

    def test_make_client_vertex_when_no_api_key_or_forced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_webfetch, "load_env", lambda _: None)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
        monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

        captured_kwargs: dict = {}

        def fake_client(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(gemini_webfetch.genai, "Client", fake_client)
        gemini_webfetch.make_client()

        assert captured_kwargs["vertexai"] is True
        assert captured_kwargs["project"] == "my-gcp-project"
        assert captured_kwargs["location"] == "global"

    def test_extract_response_text_handles_value_error(self) -> None:
        class BlockedResponse:
            @property
            def text(self) -> str:
                raise ValueError("Candidate was blocked by safety settings")

        assert gemini_webfetch.extract_response_text(BlockedResponse()) == ""

    def test_fetch_as_json_output(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        import json

        monkeypatch.setattr(
            gemini_webfetch,
            "fetch_raw",
            lambda *args, **kwargs: {
                "text": "要約テキスト本文",
                "statuses": [{"status": "URL_RETRIEVAL_STATUS_SUCCESS", "retrieved_url": "https://example.com/a"}],
                "fetch_ok": True,
                "fetch_ng_reason": None,
                "requested_url": "https://example.com/a",
            },
        )
        gemini_webfetch.fetch("https://example.com/a", as_json=True)
        out = json.loads(capsys.readouterr().out)
        assert out["url"] == "https://example.com/a"
        assert out["text"] == "要約テキスト本文"
        assert out["fetch_ok"] is True

    def test_audit_grounding_non_web_chunk_not_marked_grounded(self) -> None:
        text = "A社の2025年度売上高は1,200億円に達した。"
        supports = [
            SimpleNamespace(
                segment=SimpleNamespace(text="A社の2025年度売上高は1,200億円に達した"),
                grounding_chunk_indices=[0],
            )
        ]
        # chunk_index_to_source is empty because chunk 0 was not a valid web chunk
        audit = gemini_websearch.audit_grounding(text, supports, [], {})
        assert audit["verified_segments"][0]["has_grounding"] is False
        assert audit["is_fully_grounded"] is False
        assert audit["ungrounded_snippets"] == ["A社の2025年度売上高は1,200億円に達した"]


class TestRound3Fixes:
    def test_r3_1_non_ascii_url_percent_encoding_and_particle_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checked: list[str] = []
        stat = {
            "https://ja.wikipedia.org/wiki/%E5%91%B3%E3%81%AE%E7%B4%A0": (False, 404),
            "https://x.test/%E5%91%B3": (True, 200),
            "https://x.test/a%E3%81%A8": (False, 404),
            "https://x.test/a": (True, 200),
        }

        def fake_alive(u: str, timeout: float = 5.0) -> tuple[bool, int | str]:
            checked.append(u)
            return stat.get(u, (True, 200))

        monkeypatch.setattr(gemini_parallel, "check_url_alive", fake_alive)

        # 1. Non-ASCII URL is percent-encoded for check_url_alive, kept readable in text
        out1, st1 = gemini_parallel._postprocess_urls(
            "出典 https://ja.wikipedia.org/wiki/味の素 を参照",
            return_stats=True,
        )
        assert checked == ["https://ja.wikipedia.org/wiki/%E5%91%B3%E3%81%AE%E7%B4%A0"]
        assert out1 == "出典 https://ja.wikipedia.org/wiki/味の素 [DEAD-LINK: 404] を参照"
        assert st1["dead_links"] == 1

        # 2. Already percent-encoded URL is not double-encoded
        checked.clear()
        out2, _ = gemini_parallel._postprocess_urls("参照 https://x.test/%E5%91%B3 です", return_stats=True)
        assert checked == ["https://x.test/%E5%91%B3"]
        assert out2 == "参照 https://x.test/%E5%91%B3 です"

        # 3. Attached particle fallback (https://x.test/aと -> 404 -> retries https://x.test/a -> 200)
        checked.clear()
        out3, st3 = gemini_parallel._postprocess_urls("参照 https://x.test/aと 比較", return_stats=True)
        assert "https://x.test/a%E3%81%A8" in checked
        assert "https://x.test/a" in checked
        assert "[DEAD-LINK:" not in out3
        assert out3 == "参照 https://x.test/aと 比較"
        assert st3["ok_links"] == 1
        assert st3["dead_links"] == 0

    def test_r3_2_markdown_links_and_images_place_tags_outside_paren(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stat = {
            "https://d.test/a": (False, 404),
            "https://d.test/img.png": (False, 404),
            "https://ok.test/p": (True, 200),
        }
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: stat.get(u, (True, 200)))

        text = "[出典](https://d.test/a) と ([注](https://ok.test/p)) と ![図](https://d.test/img.png)"
        out, _ = gemini_parallel._postprocess_urls(text, return_stats=True)
        assert out == (
            "[出典](https://d.test/a) [DEAD-LINK: 404] と "
            "([注](https://ok.test/p)) と "
            "![図](https://d.test/img.png) [DEAD-LINK: 404]"
        )

    def test_r3_3_markdown_table_rows_and_tag_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stat = {
            "https://d.test/b": (False, 404),
        }
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: stat.get(u, (True, 200)))

        table_text = (
            "| 項目 | 出典 | 引用 |\n"
            "|---|---|---|\n"
            "| 売却 | https://d.test/b | なし |\n"
            "* 箇条書き | https://d.test/b | なし\n"
            "1. 番号付き | https://d.test/b | なし\n"
            "通常行 | https://d.test/b | なし"
        )
        out, st = gemini_parallel._postprocess_urls(table_text, verify_quotes=True, return_stats=True)
        lines = out.splitlines()
        assert lines[0] == "| 項目 | 出典 | 引用 |"
        assert lines[1] == "|---|---|---|"
        assert lines[2] == "| [UNVERIFIED] [NO-QUOTE] 売却 | https://d.test/b [DEAD-LINK: 404] | なし |"
        assert lines[3].startswith("* [UNVERIFIED] [NO-QUOTE] 箇条書き |")
        assert lines[4].startswith("1. [UNVERIFIED] [NO-QUOTE] 番号付き |")
        assert lines[5].startswith("[UNVERIFIED] [NO-QUOTE] 通常行 |")
        assert st["unverified_lines"] == 4
        assert st["no_quote"] == 4

    def test_r3_4_quote_column_selection_in_4plus_columns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        pages = {
            "https://ok.test/p": {
                "status": "OK",
                "title": "味の素 ニュース",
                "text": "2024年4月30日に連雲港の吸収合併を発表した。譲渡先は如意情集団。",
                "truncated": False,
            }
        }
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: pages.get(u, {"status": "ERROR", "title": "", "text": "", "truncated": False}),
        )

        # 1. 4 columns: quote is column after URL (col 2), col 3 is remarks
        line1 = "* 合併 | https://ok.test/p | 譲渡先は如意情集団 | 備考"
        out1, st1 = gemini_parallel._postprocess_urls(line1, verify_quotes=True, return_stats=True)
        assert "[QUOTE-MISMATCH]" not in out1
        assert st1["quote_mismatch"] == 0

        # 2. URL in final column -> skipped (not marked [NO-QUOTE] or [QUOTE-MISMATCH])
        line2 = "* 合併 | 引用だけ | https://ok.test/p"
        out2, st2 = gemini_parallel._postprocess_urls(line2, verify_quotes=True, return_stats=True)
        assert "[NO-QUOTE]" not in out2 and "[QUOTE-MISMATCH]" not in out2
        assert st2["no_quote"] == 0 and st2["quote_mismatch"] == 0

        # 3. 4 columns with empty placeholder in quote column -> [NO-QUOTE]
        line3 = "* 合併 | https://ok.test/p | なし | 備考"
        out3, st3 = gemini_parallel._postprocess_urls(line3, verify_quotes=True, return_stats=True)
        assert out3.startswith("* [NO-QUOTE] 合併 |")
        assert st3["no_quote"] == 1

    def test_r3_5_conclusion_line_downgrade_and_banner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stat = {
            "https://d.test/a": (False, 404),
            "https://d.test/b": (False, 404),
            "https://ok.test/p": (True, 200),
        }
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: stat.get(u, (True, 200)))

        # 1. All URLs dead -> [CONCLUSION-UNVERIFIED] + warning in summary banner
        text_all_dead = "結論: 売却が確認された\n- 売却 | https://d.test/a | 売却した"
        out1, st1 = gemini_parallel._postprocess_urls(text_all_dead, return_stats=True)
        assert out1.splitlines()[0] == "結論: [CONCLUSION-UNVERIFIED] 売却が確認された"
        assert st1["conclusion_unverified"] is True
        banner1 = gemini_parallel._format_summary_banner(st1)
        assert "[警告] 根拠となる生存URLが不足しています" in banner1

        # 2. 0 URLs in response -> [CONCLUSION-UNVERIFIED]
        text_no_url = "【結論】一次資料から売却が確認された。\n- 詳細は不明"
        out2, st2 = gemini_parallel._postprocess_urls(text_no_url, return_stats=True)
        assert out2.splitlines()[0] == "【結論】 [CONCLUSION-UNVERIFIED] 一次資料から売却が確認された。"
        assert st2["conclusion_unverified"] is True

        # 3. >= 50% unverified fact lines -> [CONCLUSION-LOW-CONFIDENCE]
        text_half_dead = (
            "要約: 一部確認された\n"
            "- 事実1 | https://d.test/a | 引用1\n"
            "- 事実2 | https://ok.test/p | 引用2"
        )
        out3, st3 = gemini_parallel._postprocess_urls(text_half_dead, return_stats=True)
        assert out3.splitlines()[0] == "要約: [CONCLUSION-LOW-CONFIDENCE] 一部確認された"
        assert st3["conclusion_unverified"] is True

        # 4. < 50% unverified fact lines and >= 1 alive URL -> no conclusion tag
        text_mostly_ok = (
            "結論: 確認された\n"
            "- 事実1 | https://ok.test/p | 引用1\n"
            "- 事実2 | https://ok.test/p | 引用2\n"
            "- 事実3 | https://d.test/a | 引用3"
        )
        out4, st4 = gemini_parallel._postprocess_urls(text_mostly_ok, return_stats=True)
        assert "[CONCLUSION-" not in out4
        assert st4["conclusion_unverified"] is False

    def test_r3_6_ssrf_protection_blocks_private_loopback_and_redirects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        urlopen_called_urls: list[str] = []

        def fake_urlopen(req, timeout=5.0):
            url = req.full_url
            urlopen_called_urls.append(url)
            if "redirect-to-local.example.com" in url:
                raise urllib.error.HTTPError(
                    url, 302, "Found", {"Location": "http://127.0.0.1/admin"}, None
                )
            return MagicMock(
                __enter__=lambda s: SimpleNamespace(status=200, geturl=lambda: url, headers={}, read=lambda n=0: b""),
                __exit__=lambda *a: False,
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(
            gemini_webfetch.socket,
            "getaddrinfo",
            lambda host, port, *a, **kw: [(2, 1, 6, "", ("93.184.215.14", 0))],
        )

        # Direct private/loopback/link-local/localhost/integer IPs must be blocked BEFORE urlopen
        for unsafe_url in (
            "http://127.0.0.1/x",
            "http://10.0.0.5/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost/secret",
            "http://internal.local/api",
            "http://2130706433/",
            "http://0x7f000001/",
            "file:///etc/passwd",
        ):
            assert gemini_webfetch.is_safe_public_url(unsafe_url) is False
            assert gemini_webfetch.check_url_alive(unsafe_url) == (False, "BLOCKED")
            assert gemini_parallel._fetch_page_content(unsafe_url)["status"] == "BLOCKED"

        assert urlopen_called_urls == []

        # Redirect from public host to 127.0.0.1 is blocked without following
        assert gemini_webfetch.check_url_alive("https://redirect-to-local.example.com/start") == (False, "BLOCKED")
        assert gemini_parallel._fetch_page_content("https://redirect-to-local.example.com/start")["status"] == "BLOCKED"
        assert all("127.0.0.1" not in u for u in urlopen_called_urls)

        # file:// is not matched by RAW_URL_RE and http://127.0.0.1 is tagged [UNCHECKED: BLOCKED]
        out, st = gemini_parallel._postprocess_urls(
            "- ローカル | http://127.0.0.1/x | 引用\n- ファイル | file:///etc/passwd | 引用",
            return_stats=True,
        )
        assert "http://127.0.0.1/x [UNCHECKED: BLOCKED]" in out
        assert "file:///etc/passwd [UNCHECKED:" not in out
        assert st["unreachable_links"] == 1

    def test_r3_7_shift_jis_content_type_and_truncation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(gemini_parallel, "is_safe_public_url", lambda u: True)

        sjis_html = (
            '<html><head><meta charset="shift_jis"><title>味の素IR</title></head>'
            "<body><p>2024年4月30日に連雲港の吸収合併を発表した。</p></body></html>"
        ).encode("cp932")

        # > 2MB payload where the quote appears after 2MB
        prefix_2mb = b"<html><body>" + (b"A" * (gemini_parallel._MAX_FETCH_BYTES + 100))
        quote_at_3mb = "後半にある重要な引用文".encode()
        huge_html = prefix_2mb + quote_at_3mb + b"</body></html>"

        def fake_urlopen(req, timeout=10.0):
            url = req.full_url
            if "sjis.test" in url:
                headers = {"Content-Type": "text/html"}
                body = sjis_html
            elif "json.test" in url:
                headers = {"Content-Type": "application/json; charset=utf-8"}
                body = b'{"key": "value"}'
            else:
                headers = {"Content-Type": "text/html; charset=utf-8"}
                body = huge_html

            return MagicMock(
                __enter__=lambda s: SimpleNamespace(
                    status=200,
                    geturl=lambda: url,
                    headers=headers,
                    read=lambda n=None: body[:n] if n is not None else body,
                ),
                __exit__=lambda *a: False,
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        text = (
            "- SJIS一致 | https://sjis.test/ir | 連雲港の吸収合併を発表した\n"
            "- JSONスキップ | https://json.test/api | 任意の引用\n"
            "- 2MB超ページ | https://huge.test/big | 後半にある重要な引用文"
        )
        out, st = gemini_parallel._postprocess_urls(text, verify_quotes=True, return_stats=True)
        lines = out.splitlines()
        assert "[QUOTE-MISMATCH]" not in lines[0] and "[UNCHECKED" not in lines[0]
        assert lines[1].startswith("- [UNCHECKED: TYPE] JSONスキップ |")
        assert lines[2].startswith("- [UNCHECKED: TRUNCATED] 2MB超ページ |")
        assert st["quote_mismatch"] == 0

    def test_r3_8_strip_agent_reasoning(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 1. Leading thought + CRITICAL INSTRUCTION lines stripped
        leaked = (
            "💡thought\n"
            "CRITICAL INSTRUCTION 1: ALWAYS prioritize custom tools. I will use `google_web_search`.\n"
            'CRITICAL INSTRUCTION 2: Related tools: `google_web_search`. I\'m querying about "味の素" or similar.\n'
            "結論: 味の素のヘイワード工場は売却されていません。\n"
            "- 事実1 | https://ok.test/p | 引用1"
        )
        cleaned, count = gemini_parallel._strip_agent_reasoning(leaked)
        assert count == 3
        assert cleaned.startswith("結論: 味の素のヘイワード工場は売却されていません。")

        # 2. CRITICAL INSTRUCTION inside the body is NOT stripped
        mid_body = (
            "結論: 正常な回答です。\n"
            "- 引用に CRITICAL INSTRUCTION を含む行 | https://ok.test/p | CRITICAL INSTRUCTION"
        )
        cleaned_mid, count_mid = gemini_parallel._strip_agent_reasoning(mid_body)
        assert count_mid == 0
        assert cleaned_mid == mid_body

        # 3. Only reasoning lines -> keeps original text and sets status OK(empty-after-strip) in run_one
        only_thought = (
            "💡thought\n"
            "CRITICAL INSTRUCTION 1: I will use `google_web_search`."
        )
        cleaned_only, count_only = gemini_parallel._strip_agent_reasoning(only_thought)
        assert cleaned_only == only_thought
        assert count_only == 0

        monkeypatch.setattr(gemini_parallel.shutil, "which", lambda _: "gemini")
        monkeypatch.setattr(
            gemini_parallel.subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(stdout=only_thought.encode("utf-8"), stderr=b"", returncode=0),
        )
        args = argparse.Namespace(max_lines=10, model="gemini-3.8-flash", timeout=30)
        res = gemini_parallel.run_one(1, "思考のみクエリ", tmp_path, args)
        md = (tmp_path / "q01.md").read_text(encoding="utf-8")
        assert 'status: "OK(empty-after-strip)"' in md
        assert "CRITICAL INSTRUCTION 1" in res["text"]


class TestRound4Fixes:
    """Round 4: R4-1 (_decode_html_bytes の未宣言 EUC-JP / ISO-2022-JP / 誤宣言フォールバック) の受け入れテスト10件"""

    S = "譲渡先は如意情集団を味の素へ"

    def test_r4_1_case01_cp932_undeclared(self) -> None:
        assert gemini_parallel._decode_html_bytes(self.S.encode("cp932"), "") == self.S

    def test_r4_1_case02_euc_jp_undeclared(self) -> None:
        assert gemini_parallel._decode_html_bytes(self.S.encode("euc_jp"), "") == self.S

    def test_r4_1_case03_iso2022_jp_undeclared(self) -> None:
        assert gemini_parallel._decode_html_bytes(self.S.encode("iso2022_jp"), "") == self.S

    def test_r4_1_case04_utf8_undeclared(self) -> None:
        assert gemini_parallel._decode_html_bytes(self.S.encode("utf-8"), "") == self.S

    def test_r4_1_case05_euc_jp_with_content_type(self) -> None:
        assert (
            gemini_parallel._decode_html_bytes(self.S.encode("euc_jp"), "text/html; charset=EUC-JP")
            == self.S
        )

    def test_r4_1_case06_cp932_with_meta_charset(self) -> None:
        raw = b'<meta charset="Shift_JIS">' + self.S.encode("cp932")
        out = gemini_parallel._decode_html_bytes(raw, "")
        assert self.S in out

    def test_r4_1_case07_cp932_with_wrong_utf8_declaration(self) -> None:
        assert (
            gemini_parallel._decode_html_bytes(self.S.encode("cp932"), "text/html; charset=utf-8")
            == self.S
        )

    def test_r4_1_case08_ascii_only(self) -> None:
        assert gemini_parallel._decode_html_bytes(b"<html>hello</html>", "") == "<html>hello</html>"

    def test_r4_1_case09_full_euc_jp_html_undeclared_quote_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        html_bytes = (
            f"<html><head><title>味の素</title></head><body><p>{self.S}</p></body></html>".encode(
                "euc_jp"
            )
        )
        monkeypatch.setattr(gemini_parallel, "is_safe_public_url", lambda u: True)
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout=10.0: MagicMock(
                __enter__=lambda s: SimpleNamespace(
                    status=200,
                    geturl=lambda: "https://euc.test/ir",
                    headers={"Content-Type": "text/html"},
                    read=lambda n=None: html_bytes[:n] if n is not None else html_bytes,
                ),
                __exit__=lambda *a: False,
            ),
        )
        page = gemini_parallel._fetch_page_content("https://euc.test/ir")
        assert page["status"] == "OK"
        assert page["title"] == "味の素"
        assert self.S in page["text"]

        out, st = gemini_parallel._postprocess_urls(
            "- 事業譲渡 | https://euc.test/ir | 譲渡先は如意情集団",
            verify_quotes=True,
            return_stats=True,
        )
        assert "[QUOTE-MISMATCH]" not in out
        assert st["quote_mismatch"] == 0

    def test_r4_1_case10_huge_2mb_euc_jp_undeclared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _time

        chunk = f"<p>{self.S}</p>\n".encode("euc_jp")
        repeats = (2 * 1024 * 1024 // len(chunk)) + 500
        huge_bytes = (
            "<html><head><title>味の素</title></head><body>".encode("euc_jp")
            + (chunk * repeats)
            + b"</body></html>"
        )
        assert len(huge_bytes) > 2 * 1024 * 1024

        monkeypatch.setattr(gemini_parallel, "is_safe_public_url", lambda u: True)
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout=10.0: MagicMock(
                __enter__=lambda s: SimpleNamespace(
                    status=200,
                    geturl=lambda: "https://euc.test/huge",
                    headers={"Content-Type": "text/html"},
                    read=lambda n=None: huge_bytes[:n] if n is not None else huge_bytes,
                ),
                __exit__=lambda *a: False,
            ),
        )
        t0 = _time.perf_counter()
        page = gemini_parallel._fetch_page_content("https://euc.test/huge")
        elapsed = _time.perf_counter() - t0
        assert elapsed < 1.0
        assert page["status"] == "OK"
        assert page["truncated"] is True
        assert page["title"] == "味の素"
        assert self.S in page["text"]


class TestRound5Fixes:
    """Round 5: R5-1 (引用突合失敗行の unsupported_lines 集計・結論確度判定・サマリ/警告バナー) 受け入れテスト11件"""

    def test_r5_1_case01_repro_one_dead_two_quote_mismatch_unverified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gemini_parallel,
            "check_url_alive",
            lambda u, timeout=5.0: (False, 404) if "dead" in u else (True, 200),
        )
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "一覧",
                "text": "製造拠点の一覧ページ",
                "truncated": False,
            },
        )
        text = (
            "結論: ヘイワード工場は2025年に売却されました。\n"
            "- 売却の事実 | https://x.test/dead.pdf | 2025年 Hayward工場を売却\n"
            "- 対象拠点 | https://x.test/index.html | ヘイワード工場\n"
            "- 費用計上 | https://x.test/index2.html | 構造改革費用"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert out.splitlines()[0] == "結論: [CONCLUSION-UNVERIFIED] ヘイワード工場は2025年に売却されました。"
        assert st["conclusion_unverified"] is True
        assert st["unsupported_lines"] == 3

    def test_r5_1_case02_one_match_two_quote_mismatch_low_confidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "IR資料",
                "text": "売上高は1000億円であった。",
                "truncated": False,
            },
        )
        text = (
            "結論: 業績と工場売却が確認されました。\n"
            "- 売上高 | https://x.test/1.html | 売上高は1000億円であった\n"
            "- 拠点売却 | https://x.test/2.html | ヘイワード工場を売却\n"
            "- 費用計上 | https://x.test/3.html | 構造改革費用を計上"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert out.splitlines()[0] == "結論: [CONCLUSION-LOW-CONFIDENCE] 業績と工場売却が確認されました。"
        assert st["conclusion_unverified"] is True
        assert st["unsupported_lines"] == 2

    def test_r5_1_case03_two_match_one_quote_mismatch_no_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "IR資料",
                "text": "売上高は1000億円であった。営業利益は150億円であった。",
                "truncated": False,
            },
        )
        text = (
            "結論: 業績が確認されました。\n"
            "- 売上高 | https://x.test/1.html | 売上高は1000億円であった\n"
            "- 営業利益 | https://x.test/2.html | 営業利益は150億円であった\n"
            "- 拠点売却 | https://x.test/3.html | ヘイワード工場を売却"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert out.splitlines()[0] == "結論: 業績が確認されました。"
        assert "[CONCLUSION-" not in out
        assert st["conclusion_unverified"] is False
        assert st["unsupported_lines"] == 1

    def test_r5_1_case04_three_no_quote_all_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "IR",
                "text": "本文テキスト",
                "truncated": False,
            },
        )
        text = (
            "結論: 売却されました。\n"
            "- 事実1 | https://x.test/1.html | なし\n"
            "- 事実2 | https://x.test/2.html | -\n"
            "- 事実3 | https://x.test/3.html | 該当なし"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert out.splitlines()[0] == "結論: [CONCLUSION-UNVERIFIED] 売却されました。"
        assert st["conclusion_unverified"] is True
        assert st["unsupported_lines"] == 3
        assert st["no_quote"] == 3

    def test_r5_1_case05_one_unchecked_403_two_quote_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gemini_parallel,
            "check_url_alive",
            lambda u, timeout=5.0: (True, 403) if "waf" in u else (True, 200),
        )
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "一覧",
                "text": "無関係な本文",
                "truncated": False,
            },
        )
        text = (
            "結論: 売却されました。\n"
            "- WAF行 | https://x.test/waf.html | 引用A\n"
            "- 不一致1 | https://x.test/1.html | 存在しない引用1\n"
            "- 不一致2 | https://x.test/2.html | 存在しない引用2"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert out.splitlines()[0] == "結論: [CONCLUSION-LOW-CONFIDENCE] 売却されました。"
        assert st["conclusion_unverified"] is True
        assert st["unsupported_lines"] == 2

    def test_r5_1_case06_three_unchecked_403_no_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 403))
        text = (
            "結論: 確認中。\n"
            "- WAF1 | https://x.test/waf1.html | 引用1\n"
            "- WAF2 | https://x.test/waf2.html | 引用2\n"
            "- WAF3 | https://x.test/waf3.html | 引用3"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        assert "[CONCLUSION-" not in out
        assert st["conclusion_unverified"] is False
        assert st["unsupported_lines"] == 0

    def test_r5_1_case07_without_verify_quotes_three_alive_no_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        text = (
            "結論: 売却されました。\n"
            "- 事実1 | https://x.test/1.html | 存在しない引用1\n"
            "- 事実2 | https://x.test/2.html | 存在しない引用2\n"
            "- 事実3 | https://x.test/3.html | 存在しない引用3"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=False)
        assert "[CONCLUSION-" not in out
        assert "[QUOTE-MISMATCH]" not in out
        assert st["conclusion_unverified"] is False
        assert st["unsupported_lines"] == 0

    def test_r5_1_case08_both_unverified_and_quote_mismatch_counted_once_per_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gemini_parallel,
            "check_url_alive",
            lambda u, timeout=5.0: (False, 404) if "dead" in u else (True, 200),
        )
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "IR",
                "text": "正しい引用テキスト",
                "truncated": False,
            },
        )
        # 1行に [UNVERIFIED] と [QUOTE-MISMATCH] が両方付く行が2行 + 一致1行
        text = (
            "結論: テスト結論です。\n"
            "- [QUOTE-MISMATCH] 事実1 | https://x.test/dead1.html | 誤引用1\n"
            "- [UNVERIFIED] 事実2 | https://x.test/ok2.html | 誤引用2\n"
            "- 事実3 | https://x.test/ok3.html | 正しい引用テキスト"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        lines = out.splitlines()
        assert "[UNVERIFIED]" in lines[1] and "[QUOTE-MISMATCH]" in lines[1]
        assert "[UNVERIFIED]" in lines[2] and "[QUOTE-MISMATCH]" in lines[2]
        assert st["unsupported_lines"] == 2
        assert lines[0] == "結論: [CONCLUSION-LOW-CONFIDENCE] テスト結論です。"
        assert st["conclusion_unverified"] is True

    def test_r5_1_case09_multiple_conclusion_lines_all_tagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gemini_parallel, "check_url_alive", lambda u, timeout=5.0: (True, 200))
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "IR",
                "text": "無関係な本文",
                "truncated": False,
            },
        )
        text = (
            "結論: ヘイワード工場は売却されました。\n"
            "- 事実1 | https://x.test/1.html | 存在しない引用1\n"
            "- 事実2 | https://x.test/2.html | 存在しない引用2\n"
            "結論: ヘイワード工場は売却されました。"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        lines = out.splitlines()
        assert lines[0] == "結論: [CONCLUSION-UNVERIFIED] ヘイワード工場は売却されました。"
        assert lines[3] == "結論: [CONCLUSION-UNVERIFIED] ヘイワード工場は売却されました。"
        assert st["conclusion_unverified"] is True

    def test_r5_1_case10_summary_banner_format_and_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gemini_parallel,
            "check_url_alive",
            lambda u, timeout=5.0: (False, 404) if "dead" in u else (True, 200),
        )
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "一覧",
                "text": "製造拠点の一覧ページ",
                "truncated": False,
            },
        )
        text = (
            "結論: ヘイワード工場は2025年に売却されました。\n"
            "- 売却の事実 | https://x.test/dead.pdf | 2025年 Hayward工場を売却\n"
            "- 対象拠点 | https://x.test/index.html | ヘイワード工場\n"
            "- 空引用 | https://x.test/index2.html | なし"
        )
        out, st = gemini_parallel._postprocess_urls(text, return_stats=True, verify_quotes=True)
        banner = gemini_parallel._format_summary_banner(st)
        body_qm_tags = out.count("[QUOTE-MISMATCH]") + out.count("[NO-QUOTE]")
        body_unsupported_lines = sum(
            1
            for ln in out.splitlines()
            if any(t in ln for t in ("[UNVERIFIED]", "[QUOTE-MISMATCH]", "[NO-QUOTE]"))
        )
        assert body_qm_tags == 2
        assert body_unsupported_lines == 3
        assert f"未検証行 1 / 引用不一致 {body_qm_tags} / 裏付けなし {body_unsupported_lines}" in banner

    def test_r5_1_case11_warning_messages_frontmatter_and_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            gemini_parallel,
            "check_url_alive",
            lambda u, timeout=5.0: (False, 404) if "dead" in u else (True, 200),
        )
        monkeypatch.setattr(
            gemini_parallel,
            "_fetch_page_content",
            lambda u, timeout=10.0: {
                "status": "OK",
                "title": "一覧",
                "text": "製造拠点の一覧ページ",
                "truncated": False,
            },
        )

        # 1. 引用不一致由来の判定（および両方該当する場合）は新しい警告文面のみを出す
        text_qm = (
            "結論: 売却されました。\n"
            "- 死リンク | https://x.test/dead.pdf | 売却\n"
            "- 引用不一致1 | https://x.test/1.html | ヘイワード工場\n"
            "- 引用不一致2 | https://x.test/2.html | 構造改革費用"
        )
        _, st_qm = gemini_parallel._postprocess_urls(text_qm, return_stats=True, verify_quotes=True)
        banner_qm = gemini_parallel._format_summary_banner(st_qm)
        assert (
            "> [警告] 根拠行の多くで、URLが死んでいるか、引用がページに存在しません。"
            "結論は一次資料で未確認として扱ってください。"
        ) in banner_qm
        assert "根拠となる生存URLが不足しています" not in banner_qm

        # 2. 生存URL不足のみのときは従来の警告文面
        text_dead_only = (
            "結論: 売却されました。\n"
            "- 死リンク | https://x.test/dead.pdf | 売却"
        )
        _, st_dead = gemini_parallel._postprocess_urls(text_dead_only, return_stats=True, verify_quotes=False)
        banner_dead = gemini_parallel._format_summary_banner(st_dead)
        assert "> [警告] 根拠となる生存URLが不足しています。結論は一次資料で未確認として扱ってください。" in banner_dead
        assert "URLが死んでいるか、引用がページに存在しません" not in banner_dead

        # 3. フロントマター (unsupported_lines) と 標準出力 (quote-mismatch=n) の確認
        monkeypatch.setattr(gemini_parallel.shutil, "which", lambda _: "gemini")
        monkeypatch.setattr(
            gemini_parallel.subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(stdout=text_qm.encode("utf-8"), stderr=b"", returncode=0),
        )
        monkeypatch.setattr(
            "sys.argv",
            ["gemini_parallel.py", "-o", str(tmp_path), "--preview", "0", "--verify-quotes", "テスト質問"],
        )
        with pytest.raises(SystemExit) as exc_info:
            gemini_parallel.main()
        assert exc_info.value.code == 0
        stdout = capsys.readouterr().out
        assert "⚠ conclusion-unverified" in stdout
        assert "quote-mismatch=2" in stdout
        md_text = (tmp_path / "q01.md").read_text(encoding="utf-8")
        assert "unsupported_lines: 3\n" in md_text
        assert "conclusion_unverified: true\n" in md_text


