# Flashcard decision round

A coding agent often reaches a point where it needs ten small decisions from a human: keep or drop this note, which of two options, merge these two files. Asking them one by one in the chat is slow. Letting the agent guess is worse.

This tool hands those decisions to the human as flashcards in a small browser window. You answer with the number keys, usually in a few seconds per card. When you press send, the agent gets all answers back as JSON and continues.

I built it as a Claude Code skill for my own knowledge system, where the monthly clean-up produces 10 to 30 keep/drop/merge decisions at once.

## How it works

```
agent ──questions JSON──> vragenronde.py ──> local HTTP server (127.0.0.1, random port)
                                │                     │
                                │                     └── serves one HTML page, opens browser
                                │                                  │
                                │        <── POST /progress (after every answer)
                                │        <── POST /submit   (on send)
                                └──answers JSON on stdout──> agent continues
```

- One Python file, standard library only. No dependencies, no build step.
- The page is a single inline HTML template; the questions are injected as JSON (with `</` escaped so a question text cannot close the script tag).
- Every answer is posted to the server as it is given. If you walk away and the timeout hits, the agent still gets the answers so far instead of nothing.
- The server only listens on `127.0.0.1`, on a free port picked by the OS.

## Keys

| Key | Action |
| --- | --- |
| `1` to `9` | pick an option |
| `a` | type a free answer (Enter saves, Esc goes back) |
| space or `` ` `` | skip, answer becomes `null` |
| left arrow | previous question |
| Enter on the summary | send |

## Design choices

- **One option set per batch.** When `1` means "keep" on every card, you stop reading the buttons after the third card. That is where the speed comes from. A question can still override the options.
- **Free text and skip are always there**, so the agent never has to add "other" or "skip" as options.
- **A summary before sending** shows how many of each answer you gave, which catches a run of accidental key presses.
- **Exit codes the agent can act on**: 0 means answers came back, 1 means cancelled with nothing answered. The skill tells the agent to fall back to asking in the chat on 1, not to retry.

## Usage

```bash
python skill/scripts/vragenronde.py examples/questions.json
# or from stdin, which is how the agent calls it:
python skill/scripts/vragenronde.py - < examples/questions.json
```

Output:

```json
{"n1": "keep", "n2": "drop", "n3": "merge", "db": "sqlite"}
```

Input format: a flat list of `{"id", "q", "options"?}` objects, or a wrapper `{"options", "skip", "questions"}` with a batch default. An option is a string or `{"value", "label", "hint"}`. Optional per question: `kop` (small heading) and `meta` (tags, `{"text", "tone": "warn"}` shows red). Max 9 options. See the docstring at the top of the script.

To use it as a Claude Code skill, copy `skill/` to `.claude/skills/vragenronde/`. The `SKILL.md` tells the agent when to use it (5 or more decisions at once) and how.

## Tests

```bash
pip install pytest
python -m pytest -q
```

14 tests: input validation (defaults, batch options, overrides, nine kinds of invalid input) and a round trip against the real HTTP server (page served, progress saved, submit ends the wait, bad JSON gets 400, unknown paths 404). Result on my machine: `14 passed`.

## Notes

- The UI text and `SKILL.md` are in Dutch, because I use it in Dutch. The code and this README are in English.
- Colour palette: Everforest by sainnhe, light and dark mode via `prefers-color-scheme`.

## License

MIT
