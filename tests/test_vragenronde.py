import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "scripts"))
import vragenronde as vr  # noqa: E402


def test_flat_list_gets_default_options():
    qs, skip = vr.validate_questions([{"id": "a", "q": "Keep it?"}])
    assert qs == [{"id": "a", "q": "Keep it?", "options": ["ja", "nee"]}]
    assert skip is None


def test_batch_options_apply_and_per_question_override():
    raw = {
        "options": ["keep", "drop", "merge"],
        "skip": "leave",
        "questions": [
            {"id": "a", "q": "First?"},
            {"id": "b", "q": "DB?", "options": ["postgres", "sqlite"]},
        ],
    }
    qs, skip = vr.validate_questions(raw)
    assert qs[0]["options"] == ["keep", "drop", "merge"]
    assert qs[1]["options"] == ["postgres", "sqlite"]
    assert skip == "leave"


def test_kop_and_meta_are_kept():
    qs, _ = vr.validate_questions(
        [{"id": "a", "q": "x", "kop": "Project", "meta": [{"text": "late", "tone": "warn"}]}]
    )
    assert qs[0]["kop"] == "Project"
    assert qs[0]["meta"][0]["tone"] == "warn"


@pytest.mark.parametrize(
    "raw, msg",
    [
        ([], "non-empty"),
        ("text", "JSON array"),
        ([{"id": "a"}], "'q'"),
        ([{"q": "x"}], "'id'"),
        ([{"id": "a", "q": "x"}, {"id": "a", "q": "y"}], "duplicate"),
        ([{"id": "a", "q": "x", "options": ["only"]}], ">=2"),
        ([{"id": "a", "q": "x", "options": [str(i) for i in range(10)]}], "max 9"),
        ([{"id": "a", "q": "x", "options": ["ok", {"label": "no value"}]}], "non-empty string"),
        ({"questions": []}, "non-empty 'questions'"),
    ],
)
def test_invalid_input_is_rejected(raw, msg):
    with pytest.raises(ValueError, match=msg):
        vr.validate_questions(raw)


def _start_server(questions):
    qjson = json.dumps({"questions": questions, "skip": None})
    result, done = {}, threading.Event()
    port = vr.pick_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), vr.make_handler(qjson, result, done))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}", result, done


def _post(url, body):
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5)


def test_server_serves_page_and_collects_answers():
    qs, _ = vr.validate_questions([{"id": "a", "q": "Keep it?"}])
    server, base, result, done = _start_server(qs)
    try:
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert "Keep" in page and "__QUESTIONS_JSON__" not in page

        _post(base + "/progress", b'{"a": "ja"}')
        assert result["answers"] == {"a": "ja"} and not done.is_set()

        _post(base + "/submit", b'{"a": "nee"}')
        assert done.wait(2) and result["answers"] == {"a": "nee"}
    finally:
        server.shutdown()
        server.server_close()


def test_server_rejects_bad_json_and_unknown_paths():
    server, base, result, _ = _start_server([{"id": "a", "q": "x", "options": ["ja", "nee"]}])
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(base + "/submit", b"[1, 2]")
        assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(base + "/other", b"{}")
        assert e.value.code == 404
        assert "answers" not in result
    finally:
        server.shutdown()
        server.server_close()
