"""Automated-loop tests plus offline Chromium checks against the saved HTML."""
from datetime import date
from pathlib import Path
import re
import tempfile
import unittest

from automated_game import ContextoBrowser, classify_feedback, parse_date, ROOT
from gemini_trial import GameLog, run_game
from test_gemini_trial import Client, Response


class AutomationTests(unittest.TestCase):
    def test_date_formats(self):
        for value in ["2026-10-05", "05/10/2026", "05.10.2026"]:
            self.assertEqual(parse_date(value), date(2026, 10, 5))
        for value in ["2026-02-30", "", "10-05", "tomorrow"]:
            with self.assertRaises(ValueError):
                parse_date(value)

    def test_errors_are_not_silently_valid_guesses(self):
        self.assertEqual(classify_feedback({"kind": "error", "message": "Word not found"}), "invalid")
        for result in [{"kind": "error", "message": "Rate limit exceeded"},
                       {"kind": "rank", "rank": 34, "repeated": True}]:
            with self.assertRaises(RuntimeError):
                classify_feedback(result)

    def test_no_manual_input_in_automated_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            log = GameLog(Path(directory) / "run")
            client = Client([Response("water"), Response("material", "i2")])
            submissions = []
            def feedback(guess, turn):
                submissions.append((guess, turn))
                return 402 if turn == 1 else 1
            def forbidden(_):
                self.fail("Automatic mode requested terminal feedback")
            reason = run_game(client, log, "test", "2026-10-06", read=forbidden,
                              show=lambda _: None, get_feedback=feedback)
            self.assertEqual(reason, "success")
            self.assertEqual(submissions, [("water", 1), ("material", 2)])
            self.assertIn("water -> rank 402", client.requests[1]["input"])

    def test_browser_failure_preserves_game_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            log = GameLog(Path(directory) / "run")
            client = Client([Response("water")])
            def failed(guess, turn):
                raise RuntimeError("Site did not return fresh feedback")
            reason = run_game(client, log, "test", "2026-10-06", show=lambda _: None,
                              get_feedback=failed)
            self.assertEqual(reason, "browser_error")
            self.assertEqual(len(client.requests), 1)
            self.assertIn("Site did not return fresh feedback", log.path.read_text(encoding="utf-8"))


class SavedHtmlBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Playwright not installed")
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.context.route("**/*", lambda route: route.abort())
        self.page = self.context.new_page()
        self.log = GameLog(Path(self.temp.name) / "run")
        self.adapter = ContextoBrowser(self.page, self.log, timeout_ms=1000)

    def html(self, number):
        html = (ROOT / "html" / str(number) / "Contexto.html").read_text(encoding="utf-8")
        return re.sub(r"<script\b[^>]*>.*?</script\s*>", "", html, flags=re.DOTALL | re.IGNORECASE)

    def set_response(self, number):
        self.page.evaluate("""html => {
            document.querySelector('form').addEventListener('submit', event => {
                event.preventDefault();
                const saved = new DOMParser().parseFromString(html, 'text/html');
                document.querySelector('#root').innerHTML = saved.querySelector('#root').innerHTML;
            });
        }""", self.html(number))

    def test_rank_one_and_completion_from_snapshot_five(self):
        self.page.set_content(self.html(3), wait_until="domcontentloaded")
        self.set_response(5)
        self.assertEqual(self.adapter.submit("material", 1), 1)
        self.assertTrue((self.adapter.artifacts / "turn_01.html").exists())
        self.assertIn("material", self.log.path.read_text(encoding="utf-8"))

    def test_duplicate_from_snapshot_four(self):
        self.page.set_content(self.html(3), wait_until="domcontentloaded")
        self.set_response(4)
        with self.assertRaisesRegex(RuntimeError, "already-guessed"):
            self.adapter.submit("resource", 1)

    def test_rank_from_current_message_not_first_history_row(self):
        self.page.set_content(self.html(2), wait_until="domcontentloaded")
        self.set_response(3)
        # Snapshot 3's latest word is pollution (1754); first history row is environment (239).
        self.assertEqual(self.adapter.submit("pollution", 1), 1754)

    def test_loading_message_is_not_an_error(self):
        self.page.set_content(self.html(2), wait_until="domcontentloaded")
        self.page.evaluate("""html => {
            document.querySelector('form').addEventListener('submit', event => {
                event.preventDefault();
                document.querySelector('.message').innerHTML =
                    '<div class="message-text">Calculating...</div>';
                setTimeout(() => {
                    const saved = new DOMParser().parseFromString(html, 'text/html');
                    document.querySelector('#root').innerHTML = saved.querySelector('#root').innerHTML;
                }, 100);
            });
        }""", self.html(3))
        self.assertEqual(self.adapter.submit("pollution", 1), 1754)

    def test_stale_message_is_never_accepted(self):
        self.page.set_content(self.html(3), wait_until="domcontentloaded")
        self.page.evaluate("document.querySelector('form').addEventListener('submit', e => e.preventDefault())")
        self.adapter.timeout_ms = 100
        with self.assertRaises(Exception):
            self.adapter.submit("water", 1)

    def test_cookie_dialog_is_dismissed(self):
        self.page.set_content(self.html(3), wait_until="domcontentloaded")
        self.page.evaluate("""() => {
            const button = document.createElement('button');
            button.textContent = 'Do not consent';
            button.onclick = () => button.remove();
            document.body.appendChild(button);
        }""")
        self.page.locator('input[name="word"]').click()
        self.assertEqual(self.page.get_by_role('button', name='Do not consent', exact=True).count(), 0)
        self.assertIn('cookie_choice', self.log.path.read_text(encoding='utf-8'))


if __name__ == "__main__":
    unittest.main()
