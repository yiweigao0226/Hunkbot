"""
Tests for diff_processor.py
Run with: pytest tests/ -v
"""
from unittest.mock import MagicMock
from app.services.diff_processor import (
    _should_skip,
    _infer_language,
    _truncate_patch,
    process_pr_files,
)


# --- Unit tests for helper functions ---

def test_should_skip_lock_files():
    assert _should_skip("package-lock.json") is True
    assert _should_skip("yarn.lock") is True
    assert _should_skip("poetry.lock") is True


def test_should_skip_generated_files():
    assert _should_skip("src/proto/user_pb2.py") is True
    assert _should_skip("dist/bundle.min.js") is True


def test_should_not_skip_normal_files():
    assert _should_skip("src/auth/login.py") is False
    assert _should_skip("components/Button.tsx") is False


def test_infer_language():
    assert _infer_language("main.py") == "Python"
    assert _infer_language("App.tsx") == "TypeScript/React"
    assert _infer_language("main.go") == "Go"
    assert _infer_language("unknown.xyz") == ""


def test_truncate_patch_short():
    patch = "\n".join([f"line {i}" for i in range(10)])
    assert _truncate_patch(patch, 20) == patch  # no truncation needed


def test_truncate_patch_long():
    patch = "\n".join([f"line {i}" for i in range(100)])
    result = _truncate_patch(patch, 20)
    assert len(result.splitlines()) == 21  # 20 lines + truncation notice
    assert "truncated" in result


def test_truncate_patch_empty():
    assert _truncate_patch("", 100) == ""


# --- Integration-style test for process_pr_files ---

def _make_mock_file(filename, status="modified", patch="@@ -1,3 +1,4 @@\n+new line\n old line"):
    f = MagicMock()
    f.filename = filename
    f.status = status
    f.patch = patch
    f.additions = 1
    f.deletions = 0
    return f


def test_process_pr_files_filters_lock_files():
    pr = MagicMock()
    pr.get_files.return_value = [
        _make_mock_file("src/main.py"),
        _make_mock_file("package-lock.json"),
        _make_mock_file("yarn.lock"),
    ]
    pr.body = "Fix auth bug"
    pr.title = "Fix: login issue"
    pr.number = 42
    pr.user.login = "eva"
    pr.base.repo.full_name = "eva/myapp"
    pr.base.ref = "main"
    pr.head.ref = "fix/auth"

    ctx = process_pr_files(pr)

    assert len(ctx.files) == 1
    assert ctx.files[0].filename == "src/main.py"


def test_process_pr_files_skips_removed():
    pr = MagicMock()
    pr.get_files.return_value = [
        _make_mock_file("src/old.py", status="removed"),
        _make_mock_file("src/new.py", status="added"),
    ]
    pr.body = ""
    pr.title = "Refactor"
    pr.number = 1
    pr.user.login = "eva"
    pr.base.repo.full_name = "eva/myapp"
    pr.base.ref = "main"
    pr.head.ref = "refactor"

    ctx = process_pr_files(pr)

    assert len(ctx.files) == 1
    assert ctx.files[0].filename == "src/new.py"
