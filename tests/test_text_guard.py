"""No agent or network calls: preserve UTF-8 and reject already lossy outgoing text."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("REASON_CHAT_HOME", tempfile.mkdtemp())
os.environ.setdefault("REASON_BIN", sys.executable)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rnc
import server
from text_guard import ENCODING_ERROR, TextEncodingError, encoding_issue

BAD = "@b-claude PI #883? PR ?? ?????. head 841fb72a CI 10? SUCCESS? ?????, ?? head ??? ??? P1(manual ?? ??)? P2(cleanup ?? ? ?? ?)? ?? ?? ??? ????? ?????."


class TextGuardTest(unittest.TestCase):
    def test_ascii_conversion_of_korean_report_is_detected(self):
        original = "@b-claude 다음 작업 진행 상태입니다. 검증 결과 확인했습니다. 아직 완료 조건은 남아 있습니다. 수정 후 새 검사를 진행하고 결과를 보고해 주세요."
        self.assertIsNone(encoding_issue(original))
        self.assertEqual(encoding_issue(original.encode("ascii", "replace").decode("ascii")), ENCODING_ERROR)
        self.assertEqual(encoding_issue(BAD), ENCODING_ERROR)

    def test_replacement_and_invalid_unicode(self):
        for text in ("검증 결과 \ufffd 손상", "unpaired \ud800"):
            self.assertEqual(encoding_issue(text), ENCODING_ERROR)

    def test_questions_code_and_quoted_evidence_are_allowed(self):
        for text in ("Why? What? Which? How?", "정말??? 확인해 주세요!", "你好·안녕·hello 🤖🐰",
                     "```js\nx = a ?? b; // ???? ???? ???? ????\n```", "`" + BAD + "`", "> " + BAD):
            self.assertIsNone(encoding_issue(text), repr(text))

    def test_local_file_check_never_contacts_the_server(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.object(rnc, "server_token") as contact, \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            p = Path(home) / "body.md"
            p.write_text("한글·中文·🤖 원문 보존", encoding="utf-8-sig")
            self.assertEqual(rnc.main(["text", "check", "--file", str(p)]), 0)
            p.write_text(BAD, encoding="utf-8")
            self.assertEqual(rnc.main(["text", "check", "--file", str(p)]), 1)
            p.write_bytes("한글".encode("cp949"))
            self.assertEqual(rnc.main(["text", "check", "--file", str(p)]), 1)
            contact.assert_not_called()

    def test_http_sends_reject_damage_before_any_side_effect(self):
        for route, request in (("/api/send", {"to":"pat/b-claude", "body":BAD}),
                               ("/api/rooms/send", {"id":"room", "body":BAD}),
                               ("/api/rooms/post", {"id":"room", "as":"b-claude", "body":BAD})):
            h = object.__new__(server.Handler)
            h.path, h.host_ok, h.read_json, h.send_json = route, lambda: True, lambda: request, mock.Mock()
            with mock.patch.object(server.ROOMS, "get", return_value={"group":True}), \
                    mock.patch.object(server, "send_one") as send, \
                    mock.patch.object(server.RELAY, "post_as") as post_as, mock.patch.object(server.RELAY, "post") as post:
                h.do_POST()
                self.assertEqual(h.send_json.call_args.args, ({"error":ENCODING_ERROR}, 400))
                send.assert_not_called(); post_as.assert_not_called(); post.assert_not_called()

    def test_http_preserves_korean_and_emoji_exactly(self):
        body = "한글·中文·emoji 🤖 원문 그대로"
        h = object.__new__(server.Handler)
        h.send_json = mock.Mock()
        with mock.patch.object(server, "send_one", return_value=(0,"","")) as send, \
                mock.patch.object(server, "dm_note", return_value=""):
            h.send_message({"to":"pat/b-claude", "body":body})
        send.assert_called_once_with("pat/b-claude", body, False)


if __name__ == "__main__":
    unittest.main()
