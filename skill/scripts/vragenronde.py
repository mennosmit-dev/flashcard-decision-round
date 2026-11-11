#!/usr/bin/env python3
"""vragenronde: spawn a fast browser UI to batch-answer questions as flashcards.

Usage:
    vragenronde.py <questions.json> [--timeout SECONDS] [--no-browser]

Reads questions from <questions.json>, opens a browser UI where the user
answers via keyboard (1-9 choose, a=type free text, space=skip, left=back),
and writes the answers as a JSON object to stdout.

Input format — either a flat array of question objects:
    [
      {"id": "q1", "q": "Use TypeScript?"},
      {"id": "q2", "q": "DB?", "options": ["postgres", "sqlite"]}
    ]
or a wrapper object with a batch-level default option set applied to every
question (per-question "options" still overrides):
    {
      "options": ["op lijst", "niet", "twijfel"],
      "skip": "laat staan",
      "questions": [
        {"id": "melk", "q": "Melk op de lijst?"},
        {"id": "db", "q": "DB?", "options": ["postgres", "sqlite"]}
      ]
    }
- An option is a string, or {"value": "...", "label": "...", "hint": "..."}
  (label/hint are display only; the answer is the value).
- A question may carry "kop" (small line above, e.g. the project) and "meta"
  (list of strings or {"text": "...", "tone": "warn"|"muted"}) shown as labels.
- "options" defaults to ["ja", "nee"]. "skip" renames the skip button.
- Skip → answer is null. "anders" (a) → answer is the typed string.

Every answer is sent to the server as it is given, so a timeout returns the
answers so far instead of nothing.

Output (stdout): {"q1": "ja", "q2": "postgres"} or {"q1": null, ...}
Exit 0 = submitted (or timeout with partial answers). Exit 1 = cancelled
without any answer / error (message on stderr).
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>vragenronde</title>
<style>
/* Everforest (sainnhe, medium) — light default, dark via prefers-color-scheme */
:root{
  --bg0:#fdf6e3;--bg-dim:#f2efdf;--bg1:#f4f0d9;--bg2:#efebd4;--bg3:#e6e2cc;
  --fg:#5c6a72;--grey:#939f91;--green:#8da101;--red:#f85552;--orange:#f57d26;
  --card:#fffbef;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg0:#2d353b;--bg-dim:#232a2e;--bg1:#343f44;--bg2:#3d484d;--bg3:#475258;
    --fg:#d3c6aa;--grey:#859289;--green:#a7c080;--red:#e67e80;--orange:#e69875;
    --card:#343f44;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg0);color:var(--fg);font-family:-apple-system,"Segoe UI",system-ui,sans-serif}
body{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px 16px;overflow:hidden}
#progress{position:fixed;top:0;left:0;height:3px;width:100%;background:var(--bg-dim)}
#progress > span{display:block;height:100%;background:var(--green);width:0%;transition:width 120ms ease}
#counter{position:fixed;top:14px;left:0;right:0;text-align:center;font-size:12px;color:var(--grey);font-variant-numeric:tabular-nums;letter-spacing:.04em;pointer-events:none}
#last{position:fixed;bottom:16px;left:0;right:0;text-align:center;font-size:12px;color:var(--grey);pointer-events:none;min-height:1em}
#last b{color:var(--fg);font-weight:500}
#stage{width:min(640px,100%)}
.card{background:var(--card);border:1px solid var(--bg3);border-radius:12px;padding:28px 28px 24px;margin-bottom:20px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.kop{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--grey);margin-bottom:10px}
.q{font-size:clamp(19px,2.6vw,26px);line-height:1.35;font-weight:500;word-wrap:break-word}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:16px}
.tag{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--bg2);color:var(--fg)}
.tag.warn{background:transparent;border:1px solid var(--red);color:var(--red);font-weight:600}
.tag.muted{color:var(--grey)}
.opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-bottom:16px}
.opt{display:flex;align-items:flex-start;gap:10px;padding:10px 14px;border:1px solid var(--bg3);border-radius:8px;background:var(--bg1);color:var(--fg);font-size:15px;cursor:pointer;font-family:inherit;text-align:left}
.opt:hover,.opt.sel{background:var(--bg2);border-color:var(--green)}
.opt .k{flex:none;width:20px;height:20px;line-height:20px;text-align:center;border-radius:4px;background:var(--bg3);font-size:12px;font-variant-numeric:tabular-nums}
.opt .l{display:flex;flex-direction:column;gap:2px}
.opt .h{font-size:12px;color:var(--grey)}
.secondary{display:flex;gap:8px;justify-content:center;margin-bottom:14px}
.secondary .opt{font-size:13px;padding:6px 12px}
#textentry{display:flex;flex-direction:column;align-items:stretch;gap:10px;margin:0 auto 16px}
#textentry input{padding:12px 16px;border:1px solid var(--bg3);border-radius:8px;background:var(--bg1);color:var(--fg);font-size:17px;font-family:inherit;outline:none}
#textentry input:focus{border-color:var(--green)}
.hint{color:var(--grey);font-size:12px;letter-spacing:.02em;text-align:center}
.hint kbd{background:var(--bg2);padding:1px 6px;border-radius:3px;border:1px solid var(--bg3);font-family:inherit;font-size:11px;color:var(--fg)}
.summary h2{font-size:22px;font-weight:500;margin-bottom:16px}
.summary table{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:15px}
.summary td{padding:7px 0;border-bottom:1px solid var(--bg3)}
.summary td.n{text-align:right;font-variant-numeric:tabular-nums}
.btn{padding:10px 20px;border-radius:8px;border:1px solid var(--green);background:var(--green);color:var(--bg0);font-size:15px;cursor:pointer;font-family:inherit}
#done{display:none;font-size:18px;color:var(--grey)}
</style>
</head>
<body>
<div id="progress"><span></span></div>
<div id="counter"></div>
<div id="stage"></div>
<div id="last"></div>
<div id="done">Verstuurd. Terug naar Claude Code.</div>
<script>
const DATA = __QUESTIONS_JSON__;
const QUESTIONS = DATA.questions;
const SKIP = DATA.skip || 'overslaan';
const stage = document.getElementById('stage');
const counter = document.getElementById('counter');
const last = document.getElementById('last');
const progressBar = document.querySelector('#progress > span');
const done = document.getElementById('done');
const total = QUESTIONS.length;
let i = 0;
let mode = 'card';  // card | typing | summary | done
const answers = {};

const val = o => typeof o === 'string' ? o : o.value;
const lab = o => typeof o === 'string' ? o : (o.label || o.value);
const labelFor = (q, v) => {
  if (v === null || v === undefined) return SKIP;
  const o = q.options.find(o => val(o) === v);
  return o ? lab(o) : '"' + v + '"';
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function makeOpt(keyLabel, text, hint, onClick, selected) {
  const b = el('button', 'opt' + (selected ? ' sel' : ''));
  b.appendChild(el('span', 'k', keyLabel));
  const l = el('span', 'l');
  l.appendChild(el('span', '', text));
  if (hint) l.appendChild(el('span', 'h', hint));
  b.appendChild(l);
  b.onclick = onClick;
  return b;
}

function card(q) {
  const c = el('div', 'card');
  if (q.kop) c.appendChild(el('div', 'kop', q.kop));
  c.appendChild(el('div', 'q', q.q));
  if (q.meta && q.meta.length) {
    const m = el('div', 'meta');
    q.meta.forEach(t => {
      const text = typeof t === 'string' ? t : t.text;
      const tone = typeof t === 'string' ? '' : (t.tone || '');
      m.appendChild(el('span', 'tag ' + tone, text));
    });
    c.appendChild(m);
  }
  return c;
}

function sync() {
  fetch('/progress', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(answers), keepalive: true}).catch(() => {});
}

function render() {
  mode = 'card';
  if (i >= total) return summary();
  const q = QUESTIONS[i];
  counter.textContent = (i + 1) + ' / ' + total;
  progressBar.style.width = ((i / total) * 100) + '%';
  stage.innerHTML = '';
  stage.appendChild(card(q));
  const optsEl = el('div', 'opts');
  q.options.forEach((o, idx) => {
    optsEl.appendChild(makeOpt(String(idx + 1), lab(o), typeof o === 'string' ? '' : o.hint,
      () => answer(val(o)), q.id in answers && answers[q.id] === val(o)));
  });
  stage.appendChild(optsEl);
  const sec = el('div', 'secondary');
  sec.appendChild(makeOpt('␣', SKIP, '', () => answer(null)));
  sec.appendChild(makeOpt('a', 'anders, typ iets', '', () => textEntry()));
  stage.appendChild(sec);
  const hint = el('div', 'hint');
  hint.innerHTML = '<kbd>1</kbd>&ndash;<kbd>' + q.options.length + '</kbd> kies &middot; <kbd>spatie</kbd> ' + SKIP +
    ' &middot; <kbd>a</kbd> typ' + (i > 0 ? ' &middot; <kbd>&larr;</kbd> terug' : '');
  stage.appendChild(hint);
}

function textEntry() {
  mode = 'typing';
  const q = QUESTIONS[i];
  stage.innerHTML = '';
  stage.appendChild(card(q));
  const wrap = el('div');
  wrap.id = 'textentry';
  const input = el('input');
  input.type = 'text';
  input.placeholder = 'typ je antwoord…';
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = input.value.trim();
      if (v) answer(v);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      render();
    }
  });
  wrap.appendChild(input);
  stage.appendChild(wrap);
  const hint = el('div', 'hint');
  hint.innerHTML = '<kbd>Enter</kbd> opslaan &middot; <kbd>Esc</kbd> terug';
  stage.appendChild(hint);
  input.focus();
}

function answer(value) {
  const q = QUESTIONS[i];
  answers[q.id] = value;
  sync();
  last.innerHTML = '';
  last.appendChild(document.createTextNode('vorige: '));
  last.appendChild(el('b', '', labelFor(q, value)));
  i++;
  render();
}

function summary() {
  mode = 'summary';
  progressBar.style.width = '100%';
  counter.textContent = total + ' / ' + total;
  last.textContent = '';
  const counts = {};
  QUESTIONS.forEach(q => {
    const k = labelFor(q, answers[q.id]);
    counts[k] = (counts[k] || 0) + 1;
  });
  stage.innerHTML = '';
  const c = el('div', 'card summary');
  c.appendChild(el('h2', '', 'Klaar. Dit ga je versturen:'));
  const t = el('table');
  Object.entries(counts).sort((a, b) => b[1] - a[1]).forEach(([k, n]) => {
    const tr = el('tr');
    tr.appendChild(el('td', '', k));
    tr.appendChild(el('td', 'n', String(n)));
    t.appendChild(tr);
  });
  c.appendChild(t);
  const b = el('button', 'btn', 'Versturen');
  b.onclick = finish;
  c.appendChild(b);
  stage.appendChild(c);
  const hint = el('div', 'hint');
  hint.innerHTML = '<kbd>Enter</kbd> versturen &middot; <kbd>&larr;</kbd> terug';
  stage.appendChild(hint);
}

function finish() {
  mode = 'done';
  counter.style.display = 'none';
  stage.style.display = 'none';
  done.style.display = 'block';
  fetch('/submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(answers),
    keepalive: true,
  }).finally(() => {
    setTimeout(() => { try { window.close(); } catch (e) {} }, 200);
  });
}

function back() {
  if (i === 0) return;
  i--;
  last.textContent = '';
  render();
}

document.addEventListener('keydown', (e) => {
  if (mode === 'typing' || mode === 'done') return;
  if (e.key === 'ArrowLeft') { e.preventDefault(); return back(); }
  if (mode === 'summary') {
    if (e.key === 'Enter') { e.preventDefault(); finish(); }
    return;
  }
  const q = QUESTIONS[i];
  if (e.key === ' ' || e.code === 'Backquote') { e.preventDefault(); return answer(null); }
  if (e.key.toLowerCase() === 'a') { e.preventDefault(); return textEntry(); }
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= q.options.length) { e.preventDefault(); return answer(val(q.options[n - 1])); }
});

render();
</script>
</body>
</html>"""


