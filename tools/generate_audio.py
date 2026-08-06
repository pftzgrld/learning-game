#!/usr/bin/env python3
"""Generate Learning Club's spoken audio with Azure neural TTS (en-IE-EmilyNeural).

The app's vocabulary is small and fixed (times tables, spelling words, prompts,
praise), so we synthesise every phrase ONCE into audio/*.mp3 plus a
manifest.json the app uses to look up a file by normalised text. Anything not
in the manifest falls back to the device voice at runtime.

Credentials are read from ~/.azure-speech.env (never from this repo):
    AZURE_SPEECH_KEY=...
    AZURE_SPEECH_REGION=northeurope

Run:  python3 tools/generate_audio.py
Re-runs skip files that already exist, so it's safe to run again after adding
phrases. Uses the REST endpoint — no SDK install needed.
"""
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIO = ROOT / "audio"
VOICE = "en-IE-EmilyNeural"
FORMAT = "audio-24khz-48kbitrate-mono-mp3"


def load_env():
    envp = pathlib.Path.home() / ".azure-speech.env"
    if envp.exists():
        for line in envp.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not key or not region or "paste" in key.lower():
        sys.exit("Missing credentials: put AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in ~/.azure-speech.env")
    return key, region


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", t.lower())).strip()


def slug(t: str) -> str:
    return norm(t).replace("'", "").replace(" ", "-")[:60]


def phrases():
    """Every (text, relpath, slow) the app can speak. Keep in sync with index.html."""
    P = []
    # Tables Sprint questions: "3 times 7" (both orders exist as separate texts)
    for a in range(2, 13):
        for b in range(2, 13):
            P.append((f"{a} times {b}", f"tables/{a}x{b}.mp3", False))
    # Sprint results: "12 correct! New record!" / "... Well done!"
    for n in range(0, 61):
        P.append((f"{n} correct! Well done!", f"score/{n}-well.mp3", False))
        P.append((f"{n} correct! New record!", f"score/{n}-record.mp3", False))
    # Teddy addition: "3 plus 4"
    for a in range(1, 6):
        for b in range(1, 6):
            P.append((f"{a} plus {b}", f"plus/{a}p{b}.mp3", False))
    # Spelling words, normal + slow (slow is used after a wrong answer)
    words = sorted(set(re.findall(r'{ word: "([^"]+)"', (ROOT / "index.html").read_text(encoding="utf-8"))))
    for w in words:
        P.append((w, f"words/{slug(w)}.mp3", False))
        P.append((w, f"words/{slug(w)}-slow.mp3", True))
    # Teddy prompts, phonics, praise, wrong-answer reveals
    misc = [
        "What colour is this?", "What shape is this?", "What number is this?",
        "How many blocks?", "Which group has more?",
        "Well done! Three times seven is twenty one. Brilliant!",  # voice-test phrase
    ]
    plurals = ["apples", "stars", "bears", "cherries", "strawberries",
               "clovers", "fish", "flowers", "butterflies"]
    misc += [f"How many {p}?" for p in plurals]
    phon = ["sss", "ah", "tuh", "ih", "puh", "nnn", "kuh", "eh", "huh", "rrr", "mmm", "duh"]
    misc += [f"Which letter makes the {s} sound?" for s in phon] + phon
    misc += ["Well done Teddy!", "Brilliant!", "You're a star!", "Amazing!", "Super!", "Yay!"]
    answers = ["Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Brown", "Black", "White",
               "Circle", "Square", "Triangle", "Rectangle", "Star", "Heart", "Diamond"]
    answers += [str(i) for i in range(1, 11)] + list("SATIPNCKEHRMD")
    misc += [f"Nearly! It's {x}" for x in answers]
    for t in misc:
        P.append((t, f"misc/{slug(t)}.mp3", False))
    return P


def synth(key: str, region: str, text: str, slow: bool) -> bytes:
    body = html.escape(text)
    if slow:
        body = f"<prosody rate='-25%'>{body}</prosody>"
    ssml = (f"<speak version='1.0' xml:lang='en-IE'>"
            f"<voice name='{VOICE}'>{body}</voice></speak>")
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": FORMAT,
            "User-Agent": "learning-club-audio",
        })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("gave up after repeated 429s")


def main():
    key, region = load_env()
    todo = phrases()
    manifest = {}
    made = skipped = 0
    for text, rel, slow in todo:
        mkey = norm(text) + ("##slow" if slow else "")
        if mkey in manifest:
            continue  # duplicate phrase, first file wins
        manifest[mkey] = rel
        out = AUDIO / rel
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(synth(key, region, text, slow))
        made += 1
        if made % 25 == 0:
            print(f"  {made} generated...")
        time.sleep(0.3)  # stay friendly to the free tier
    (AUDIO / "manifest.json").write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")
    total_mb = sum(f.stat().st_size for f in AUDIO.rglob("*.mp3")) / 1e6
    print(f"done: {made} new, {skipped} already existed, {len(manifest)} phrases, {total_mb:.1f} MB total")


if __name__ == "__main__":
    main()
