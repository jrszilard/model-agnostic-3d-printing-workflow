#!/usr/bin/env python3
"""generator_refs.py — catch a coupon that references a constant its parent no longer has.

WHY
Coupon generators import the production module and read its constants: `production.SLOT_DEPTH`,
`pcc2.UPRIGHT_BACK_W`. When the parent is refactored the coupon is not, and nothing notices --
`test.sh` never runs a generator, and the exports were already committed. rebuild-all.sh found 11
generators dead this way, several of them COUPON scripts: the articles that qualify a joint for
parts/_lib/joints.py. A registry sample whose coupon can no longer be built cannot be re-qualified
when the material, printer or orientation changes, which the registry says re-opens the gate.

This resolves attribute reads against sibling modules statically -- no CadQuery, no geometry, no
execution -- so it is fast enough to sit in test.sh and run before every commit.

Known-dangling entries live in platform/pipeline/verify/generator_refs.allow, one
"path:module.attr" per line. They are a RATCHET, not a pardon: anything already listed is reported
as debt and does not fail, anything new does. The current list is coupons for mechanisms that were
replaced (the sign's slots became TK page seats in aa06766, pcc2's tapered upright became uniform),
so they need retiring or porting -- a design call, not a rename.

Usage: generator_refs.py [root] [--allow <file>] [--update-allow]
       exit 0 = no NEW dangling references, 1 = new ones found
"""
import ast, os, sys

def module_symbols(path):
    """Module-level names a sibling could legitimately read."""
    try:
        with open(path, encoding='utf-8') as stream:
            tree = ast.parse(stream.read())
    except (SyntaxError, OSError):
        return None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    names.update(e.id for e in t.elts if isinstance(e, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split('.')[0])
        # A module that rebinds via globals()/setattr is beyond static reach; see the guard below.
    dynamic = any(isinstance(n, ast.Name) and n.id in ('globals', 'setattr', 'vars')
                  for n in ast.walk(tree))
    return None if dynamic else names

def _py_literals(node):
    """String literals anywhere in an expression — enough to find "<module>.py" inside an
    os.path.join(HERE, "x.py") or a variable that was assigned one."""
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]

def _aliases(tree, dirpath, path):
    """alias -> sibling module file.

    Two idioms. Plain `import x` / `import x as y`, and the one this repo actually uses for
    coupons: importlib.util.spec_from_file_location(name, os.path.join(HERE, "part.py")) followed
    by `alias = importlib.util.module_from_spec(spec)`. The dynamic form was invisible to a check
    that only looked at Import nodes, which is why the first version of this file reported a clean
    repo while three coupons were dead on a constant rename.
    """
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split('.')[0]
                sib = os.path.join(dirpath, base + '.py')
                if os.path.exists(sib) and os.path.abspath(sib) != os.path.abspath(path):
                    out[a.asname or base] = sib

    # variable -> the "<something>.py" string it was assigned, for PCC2_PATH = os.path.join(...)
    pathvars = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            lits = [l for l in _py_literals(node.value) if l.endswith('.py')]
            if lits:
                pathvars[node.targets[0].id] = lits[-1]

    def spec_target(call):
        """The .py file named by a spec_from_file_location(...) call, or None."""
        f = call.func
        if not (isinstance(f, ast.Attribute) and f.attr == 'spec_from_file_location'):
            return None
        for arg in call.args[1:]:
            lits = [l for l in _py_literals(arg) if l.endswith('.py')]
            if lits:
                return lits[-1]
            if isinstance(arg, ast.Name) and arg.id in pathvars:
                return pathvars[arg.id]
        return None

    # spec variable -> target file
    specs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            t = spec_target(node.value)
            if t and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                specs[node.targets[0].id] = t
    # alias = module_from_spec(spec)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == 'module_from_spec'
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            arg = node.value.args[0] if node.value.args else None
            fname = specs.get(arg.id) if isinstance(arg, ast.Name) else None
            if fname:
                sib = os.path.join(dirpath, fname)
                if os.path.exists(sib):
                    out[node.targets[0].id] = sib
    return out

def check(root):
    bad = []
    for dirpath, _, files in os.walk(root):
        if '/src' not in dirpath.replace(os.sep, '/'):
            continue
        pys = [f for f in files if f.endswith('.py')]
        for f in pys:
            path = os.path.join(dirpath, f)
            try:
                with open(path, encoding='utf-8') as stream:
                    tree = ast.parse(stream.read())
            except (SyntaxError, OSError):
                continue
            aliases = _aliases(tree, dirpath, path)
            if not aliases:
                continue
            cache = {}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id in aliases):
                    sib = aliases[node.value.id]
                    if sib not in cache:
                        cache[sib] = module_symbols(sib)
                    syms = cache[sib]
                    if syms is not None and node.attr not in syms:
                        bad.append((path, node.lineno, node.value.id, node.attr,
                                    os.path.basename(sib)))
    return bad

def key(entry):
    path, _line, mod, attr, _sib = entry
    return f'{path}:{mod}.{attr}'

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    root = args[0] if args else '.'
    allow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generator_refs.allow')
    if '--allow' in sys.argv:
        allow_path = sys.argv[sys.argv.index('--allow') + 1]

    bad = check(root)
    if '--update-allow' in sys.argv:
        with open(allow_path, 'w', encoding='utf-8') as f:
            f.write('# Known-dangling generator references — DEBT, not approval.\n'
                    '# Each is a coupon reading a constant its parent no longer defines, because the\n'
                    '# mechanism it tested was replaced. Retire the coupon or port it; then delete the\n'
                    '# line. Anything NOT listed here fails platform/pipeline/test.sh.\n')
            for e in sorted({key(e) for e in bad}):
                f.write(e + '\n')
        print(f'wrote {allow_path} with {len({key(e) for e in bad})} entries')
        sys.exit(0)

    allowed = set()
    if os.path.exists(allow_path):
        with open(allow_path, encoding='utf-8') as stream:
            allowed = {line.strip() for line in stream
                       if line.strip() and not line.startswith('#')}
    new = [e for e in bad if key(e) not in allowed]
    known = len({key(e) for e in bad}) - len({key(e) for e in new})

    if not new:
        print(f'generator references: no new dangling references'
              + (f' ({known} known, see generator_refs.allow)' if known else ''))
        sys.exit(0)
    print(f'generator references: {len(new)} NEW dangling reference(s)')
    for path, line, mod, attr, sib in sorted(new):
        print(f'  {path}:{line}: {mod}.{attr} — not defined in {sib}')
    sys.exit(1)
