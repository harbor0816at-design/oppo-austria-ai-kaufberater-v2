from app.agent.graph import PresalesWorkflow
from app.api.chat import _is_competitor_comparison, _normalize_routing_message
from app.services.conversations import ConversationService


def test_chinese_competitor_comparison_normalizes_to_comparison_route():
    message = _normalize_routing_message("比较x9和三星s26")
    assert "OPPO Find X9" in message
    assert "Samsung" in message
    assert _is_competitor_comparison(message)
    assert PresalesWorkflow.classify_route(message) == "comparison"


def test_conversation_service_normalizes_json_strings():
    profile = ConversationService._normalize_profile('{"camera_priority": true}')
    messages = ConversationService._normalize_messages(
        '[{"role":"user","content":"相机"},{"role":"assistant","content":"好的"}]'
    )
    assert profile == {"camera_priority": True}
    assert messages == [
        {"role": "user", "content": "相机"},
        {"role": "assistant", "content": "好的"},
    ]


def test_conversation_service_rejects_malformed_history():
    assert ConversationService._normalize_profile("not-json") == {}
    assert ConversationService._normalize_messages("not-json") == []
