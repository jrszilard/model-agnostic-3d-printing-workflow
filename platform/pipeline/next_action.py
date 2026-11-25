#!/usr/bin/env python3
"""Read-only workflow routing for a part or plate directory. Never a gate or permission.

Schema 1 adds one stable `action` and a `stop` bit to the human-readable report. A
receipt is evidence of a historical send, not a live printer query. No CAD, printer,
credentials, chat history, provider SDK, or knowledge vault is needed to inspect a plate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from plate_scope import MARKER, read_hold
import plate_inventory

HERE = Path(__file__).resolve().parent
HEX = re.compile(r'[0-9a-f]{64}')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def mapping(path):
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise ValueError(f'{path.name}: expected a JSON object')
    return obj


def stamp(path):
    fields = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        k, sep, v = line.partition('=')
        if sep:
            fields.setdefault(k, []).append(v.strip())
    return fields


def check_handoff(p):
    """Check the presenter's local byte bindings, not CAD or physical qualification.

    Never follow paths from manifest contents; only read the expected adjacent files.
    The real handoff and sender remain the manufacturing authorities.
    """
    fields = stamp(p / 'handoff.txt')

    def require(k, value):
        if fields.get(k) != [value]:
            raise ValueError(f'handoff.txt: missing, ambiguous or stale {k}')

    require('outdir', str(p))
    require('verify_slice', 'PASS')
    if (p / 'verify_slice.txt').read_text().strip() != 'PASS':
        raise ValueError('verify_slice.txt: not PASS')
    gcode = p / 'plate_1.gcode'
    if not gcode.stat().st_size:
        raise ValueError('plate_1.gcode: empty')
    gsha = digest(gcode)
    require('gcode_sha', gsha)
    manifest = p / 'qualification_manifest.json'
    require('qualification_manifest', str(manifest))
    require('qualification_manifest_sha', digest(manifest))
    data = mapping(manifest)
    if data.get('schema') != 1 or data.get('human_evaluation') != 'not-evaluated':
        raise ValueError('qualification_manifest.json: not the expected machine-only record')
    for k, f, sha in [('gcode', gcode, gsha), ('project_3mf', p/'plate.3mf', None)]:
        if data['plate'][k]['sha256'] != (sha or digest(f)):
            raise ValueError(f'qualification_manifest.json: {f.name} differs from the reviewed bytes')
    plate_inventory.bound(p, fields)
    return [v.split()[0] for v in fields.get('brep_verdict', []) if v.split()]


def traces(p, r):
    for f in sorted(p.glob('gates.*.jsonl')):
        count = 0
        try:
            with f.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict) or type(row.get('blocking')) is not bool:
                            raise ValueError('not a gate result')
                    except ValueError as e:
                        # Some historical emitters did not escape quotes in enforced_as. Never
                        # guess that row's verdict; keep reading so a later refusal isn't lost.
                        r['unknown'].append(f'{f.name}: unreadable gate row ({e})')
                        continue
                    count += 1
                    if row['blocking']:
                        detail = f"{row.get('gate')} = {row.get('verdict')} (blocks with exit {row.get('exit_on_block')})"
                        if row.get('condition') not in (None, '-'):
                            detail += f"; requires {row['condition']}, kind={r.get('plate_kind')}"
                        r['blockers'].append(detail)
            if not count:
                raise ValueError('empty trace')
        except (ValueError, OSError) as e:
            r['unknown'].append(f'{f.name}: incomplete gate evidence ({e})')
        r['evidence'].append({'file': f.name, 'says': f'{count} gate(s) recorded'})


def inspect(target):
    p = Path(target).resolve()
    r = dict(schema=1, target=str(p), kind='unrecognised', state='UNKNOWN', action='identify_target',
             stop=True, evidence=[], review_paths=[], blockers=[], unknown=[], next=[])

    def cite(name, says):
        r['evidence'].append({'file': name, 'says': says})

    def choose(action, state, stop, *steps):
        r.update(action=action, state=state, stop=stop, next=list(steps))
        return r

    # Paperwork cannot lift an intent stop. An existing receipt still takes precedence as history.
    hold = read_hold(p) if p.is_dir() else None
    markers = ('preparation.json', 'sent.json', 'handoff.txt', 'plate_1.gcode', 'verify_slice.txt',
               'qualification_manifest.json', plate_inventory.REQUEST, plate_inventory.CATALOG)
    projects = sorted(f.name for f in p.glob('*.3mf') if f.is_file())
    if hold is None and not any((p/n).exists() or (p/n).is_symlink() for n in markers):
        if (p / 'spec.yaml').is_file():
            r['kind'] = 'part'; cite('spec.yaml', 'part contract')
            s = p / 'verify.stamp'
            state = 'NOT VERIFIED'
            if s.is_file():
                try:
                    verdict = stamp(s).get('verdict', ['?'])[0]
                    state = 'RECORDED VERIFY: ' + verdict
                    cite('verify.stamp', f'recorded {verdict}; not a fresh run')
                except (OSError, ValueError) as e:
                    r['unknown'].append(f'cannot read verify.stamp: {e}')
            recipe = p/'prepare.yaml'
            if recipe.is_file():
                cite('prepare.yaml', 'single-part preparation recipe')
                try:
                    root = subprocess.run(['git', '-C', str(p), 'rev-parse', '--show-toplevel'],
                                          capture_output=True, text=True, check=True, timeout=5).stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    r['unknown'].append('canonical owning checkout not established')
                else:
                    cmd = shlex.join([str(HERE/'prepare/prepare.sh'), '--root', root, str(recipe), '--preflight'])
                    return choose('preflight', state, False, cmd,
                                  'Preflight checks declared source, recipe and dependency scopes. Do not stage a whole part or change branches to tidy the tree.')
            return choose('locate_recipe', state, True,
                          'Identify the owning part or kit recipe before preparing. A verify stamp alone is not a plate. Do not stage unrelated edits.')
        if projects:
            r['kind'] = 'project'; r['review_paths'] = projects; cite(projects[0], '3MF present; no adjacent workflow record or plate_1.gcode')
            return choose('review_project', 'REVIEW PROJECT ONLY', True,
                          'Open the 3MF for review. Do not treat it as a verified job or overwrite it with a fit plate.')
        r['unknown'].append('no part spec, plate record, G-code or review project found at this directory')
        r['question'] = 'Which part or plate version do you mean, and what do you want to do with it?'
        r['next'] = ['Ask: ' + r['question']]; return r

    r['kind'] = 'plate'

    def inventory_inputs():
        try:
            wants = plate_inventory.counts(plate_inventory.load(p / plate_inventory.REQUEST))
        except (ValueError, OSError, TypeError) as exc:
            r['blockers'].append(str(exc))
            return choose('capture_inventory', 'REQUESTED PIECES UNRESOLVED', True,
                          'Use the selected brief/BOM, not the slice. If ambiguous, ask which IDs and quantities are wanted. Begin a fresh output for an already sliced legacy packet.')
        r['requested'] = wants; cite(plate_inventory.REQUEST, 'requested quantities from the brief: ' + str(wants))
        try:
            plate_inventory.inputs(p)
        except (ValueError, OSError, TypeError) as exc:
            r['blockers'].append(str(exc))
            return choose('register_inventory_models', 'SOURCE MODELS UNRESOLVED', True,
                          'Register the independently named single-piece print meshes. Do not use the finished plate as its own reference or ask again for known quantities.')
        cite(plate_inventory.CATALOG, 'reference meshes match catalog hashes; this is not a sliced count')
        return None

    r['review_paths'] = projects + [n for n in ('REVIEW.md', 'handoff.txt', 'plate_1.gcode', 'qualification_manifest.json',
        'verify_slice.txt', 'verify_report.txt', 'plate_geom.txt', 'slice_meta.json', 'plate-request.json', 'inventory-catalog.json', 'plate-inventory.json', 'supports.png', 'preview', 'sent.json') if (p/n).exists()]
    if hold is not None:
        cite(MARKER, hold['reason']); r['review_paths'].append(MARKER)
        r['blockers'].append(hold['reason']); r['question'] = hold['question']
        if 'error' in hold:
            r['unknown'].append(f"{MARKER}: {hold['error']}")
    rec = p/'sent.json'
    if rec.exists() or rec.is_symlink():  # Even an empty/malformed receipt is not absence of a send.
        try:
            sent = mapping(rec)
            if (type(sent.get('started')) is not bool or not isinstance(sent.get('gcode_sha256'), str)
                    or not HEX.fullmatch(sent['gcode_sha256']) or sent.get('gcode') != 'plate_1.gcode'
                    or not all(isinstance(sent.get(k), str) and sent[k].strip() for k in ('sent_at', 'host', 'storage'))):
                raise ValueError('missing or invalid receipt fields')
            if digest(p/'plate_1.gcode') != sent['gcode_sha256']:
                raise ValueError('local G-code has changed since that send')
        except (ValueError, OSError) as e:
            cite('sent.json', 'receipt exists; could not match it to this job'); r['blockers'].append(str(e))
            r['unknown'].append('this job may already be on the printer')
            return choose('inspect_receipt', 'SEND RECORD UNRESOLVED', True,
                          'Stop. Reconcile the receipt, filename and bytes with the operator; do not upload or start.')
        cite('sent.json', f"sent {sent['sent_at']} to {sent['host']}; started={sent['started']}")
        cite('plate_1.gcode', 'SHA-256 matches send receipt: ' + sent['gcode_sha256'])
        if sent['started']:
            return choose('await_observation', 'START RECORDED — live state unknown', True,
                          'Do NOT re-send or start again. Ask the operator for the actual outcome; the receipt is not a fit or print verdict.')
        return choose('do_not_resend', 'STAGED AT PRINTER — uploaded, not started', True,
                      'Do NOT re-send: this plate was already uploaded without a start request. Live printer state and physical outcome are unknown.')

    if hold is not None:
        return choose('clarify_scope', 'ON HOLD — scope unresolved', True,
                      'Ask: ' + hold['question'], 'Do not prepare, present for approval, upload or start this plate.')

    prep = {}; prep_invalid = False; prep_path = p/'preparation.json'
    if prep_path.exists():
        try:
            prep = mapping(prep_path)
            if prep.get('status') not in ('READY', 'PREPARING', 'BLOCKED'):
                raise ValueError('unknown preparation status')
            cite(prep_path.name, f"status={prep['status']} kind={prep.get('kind')}")
        except (OSError, ValueError) as e:
            prep_invalid = True
            r['unknown'].append(f'preparation.json could not be parsed as a preparation state: {e}')
    r['plate_kind'] = prep.get('kind'); status = prep.get('status')
    if prep.get('part'):
        r['part'] = prep['part']
    traces(p, r)
    if status == 'BLOCKED' or r['blockers']:
        if isinstance(prep.get('problems'), list):
            r['blockers'].extend(str(v) for v in prep['problems'] if v)
        attempts = prep.get('failed_attempts', 0)
        if (type(attempts) is int and attempts >= 2) or prep.get('repair_attempt'):
            return choose('escalate', 'BLOCKED — repair spent', True,
                          'Present the blocker, changed inputs and evidence to the owner. Do not repeat the run.')
        repair = ('Use the multi-input recipe; do not substitute single-primary prepare.sh.' if prep.get('models') else
                  'One changed-input repair with --repair-reason, not an automatic retry.')
        return choose('inspect_blocker', 'BLOCKED', True, 'Read the named stage log and the gate exit first. ' + repair)
    # Diagnostic JSONL is not the production verdict. A complete independently bound handoff
    # can be presented despite an unknown trace row; no actual blocking row is ignored above.
    if prep_invalid or (r['unknown'] and not (p/'handoff.txt').is_file()):
        return choose('inspect_preparation', 'UNKNOWN', True, 'Resolve incomplete records before advancing; do not upload or start.')
    if status == 'PREPARING':
        return choose('inspect_preparation', 'PREPARING OR INTERRUPTED', True,
                      'Check the owner and active preparation/log before taking over. Do not launch another pass.')
    if (p/'handoff.txt').exists():
        try:
            verdicts = check_handoff(p)
        except (ValueError, OSError, KeyError, TypeError) as e:
            r['blockers'].append(str(e)); cite('handoff.txt', 'could not bind current plate artifacts')
            return choose('rebuild_handoff', 'HANDOFF INCOMPLETE OR STALE', True,
                          'Check the named artifact, verify the intended slice and rerun the real handoff. Prior approval does not transfer.')
        cite('handoff.txt', 'local bindings checked; B-rep verdicts: ' + (', '.join(verdicts) or 'not recorded'))
        cite('qualification_manifest.json', 'machine identity only; matches adjacent G-code and project')
        cite('plate-inventory.json', 'requested IDs and quantities match identified 3MF bodies with model extrusion; current input/report hashes match the handoff')
        notes = ['Present the exact review artifacts and stop. Approval is theirs; never infer APPROVED=1 from this report.']
        if 'DEBT' in verdicts:
            notes.insert(0, 'Disclose the declared measurement debt; a digital check is not a physical result.')
        return choose('review_handoff', 'AWAITING HUMAN APPROVAL', True, *notes)
    if status == 'READY':
        essentials = ('plate.3mf', 'plate_1.gcode', 'verify_slice.txt')
        absent = [n for n in essentials if not (p/n).is_file() or not (p/n).stat().st_size]
        try:
            vs_pass = not absent and (p/'verify_slice.txt').read_text().strip() == 'PASS'
        except (ValueError, OSError):
            vs_pass = False
        if not vs_pass:
            r['blockers'].append('missing ' + ', '.join(absent) if absent else 'verify_slice.txt is not a readable PASS')
            return choose('inspect_preparation', 'READY RECORD WITHOUT VERIFIED SLICE', True,
                          'Reconcile the incomplete prepared plate before running a handoff.')
        problem = inventory_inputs()
        if problem is not None:
            return problem
        return choose('prepare_handoff', 'READY (handoff not present)', False,
                      'Run the actual handoff.sh on the intended plate; READY alone is not authority to send.')
    if not prep_path.exists() and (p/plate_inventory.REQUEST).exists() and not (p/'plate_1.gcode').exists():
        problem = inventory_inputs()
        if problem is not None:
            return problem
        return choose('locate_recipe', 'REQUEST AND CATALOG PRESENT — NOT SLICED', True,
                      'Use the owning preparation recipe for this requested scope. No verified plate exists.')
    return choose('inspect_preparation', 'NO COMPLETED HANDOFF', True,
                  'Find the owning recipe and review the preparation evidence. A slice by itself is not a handoff.')


def inspect_targets(targets):
    """Explicit alternatives only. Never resolve an ambiguous nickname by recency or readiness."""
    paths = list(dict.fromkeys(Path(t).resolve() for t in targets)) or [Path.cwd()]
    if len(paths) == 1:
        return inspect(paths[0])
    rows = [inspect(path) for path in paths]
    question = 'Which of these versions do you mean, and which part IDs or quantities should change or stay?'
    return dict(schema=1, kind='candidates', target='explicit alternatives (none selected)',
                action='clarify_target', stop=True, state='TARGET NOT SELECTED', question=question,
                candidates=[{k: row[k] for k in ('target', 'action', 'state', 'evidence', 'question') if k in row} for row in rows],
                evidence=[], blockers=[], unknown=['operator selection is not recorded by these paths'], review_paths=[],
                next=['Name the actual alternatives and ask: ' + question, 'Do not act on any candidate until the intended scope is clear.'])


def render(report):
    lines = [f"{report['kind'].upper()}: {report['target']}", 'STATE: ' + report['state'],
             f"ACTION: {report['action']}   STOP: {str(report['stop']).lower()}"]
    if report.get('part'):
        lines.append('PART:  ' + str(report['part']))
    lines += ['', 'Read from (nothing below is inferred):']
    lines.extend(f"  {row['file']}: {row['says']}" for row in report['evidence'])
    for row in report.get('candidates', []):
        lines.append(f"  {row['target']}: {row['action']} — {row['state']}")
        lines.extend(f"    {ev['file']}: {ev['says']}" for ev in row['evidence'])
    for key in ('unknown', 'blockers', 'next', 'review_paths'):
        if report[key]:
            lines += ['', key.upper() + ':', *('  - ' + s for s in report[key])]
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='*', help='exact part/plate directory; multiple distinct candidates require a choice')
    parser.add_argument('--json', action='store_true', help='schema 1; exit 0 means inspected, not approved')
    args = parser.parse_args(argv)
    report = inspect_targets(args.target)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
