"""Play an English Contexto puzzle by date, with Gemini and Playwright."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from gemini_trial import DEFAULT_MODEL, MEMORY_MODES, GameLog, create_client, read_api_key, run_game

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".conda" / "browsers"))

# The last-message panel is distinct from the rank-sorted history. Require a
# changed panel, a numeric rank, and the cleared input before accepting a row.
READ_FEEDBACK = """({before}) => {
    const message = document.querySelector('main .message');
    if (!message || message.innerHTML === before) return false;
    const error = message.querySelector('.message-text');
    if (error) {
        const text = error.innerText.trim();
        if (/^calculating[.\\u2026]*$/i.test(text)) return false;
        return {kind: 'error', message: text};
    }
    const row = message.querySelector('.row');
    const input = document.querySelector('input[name="word"]');
    if (!row || !input || input.value.trim()) return false;
    const wordNode = row.querySelector('.row-word');
    const rankNode = row.querySelector(':scope > span:last-child');
    const rankText = rankNode?.textContent.trim();
    if (!wordNode || !/^\\d+$/.test(rankText || '') || Number(rankText) < 1) return false;
    const word = Array.from(wordNode.childNodes).filter(n => n.nodeType === 3)
        .map(n => n.textContent).join('').trim();
    return {kind: 'rank', word, rank: Number(rankText),
        repeated: !!row.querySelector('.row-note'), message: message.innerText.trim(),
        completion: document.querySelector('.end-msg')?.innerText.trim() || ''};
}"""


def parse_date(value):
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError("Use YYYY-MM-DD, DD/MM/YYYY, or DD.MM.YYYY for the puzzle date.")


def classify_feedback(result):
    if result["kind"] == "rank":
        if result["repeated"]:
            raise RuntimeError("Contexto returned an already-guessed word; stopping to avoid a loop.")
        return result["rank"]
    message = result["message"]
    # Unknown failures (including service/access failures) must not become OOV guesses.
    if re.search(r"word.{0,30}(not found|not recognized|not recognised)|"
                 r"(don't|do not) know (that|this|the) word|"
                 r"not (a |in the )?(valid word|dictionary|vocabulary)|unknown word",
                 message, re.IGNORECASE):
        return "invalid"
    raise RuntimeError(f"Contexto reported an error: {message}")


class ContextoBrowser:
    def __init__(self, page, log, timeout_ms=45000):
        self.page = page
        self.log = log
        self.timeout_ms = timeout_ms
        self.artifacts = log.path.parent / "browser"
        self.artifacts.mkdir()
        page.set_default_timeout(timeout_ms)
        # A delayed consent overlay can steal focus during keyboard submission.
        page.add_locator_handler(
            page.get_by_role("button", name="Do not consent", exact=True),
            lambda locator: self.dismiss_consent())

    def dismiss_consent(self):
        button = self.page.get_by_role("button", name="Do not consent", exact=True)
        if button.is_visible():
            button.click()
            button.wait_for(state="hidden")
            self.log.write("cookie_choice", choice="do_not_consent")

    def snapshot(self, name):
        try:
            (self.artifacts / f"{name}.html").write_text(self.page.content(), encoding="utf-8")
            self.page.screenshot(path=str(self.artifacts / f"{name}.png"))
        except Exception as error:
            self.log.write("artifact_error", message=str(error))

    def open_game(self, puzzle_date):
        url = f"https://contexto.me/en/previous/{puzzle_date.isoformat()}"
        self.log.write("browser_navigation", requested_date=puzzle_date.isoformat(), url=url)
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.locator('input[name="word"]').wait_for(state="visible")
        displayed = self.page.locator(".info-bar > span").first.inner_text().strip()
        try:
            actual = datetime.strptime(displayed, "%m/%d/%Y").date()
        except ValueError as error:
            raise RuntimeError(f"Cannot verify the website puzzle date: {displayed}") from error
        if actual != puzzle_date:
            raise RuntimeError(f"Requested {puzzle_date}, but the site opened {actual}.")
        if self.page.locator(".guess-history .row").count() or self.page.locator(".end-msg").count():
            raise RuntimeError("The page already has guesses or is completed; expected a fresh game.")
        self.log.write("browser_ready", requested_date=puzzle_date.isoformat(),
                       displayed_date=displayed, url=self.page.url, fresh_game=True)
        self.snapshot("initial")

    def submit(self, guess, turn):
        message = self.page.locator("main .message")
        before = message.inner_html() if message.count() else ""
        self.log.write("browser_submit", turn=turn, guess=guess)
        try:
            field = self.page.locator('input[name="word"]')
            # A real focus click triggers the overlay handler before keyboard input.
            field.click()
            field.fill(guess)
            field.press("Enter")
            result = self.page.wait_for_function(READ_FEEDBACK, arg={"before": before},
                                                 timeout=self.timeout_ms).json_value()
            self.log.write("browser_feedback", turn=turn, submitted_word=guess,
                           observed=result, url=self.page.url)
            self.snapshot(f"turn_{turn:02d}")
            return classify_feedback(result)
        except Exception:
            self.snapshot(f"error_turn_{turn:02d}")
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", nargs="?", help="Puzzle date (YYYY-MM-DD)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--memory", choices=MEMORY_MODES, default="explicit",
                        help="explicit: send all guesses/ranks; linked: use previous_interaction_id")
    parser.add_argument("--max-guesses", type=int, default=30)
    parser.add_argument("--show-browser", action="store_true", help="Watch the browser as it plays")
    parser.add_argument("--check-site", action="store_true",
                        help="Verify date navigation only, without Gemini calls or guesses")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs")
    args = parser.parse_args()
    try:
        puzzle_date = parse_date(args.date or input("Puzzle date (YYYY-MM-DD): "))
    except (ValueError, EOFError, KeyboardInterrupt) as error:
        parser.error(str(error) or "Date entry cancelled")
    if puzzle_date > date.today():
        parser.error("Future puzzles are not available")
    if args.max_guesses < 1:
        parser.error("--max-guesses must be positive")
    key = read_api_key()
    if not args.check_site and not key:
        parser.error("Set GEMINI_API_KEY in the .env next to this script first")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error("Install the Conda environment from environment.yml (see README.md)")
    directory = args.output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                   + "_auto_" + uuid4().hex[:8])
    log = GameLog(directory, key)
    log.write("automation_config", puzzle_date=puzzle_date.isoformat(),
              memory_mode=args.memory,
              headless=not args.show_browser, check_site=args.check_site)
    print(f"Opening Contexto for {puzzle_date}. Records: {directory}")
    client = None
    game_started = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.show_browser)
            context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
            page = context.new_page()
            adapter = ContextoBrowser(page, log)
            try:
                adapter.open_game(puzzle_date)
                if args.check_site:
                    log.write("termination", reason="site_check_passed", submitted_guesses=0)
                    log.export()
                    print("Date verified. Fresh game loaded. No model calls or guesses made.")
                    return 0
                client = create_client(key)
                game_started = True
                reason = run_game(client, log, args.model, puzzle_date.isoformat(),
                                  args.max_guesses, get_feedback=adapter.submit,
                                  memory_mode=args.memory)
                adapter.snapshot("final")
                return 0 if reason in {"success", "guess_limit"} else 1
            finally:
                if not game_started:
                    adapter.snapshot("navigation")
                context.close()
                browser.close()
    except (Exception, KeyboardInterrupt) as error:
        log.write("browser_error", error_type=type(error).__name__, message=str(error))
        if not game_started:
            log.write("termination", reason="browser_setup_error", submitted_guesses=0)
        log.export()
        print(f"Stopped: {error}\nRecords: {directory}", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
