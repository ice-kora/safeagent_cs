"""pytest 配置与 fixtures。

本文件确保：
- _ENV_FILES_LOADED 在每个测试前被重置，避免跨测试 env 污染
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_env_files_loaded() -> None:
    """每个测试前重置 env 文件加载标志，确保 load_env_files 正常执行。"""
    import app.core.env as _env_mod

    _env_mod._ENV_FILES_LOADED = False