def make_handler(questions_json: str, result_holder: dict, done_event: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                body = HTML_TEMPLATE.replace("__QUESTIONS_JSON__", questions_json).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path not in ("/submit", "/progress"):
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("expected JSON object")
            except (ValueError, json.JSONDecodeError) as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"bad json: {e}".encode("utf-8"))
                return
            result_holder["answers"] = data
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            if self.path == "/submit":
                done_event.set()

    return Handler


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _validate_options(opts, where: str) -> list:
    if not isinstance(opts, list) or len(opts) < 2:
        raise ValueError(f"{where}: 'options' must be array of >=2 options")
    for o in opts:
        ok = (isinstance(o, str) and o) or (isinstance(o, dict) and isinstance(o.get("value"), str) and o["value"])
        if not ok:
            raise ValueError(f"{where}: each option must be a non-empty string or {{'value': ...}}")
    if len(opts) > 9:
        raise ValueError(f"{where}: max 9 options")
    return opts


def validate_questions(raw) -> tuple[list, str | None]:
    """Accept either a flat list of questions, or a wrapper object
    {"options": [...batch default...], "skip": "...", "questions": [...]}.
    Returns (questions with effective options resolved, skip label)."""
    skip = None
    if isinstance(raw, dict):
        batch_opts = raw.get("options")
        if batch_opts is not None:
            batch_opts = _validate_options(batch_opts, "batch 'options'")
        skip = raw.get("skip") if isinstance(raw.get("skip"), str) else None
        items = raw.get("questions")
        if not isinstance(items, list) or not items:
            raise ValueError("wrapper object must have a non-empty 'questions' array")
    elif isinstance(raw, list):
        batch_opts = None
        items = raw
    else:
        raise ValueError("input must be a JSON array, or an object with 'questions'")
    if not items:
        raise ValueError("questions must be a non-empty JSON array")

    default_opts = batch_opts or ["ja", "nee"]
    seen_ids = set()
    out = []
    for idx, q in enumerate(items):
        if not isinstance(q, dict):
            raise ValueError(f"question #{idx}: must be an object")
        qid = q.get("id")
        text = q.get("q")
        if not isinstance(qid, str) or not qid:
            raise ValueError(f"question #{idx}: missing/empty 'id'")
        if not isinstance(text, str) or not text:
            raise ValueError(f"question #{idx} ({qid}): missing/empty 'q'")
        if qid in seen_ids:
            raise ValueError(f"duplicate id: {qid!r}")
        seen_ids.add(qid)
        opts = q.get("options")
        if opts is not None:
            opts = _validate_options(opts, f"question #{idx} ({qid})")
        item = {"id": qid, "q": text, "options": opts or default_opts}
        if isinstance(q.get("kop"), str):
            item["kop"] = q["kop"]
        if isinstance(q.get("meta"), list):
            item["meta"] = q["meta"]
        out.append(item)
    return out, skip


