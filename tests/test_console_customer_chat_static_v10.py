from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_console_contains_customer_chat_tab_and_demo_cases() -> None:
    html = (PROJECT_ROOT / "console" / "index.html").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "console" / "app.js").read_text(encoding="utf-8")

    assert "Customer Chat" in html
    assert "Debug Console" in html
    assert "chatTimeline" in html
    assert "checkpointList" in html
    assert "Prompt Injection 攻击" in app_js
    assert "/api/checkpoints" in app_js
    assert "/api/chat" in app_js
    assert "/api/confirm" in app_js


def test_console_static_files_do_not_embed_secret_markers() -> None:
    payload = "\n".join(
        [
            (PROJECT_ROOT / "console" / "index.html").read_text(encoding="utf-8"),
            (PROJECT_ROOT / "console" / "app.js").read_text(encoding="utf-8"),
            (PROJECT_ROOT / "console" / "style.css").read_text(encoding="utf-8"),
        ]
    ).lower()

    assert "safeagent_llm_api_key" not in payload
    assert "system prompt:" not in payload
    assert "bearer " not in payload
