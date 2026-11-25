#!/usr/bin/env python3
"""Record a plate-scope question, not a manufacturing verdict or permission.

The mere presence of the adjacent marker stops future work on this directory, even if
it is damaged or the G-code changes. No printer, provider, git, CAD, or YAML required.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

MARKER = 'scope-hold.json'


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1500 or not value.isprintable():
        raise ValueError(f'{name} must be one non-empty line (max 1500 characters)')
    return value.strip()


def read_hold(plate):
    """None only for absence. A broken link, wrong type or bad record is a stop."""
    path = plate / MARKER
    try:
        try:
            st = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_size > 16384:
            raise ValueError('expected a small regular file, not a link or directory')
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1):
            raise ValueError('expected scope record schema 1')
        return {k: text(data.get(k), k) for k in ('reason', 'question')}
    except (OSError, ValueError, RecursionError) as exc:
        return {'reason': 'The scope hold could not be read.', 'error': str(exc),
                'question': 'What is the intended plate and inventory? Reconcile the damaged hold before proceeding.'}


class ScopeHeld(ValueError):
    """An intent stop is not a failed manufacturing attempt."""


def require_open(plate):
    hold = read_hold(plate)
    if hold is not None:
        detail = ' (' + hold['error'] + ')' if 'error' in hold else ''
        raise ScopeHeld(f'{plate / MARKER}: {hold["reason"]}{detail}\nAsk: {hold["question"]}')


def place_hold(plate, reason, question):
    markers = ('preparation.json', 'handoff.txt', 'plate_1.gcode', 'sent.json')
    if not (any((plate/n).is_file() for n in markers) or any(f.is_file() for f in plate.glob('*.3mf'))):
        raise ValueError('identify an existing plate directory first; do not mark a project or guess a target')
    record = {'schema': 1, 'reason': text(reason, 'reason'), 'question': text(question, 'question')}
    # Exclusive creation. Even an interrupted write leaves a stop, not a false clearance.
    with (plate / MARKER).open('x', encoding='utf-8') as f:
        json.dump(record, f, indent=2, ensure_ascii=False); f.write('\n')
    print(f'Held {plate}. Ask: {record["question"]}')


def reopen(plate, answer):
    """For an operator selecting this SAME scope. Archive the old handoff before lifting its hold."""
    answer = text(answer, 'operator answer')
    if answer.casefold() in {'approved=1', 'confirmed=1'}:
        raise ValueError('an approval token is not an answer to a scope question')
    hold = read_hold(plate)
    if hold is None or 'error' in hold:
        raise ValueError('need a readable active hold; reconcile missing/damaged records with the operator')
    if os.path.lexists(plate/'sent.json'):
        raise ValueError('possible prior send; reconcile receipt, do not reopen or resend this packet')
    history = plate/'scope-history'
    history.mkdir(exist_ok=True)
    if history.is_symlink() or not history.is_dir():
        raise ValueError('scope-history must be a local directory')
    # Unique entry even across cycles. If interrupted before the final rename, the hold stays in force.
    archive = Path(tempfile.mkdtemp(prefix='decision-', dir=history))
    (archive/'answer.txt').write_text(answer + '\n', encoding='utf-8')
    if os.path.lexists(plate/'handoff.txt'):
        (plate/'handoff.txt').rename(archive/'handoff.txt')
    (plate/MARKER).rename(archive/MARKER)
    print(f'Answer and prior handoff archived in {archive}. Recheck the packet and present a fresh handoff. No approval or send.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_ in [('check','read-only; 0 = no marker, 18 = held (never permission)'),
                        ('hold','park an existing plate; record exactly one question'),
                        ('reopen-for-review','after an explicit same-scope answer only; invalidates the prior handoff')]:
        p = sub.add_parser(name, help=help_); p.add_argument('plate', type=Path)
        if name == 'hold':
            p.add_argument('--reason', required=True); p.add_argument('--question', required=True)
        if name == 'reopen-for-review':
            p.add_argument('--answer', required=True, help='the actual operator reply, not an agent guess or an upload token')
    args = parser.parse_args(argv)
    try:
        plate = args.plate.resolve(strict=True)
        if not plate.is_dir():
            raise ValueError('expected an exact plate directory')
        if args.command == 'check':
            require_open(plate)
            print('PLATE_SCOPE_RESULT: PASS')
        elif args.command == 'hold':
            place_hold(plate, args.reason, args.question)
        else:
            reopen(plate, args.answer)
    except ScopeHeld as exc:
        print('PLATE_SCOPE_RESULT: HOLD', file=sys.stderr); print(exc, file=sys.stderr)
        return 18
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'{parser.prog}: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
