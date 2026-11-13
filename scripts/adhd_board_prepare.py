"""Combine independent-reference fixtures into synthesizable board-test ROMs."""
import argparse
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--classes', type=int, choices=[10,26], default=10)
    a = ap.parse_args()
    source = ROOT/'build'/f'adhd-sim-k{a.classes}-d8192'
    out = ROOT/'build'/f'adhd-board-k{a.classes}'
    out.mkdir(parents=True, exist_ok=True)
    for kind in ('model','features','query'):
        (out/f'board_{kind}.hex').write_text(''.join(
            (source/f'{kind}{i}.hex').read_text() for i in range(4)))
    expected = json.loads((source/'expected.json').read_text())
    (out/'board_expected.hex').write_text(''.join(
        f"{(e['winner']<<16)|e['scores'][e['winner']]:08x}\n" for e in expected))
    print(out)

if __name__ == '__main__': main()
