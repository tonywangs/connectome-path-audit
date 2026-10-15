#!/usr/bin/env python3
"""Check the publishable working tree and recorded verification fingerprints."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    raw = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    names = sorted(set(n.decode() for n in raw.split(b'\0') if n))
    names = [n for n in names if (ROOT / n).exists()]
    assert len(names) <= 1000, 'file count exceeds 1000'
    total = 0
    for name in names:
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), f'not a regular file: {name}'
        size = path.stat().st_size
        assert size <= 10 * 1024 * 1024, f'file too large: {name}'
        assert not name.endswith('.log') or name == 'results/tests.log', f'non-test log: {name}'
        total += size
    assert total <= 32 * 1024 * 1024, 'tree exceeds 32 MiB'
    evidence = json.loads((ROOT / 'results/verification.json').read_text())
    for name, expected in evidence['verified_files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, f'verification stale: {name}'
    example = ROOT / 'results/example'
    marker = json.loads((example / 'COMPLETE.json').read_text())
    for name, info in marker['artifacts'].items():
        raw = (example / name).read_bytes()
        assert len(raw) == info['bytes']
        assert hashlib.sha256(raw).hexdigest() == info['sha256']
    print(json.dumps({'publishable_files': len(names), 'total_bytes': total,
                      'largest_file_bytes': max((ROOT / n).stat().st_size for n in names),
                      'recorded_source_hashes_match': True, 'example_bundle_hashes_match': True}, sort_keys=True))


if __name__ == '__main__': main()
