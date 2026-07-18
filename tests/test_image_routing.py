"""Guard for image-input routing in laap/llm_respond.

Aris's default model (deepseek) is not vision-capable; sending an image to it
errors at OpenRouter. When a request carries an image_url content part, the LLM
call must route to the vision model instead. Pins the detection + routing.
"""
from laap import llm_respond as lr

_IMG_MSG = {"role": "user", "content": [
    {"type": "text", "text": "這是什麼"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
]}
_TEXT_MSG = {"role": "user", "content": "純文字"}
_TEXT_PARTS = {"role": "user", "content": [{"type": "text", "text": "只有文字 part"}]}


def test_has_image_detects_image_url_part():
    assert lr._has_image([_TEXT_MSG, _IMG_MSG]) is True


def test_has_image_false_for_text():
    assert lr._has_image([_TEXT_MSG]) is False
    assert lr._has_image([_TEXT_PARTS]) is False   # list content but no image
    assert lr._has_image([]) is False
    assert lr._has_image(None) is False


def test_route_model_switches_to_vision_on_image():
    assert lr._route_model([_IMG_MSG], "deepseek-x") == lr._VISION_MODEL


def test_route_model_keeps_default_for_text():
    assert lr._route_model([_TEXT_MSG], "deepseek-x") == "deepseek-x"


def test_vision_model_env_override(monkeypatch):
    # the module reads NEURALIS_VISION_MODEL at import; the default must be a
    # real OpenRouter vision id, and routing must return whatever _VISION_MODEL is
    monkeypatch.setattr(lr, "_VISION_MODEL", "vendor/custom-vl")
    assert lr._route_model([_IMG_MSG], "d") == "vendor/custom-vl"
