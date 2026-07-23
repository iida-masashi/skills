"""Shared fixtures: mock anaplan_sdk and heavy dependencies before import."""
import sys
import types
import unittest.mock as mock
from pathlib import Path

# anaplan_sdk をモック（インストール不要にする）
if "anaplan_sdk" not in sys.modules:
    _sdk = types.ModuleType("anaplan_sdk")
    _sdk.Client = mock.MagicMock()  # type: ignore[attr-defined]
    sys.modules["anaplan_sdk"] = _sdk

# libs/ ディレクトリをパスに追加
for _subdir in ["history_audit"]:
    _p = str(Path(__file__).parent.parent / "libs" / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)