def main():
    parser = argparse.ArgumentParser(description="Fast batch question UI in browser.")
    parser.add_argument("questions_file", help="path to JSON with questions ('-' for stdin)")
    parser.add_argument("--timeout", type=int, default=3600, help="seconds to wait for submit (default 3600)")
    parser.add_argument("--no-browser", action="store_true", help="do not auto-open browser")
    args = parser.parse_args()

    try:
        if args.questions_file in ("-", "/dev/stdin"):  # Windows kent /dev/stdin niet
            sys.stdin.reconfigure(encoding="utf-8")
            raw = json.load(sys.stdin)
        else:
            with open(args.questions_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        questions, skip = validate_questions(raw)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"vragenronde: {e}", file=sys.stderr)
        sys.exit(1)

    questions_json = json.dumps({"questions": questions, "skip": skip}).replace("</", "<\\/")

    port = pick_port()
    result: dict = {}
    done = threading.Event()
    handler = make_handler(questions_json, result, done)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"vragenronde: serving {len(questions)} question(s) at {url}", file=sys.stderr)
    if not args.no_browser:
        webbrowser.open(url)

    try:
        ok = done.wait(timeout=args.timeout)
    except KeyboardInterrupt:
        ok = False
    server.shutdown()
    server.server_close()

    answers = result.get("answers", {})
    if not ok:
        if not answers:
            print("vragenronde: cancelled (timeout or interrupt)", file=sys.stderr)
            sys.exit(1)
        print(f"vragenronde: niet verstuurd, {len(answers)} antwoord(en) tot nu toe teruggegeven", file=sys.stderr)

    normalized = {q["id"]: answers.get(q["id"]) for q in questions}
    print(json.dumps(normalized, ensure_ascii=False))


if __name__ == "__main__":
    main()
