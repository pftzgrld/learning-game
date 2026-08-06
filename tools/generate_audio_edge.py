#!/usr/bin/env python3
"""Generate Learning Club's audio via edge-tts (same en-IE-EmilyNeural voice,
no API key). Reuses the phrase list from generate_audio.py; writes the same
audio/*.mp3 layout and manifest.json. Re-runs skip existing files.

Run with an interpreter that has edge-tts installed:
    python3 tools/generate_audio_edge.py
"""
import asyncio
import importlib.util
import json
import pathlib
import sys

import edge_tts

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIO = ROOT / "audio"
VOICE = "en-IE-EmilyNeural"

spec = importlib.util.spec_from_file_location("gen", HERE / "generate_audio.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


async def synth(text: str, path: pathlib.Path, slow: bool):
    kwargs = {"rate": "-25%"} if slow else {}
    comm = edge_tts.Communicate(text, VOICE, **kwargs)
    await comm.save(str(path))


async def main():
    todo = gen.phrases()
    manifest = {}
    made = skipped = failed = 0
    for text, rel, slow in todo:
        mkey = gen.norm(text) + ("##slow" if slow else "")
        if mkey in manifest:
            continue
        manifest[mkey] = rel
        out = AUDIO / rel
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            try:
                await synth(text, out, slow)
                break
            except Exception as e:
                if attempt == 3:
                    print(f"FAILED after retries: {text!r}: {e}")
                    failed += 1
                    del manifest[mkey]
                    if out.exists():
                        out.unlink()
                else:
                    await asyncio.sleep(3 * (attempt + 1))
        else:
            continue
        made += 1
        if made % 50 == 0:
            print(f"  {made} generated...")
        await asyncio.sleep(0.15)
    (AUDIO / "manifest.json").write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")
    total_mb = sum(f.stat().st_size for f in AUDIO.rglob("*.mp3")) / 1e6
    print(f"done: {made} new, {skipped} existed, {failed} failed, {len(manifest)} phrases, {total_mb:.1f} MB")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
