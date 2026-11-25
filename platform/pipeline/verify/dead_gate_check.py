#!/usr/bin/env python3
"""dead_gate_check.py — refuse an assertion that cannot fail.

WHY THIS EXISTS
A gate that cannot fire is worse than no gate. No gate prompts caution; a dead one produces
confidence, and someone reads "smoke check passed" and ships. This repo has the receipts:
`docs/remediation-plan.md` opens on a provenance gate at 0/16 specs and a boundary validator
nothing ran, and `_smoke_check` in bottle-lamp-carrier says in its own docstring that "every rule
here was violated silently at least once during rev 4".

On 2026-09-04 a review found three assertions in `parts/**/src` that can never fail. All three were
confirmed by reading the definitions, and all three sit on geometry that has been printed:

  1. bottle-lamp-carrier.py:794 — the gate keeping the anchor OUT of the protected nOOd channel,
     which is BL1's recorded scar.
         reach     = _ANCHOR_REACH(...) + _channel_inner_edge(...) - ANCHOR_BOND
         protected = r_at + inner + ANCHOR_CHANNEL_CLEAR      # r_at, inner: the same two calls
         if reach > protected:            # difference is -(0.60 + 0.15), a compile-time constant
  2. bottle-lamp-carrier.py:811 — the BL1 "rungs must reach the ribbon" regression check.
         r_at  = r0 + (r1 - r0) * frac
         reach = _ANCHOR_REACH(r0, r1, frac)   # whose whole body is `return r0 + (r1-r0)*frac`
         if reach < r_at - rt / 2.0 - 0.01:    # comparing a value with itself
  3. balloon-lamp-sprung.py:247 — the hoop-fold exemption.
         exempt = [i for i in range(len(RING_F)) if not folds(i)]
         for i in exempt:
             if RING_R[i] > rf * FOLD_MARGIN:  # which is exactly what folds(i) returns
                 raise AssertionError(...)

Nobody was careless. In each case the two operands are several lines apart, wear different names,
and read as arithmetic over real values. That is precisely the shape a machine is good at and a
reader is not.

WHAT IT CATCHES, AND WHAT IT DOES NOT
Three syntactic rules, one per defect above (R1/R2/R3 in the code). It is a FLOOR, not a ceiling:
it finds assertions that are dead *structurally*. It cannot find one that is merely too loose —
`assert_snap_geometry` in balloon-lamp-clip-mock.py fires, but with 1.425 mm of slack it would keep
passing after the retaining head had been buried. Nothing here replaces constructing the failure
and watching the gate refuse.

Deliberately conservative: it reports only when the reduction is certain, because a check with
false positives gets an allow-list bolted on and then gets ignored, which is the disease again.

Usage:  python3 platform/pipeline/verify/dead_gate_check.py [root]     exit 0 = no dead gates
"""
import ast
import os
import sys

MAX_INLINE_DEPTH = 6
# A comparison whose operands expand into a tree too deep to walk is left unjudged and counted here.
# Substituting a long fluent chain (`s.fuse(a).fuse(b)...`) six levels down overflowed the interpreter's
# recursion limit in lighthouse-cap.py, and from 2026-11-06 to 2026-11-11 that one file crashed the
# whole check: no generator was being checked for dead gates at all.
TOO_DEEP = []
_PRUNE = {".git", "__pycache__", "build", ".venv", ".venv-ai", "node_modules", "releases", "vendor"}


# ─── expansion: substitute what is knowable, leave the rest opaque ────────────────────────────────

def _single_return_funcs(tree):
    """Module-level `def f(...): return <expr>` — the only functions safe to inline.

    A body with branches, loops or several returns has no single expression to substitute, and
    guessing one is how a checker starts inventing findings.
    """
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body = [n for n in node.body if not (isinstance(n, ast.Expr)
                                                 and isinstance(n.value, ast.Constant)
                                                 and isinstance(n.value.value, str))]
            if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
                args = node.args
                if not (args.vararg or args.kwarg or args.posonlyargs or args.kwonlyargs):
                    out[node.name] = ([a.arg for a in args.args], body[0].value)
    return out


def _module_constants(tree):
    """Module-level `NAME = <numeric expr>`, bound once.

    Without these, `reach - protected` in bottle-lamp-carrier reduces to
    `-ANCHOR_BOND - ANCHOR_CHANNEL_CLEAR` — two opaque atoms rather than the constant -0.75 it
    really is, and the rule that should catch it sees a data-dependent difference.
    """
    counts, values = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            counts[name] = counts.get(name, 0) + 1
            values[name] = node.value
    out = {}
    for name, value in values.items():
        if counts[name] != 1:
            continue
        if _reduce(value).is_constant:
            out[name] = value
    return out


def _single_assignment_locals(fn):
    """Locals bound exactly once in this function, by a plain `name = expr`.

    Once only: a name that is reassigned has no single value, and substituting the first one would
    be a lie. Loop variables, `for` targets, augmented assignment and tuple unpacking are all
    excluded for the same reason.
    """
    counts, values = {}, {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    counts[tgt.id] = counts.get(tgt.id, 0) + 1
                    values[tgt.id] = node.value
                else:
                    for sub in ast.walk(tgt):
                        if isinstance(sub, ast.Name):
                            counts[sub.id] = counts.get(sub.id, 0) + 2   # never substitutable
        elif isinstance(node, (ast.AugAssign, ast.NamedExpr)):
            tgt = node.target
            if isinstance(tgt, ast.Name):
                counts[tgt.id] = counts.get(tgt.id, 0) + 2
        elif isinstance(node, ast.For):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    counts[sub.id] = counts.get(sub.id, 0) + 2
        elif isinstance(node, (ast.comprehension,)):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    counts[sub.id] = counts.get(sub.id, 0) + 2
    return {k: v for k, v in values.items() if counts.get(k) == 1}


class _Expander(ast.NodeTransformer):
    def __init__(self, env, funcs, depth, consts):
        self.env, self.funcs, self.depth, self.consts = env, funcs, depth, consts

    def visit_Name(self, node):
        if self.depth < MAX_INLINE_DEPTH and node.id in self.env:
            return _expand(self.env[node.id], self.env, self.funcs, self.depth + 1, self.consts)
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if self.depth >= MAX_INLINE_DEPTH:
            return node
        if isinstance(node.func, ast.Name) and node.func.id in self.funcs and not node.keywords:
            params, body = self.funcs[node.func.id]
            if len(params) == len(node.args):
                # The callee's scope is its parameters PLUS the module constants -- not the caller's
                # locals, which it cannot see. Dropping the constants here is what left
                # `- ANCHOR_BOND` as an opaque atom and hid the very finding this rule is for.
                bound = dict(self.consts)
                bound.update(zip(params, node.args))
                return _expand(body, bound, self.funcs, self.depth + 1, self.consts)
        return node


def _expand(node, env, funcs, depth=0, consts=None):
    """Rewrite `node` with single-assignment locals and single-return calls substituted in."""
    if depth >= MAX_INLINE_DEPTH:
        return node
    expander = _Expander(env, funcs, depth, consts if consts is not None else {})
    return expander.visit(ast.fix_missing_locations(_copy(node)))


def _copy(node):
    return ast.parse(ast.unparse(node), mode="eval").body if not isinstance(node, ast.Module) else node


def _canon(node):
    """A comparable string for an expanded expression."""
    try:
        return ast.unparse(node)
    except Exception:
        return None


# ─── linear reduction: atoms + a constant ─────────────────────────────────────────────────────────

class Lin:
    """A linear combination of opaque atoms plus a numeric constant.

    Anything not additively decomposable — a product of two variables, a subscript, an unresolved
    call — becomes one ATOM keyed by its source text. Two atoms are equal when their text is equal,
    which is what lets `_ANCHOR_REACH(r0, r1, frac)` on one side of a comparison cancel against the
    same call on the other. That assumes such a call is pure; every one of these is a geometry
    helper over its arguments, and impurity would only cost a missed finding, never a false one.
    """

    def __init__(self, atoms=None, const=0.0):
        self.atoms = dict(atoms or {})
        self.const = const

    def __add__(self, other):
        out = Lin(self.atoms, self.const + other.const)
        for k, v in other.atoms.items():
            out.atoms[k] = out.atoms.get(k, 0.0) + v
        return out.trim()

    def __neg__(self):
        return Lin({k: -v for k, v in self.atoms.items()}, -self.const)

    def __sub__(self, other):
        return self + (-other)

    def scale(self, factor):
        return Lin({k: v * factor for k, v in self.atoms.items()}, self.const * factor).trim()

    def trim(self):
        self.atoms = {k: v for k, v in self.atoms.items() if abs(v) > 1e-12}
        return self

    @property
    def is_constant(self):
        return not self.atoms

    @property
    def is_data_dependent(self):
        return bool(self.atoms)


def _reduce(node):
    """Expression -> Lin. Never fails; anything opaque becomes an atom."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return Lin({}, float(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_reduce(node.operand)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _reduce(node.operand)
    if isinstance(node, ast.BinOp):
        left, right = _reduce(node.left), _reduce(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            if left.is_constant:
                return right.scale(left.const)
            if right.is_constant:
                return left.scale(right.const)
        if isinstance(node.op, ast.Div) and right.is_constant and right.const != 0:
            return left.scale(1.0 / right.const)
    key = _canon(node)
    return Lin({key: 1.0} if key is not None else {"<unparseable>": 1.0}, 0.0)


# ─── the three rules ──────────────────────────────────────────────────────────────────────────────

_ALWAYS = {ast.Lt: lambda d: d < 0, ast.LtE: lambda d: d <= 0, ast.Gt: lambda d: d > 0,
           ast.GtE: lambda d: d >= 0, ast.Eq: lambda d: d == 0, ast.NotEq: lambda d: d != 0}


def _varies_at_runtime(node, params):
    """Does this expanded expression depend on anything that is not fixed at import time?

    The discriminator that keeps CONSTANT-DRIFT TRIPWIRES out of the report. A guard like

        if (TOOTH_PITCH, GROOVE_WIDTH, TOOTH_DEPTH) != (2.4, 1.8, 0.2): raise

    reduces to a constant by construction and is always False today -- and that is the entire
    point of it. It is not a dead gate; it is a gate whose job is to stay quiet until somebody
    edits a qualified constant, and reporting it would train people to ignore this check. So a
    comparison is only interesting when at least one side reaches something that actually varies:
    a parameter of the enclosing function, or a call that could not be inlined.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in params:
            return True
        if isinstance(sub, (ast.Call, ast.Subscript, ast.Attribute)):
            return True
    return False


def _param_names(fn):
    args = fn.args
    names = {a.arg for a in list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _check_comparison(cmp_node, env, funcs, consts, params, path, findings):
    """Judge one comparison; one that cannot be expanded is recorded in TOO_DEEP, never a crash and
    never a finding (this check reports only what is certain)."""
    try:
        _judge_comparison(cmp_node, env, funcs, consts, params, path, findings)
    except RecursionError:
        TOO_DEEP.append((path, getattr(cmp_node, "lineno", 0)))


def _judge_comparison(cmp_node, env, funcs, consts, params, path, findings):
    if len(cmp_node.ops) != 1 or len(cmp_node.comparators) != 1:
        return
    op = type(cmp_node.ops[0])
    if op not in _ALWAYS:
        return
    left = _expand(cmp_node.left, env, funcs, 0, consts)
    right = _expand(cmp_node.comparators[0], env, funcs, 0, consts)
    lin_l, lin_r = _reduce(left), _reduce(right)

    # R1 — the two sides differ by a compile-time constant, while at least one side LOOKS
    # data-dependent. A comparison between two literals is a deliberate switch and is left alone.
    # R2 runs FIRST and is not subject to the runtime filter below. Two names bound to the same
    # expression and then compared is a defect whatever the expression is made of --
    # photo-calibration-corner.py:199 assigns `screw_axis` and `upright_axis` the identical tuple
    # and then raises on "PCCZ/PCCH M3 bore misalignment" if they differ, which they cannot.
    for lname, rname in _aliased_across(cmp_node, env, funcs, consts):
        findings.append((path, cmp_node.lineno, "R2",
                         "`%s` and `%s` are the same expression (`%s`), so this compares a value "
                         "with itself and only the literal offsets decide it"
                         % (lname, rname, _alias_text(lname, env, funcs, consts))))
        return

    if not (_varies_at_runtime(left, params) or _varies_at_runtime(right, params)):
        return

    diff = lin_l - lin_r
    if diff.is_constant and (lin_l.is_data_dependent or lin_r.is_data_dependent):
        verdict = _ALWAYS[op](diff.const)
        findings.append((path, cmp_node.lineno, "R1",
                         "every term cancels: `%s` reduces to the constant %.6g, so this is always %s"
                         % (_canon(cmp_node) or "<expr>", diff.const, verdict)))
        return




def _local_names(node, env):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in env}


def _alias_text(name, env, funcs, consts):
    text = _canon(_expand(env[name], env, funcs, 0, consts))
    return (text[:60] + "…") if text and len(text) > 60 else (text or "<expr>")


def _aliased_across(cmp_node, env, funcs, consts):
    """Pairs (left_name, right_name) bound to canonically identical expressions."""
    left_names = _local_names(cmp_node.left, env)
    right_names = _local_names(cmp_node.comparators[0], env)
    pairs = []
    for lname in sorted(left_names):
        ltext = _canon(_expand(env[lname], env, funcs, 0, consts))
        if ltext is None:
            continue
        for rname in sorted(right_names):
            if rname == lname:
                continue
            if _canon(_expand(env[rname], env, funcs, 0, consts)) == ltext:
                pairs.append((lname, rname))
    return pairs


def _check_selector_negation(fn, env, funcs, consts, path, findings):
    """R3 — a loop over `[x for x in ... if not P(x)]` whose body then tests P(x)."""
    filtered = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            comp = node.value
            if len(comp.generators) == 1 and len(comp.generators[0].ifs) == 1:
                test = comp.generators[0].ifs[0]
                if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) \
                        and isinstance(comp.generators[0].target, ast.Name) \
                        and isinstance(comp.elt, ast.Name) \
                        and comp.elt.id == comp.generators[0].target.id:
                    filtered[node.targets[0].id] = (comp.generators[0].target.id, test.operand)

    for node in ast.walk(fn):
        if not isinstance(node, ast.For) or not isinstance(node.iter, ast.Name):
            continue
        if node.iter.id not in filtered or not isinstance(node.target, ast.Name):
            continue
        comp_var, negand = filtered[node.iter.id]
        rebound = _expand(negand, {comp_var: node.target}, funcs, 0, consts)
        want = _canon(_expand(rebound, env, funcs, 0, consts))
        for inner in ast.walk(node):
            if isinstance(inner, ast.If):
                got = _canon(_expand(inner.test, env, funcs, 0, consts))
                if want is not None and got == want:
                    findings.append((path, inner.lineno, "R3",
                                     "the loop iterates items selected by `not (%s)` and then tests "
                                     "that same condition, so this branch is unreachable"
                                     % (_canon(negand) or "<expr>")))


# ─── driver ───────────────────────────────────────────────────────────────────────────────────────

def check_source(source, path="<source>"):
    findings = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(path, getattr(exc, "lineno", 0), "PARSE", "could not parse: %s" % exc)]
    funcs = _single_return_funcs(tree)
    consts = _module_constants(tree)
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        params = _param_names(fn)
        _walk_block(fn.body, dict(consts), funcs, consts, params, path, findings,
                    _rebound_in(fn))
        _check_selector_negation(fn, _block_env_snapshot(fn, consts), funcs, consts, path, findings)
    return findings


def _rebound_in(fn):
    """Names this function binds by any means OTHER than a plain `name = expr`.

    A `for` target, an augmented assignment, a walrus or a tuple unpack has no single expression
    to stand in for it, so those names stay opaque wherever they appear.
    """
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.AugAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    out.add(sub.id)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name):
                    for sub in ast.walk(tgt):
                        if isinstance(sub, ast.Name):
                            out.add(sub.id)
    return out


def _block_env_snapshot(fn, consts):
    env = dict(consts)
    opaque = _rebound_in(fn)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id not in opaque:
            env[node.targets[0].id] = node.value
    return env


def _walk_block(body, env, funcs, consts, params, path, findings, opaque):
    """Statements in order, so a name resolves to its NEAREST PRECEDING assignment.

    Function-scope single-assignment was too blunt to see the two findings this file was written
    for: `_smoke_check` in bottle-lamp-carrier assigns `r_at` and `reach` once in each of two
    branches, inside a loop, so a whole-function rule refuses to substitute either and both dead
    gates stay invisible. Ordered, block-scoped resolution is what straight-line code actually
    means, and each nested block gets its own copy so one arm cannot leak into another.
    """
    for stmt in body:
        # Test expressions first, against the environment as it stands BEFORE this statement.
        for test in _tests_of(stmt):
            for cmp_node in _comparisons_in(test):
                _check_comparison(cmp_node, env, funcs, consts, params, path, findings)

        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            for cmp_node in _comparisons_in(stmt.value):
                _check_comparison(cmp_node, env, funcs, consts, params, path, findings)
            name = stmt.targets[0].id
            if name in opaque:
                env.pop(name, None)
            else:
                env[name] = stmt.value
            continue

        if isinstance(stmt, (ast.Return, ast.Expr, ast.Raise, ast.Assert, ast.AugAssign)):
            for cmp_node in _comparisons_in(stmt):
                _check_comparison(cmp_node, env, funcs, consts, params, path, findings)
            continue

        for block in ("body", "orelse", "finalbody"):
            nested = getattr(stmt, block, None)
            if nested:
                _walk_block(nested, dict(env), funcs, consts, params, path, findings, opaque)
        for handler in getattr(stmt, "handlers", []) or []:
            _walk_block(handler.body, dict(env), funcs, consts, params, path, findings, opaque)


def _tests_of(stmt):
    if isinstance(stmt, (ast.If, ast.While)):
        return [stmt.test]
    return []


def _comparisons_in(node, skip_nested_blocks=False):
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare):
            out.append(sub)
    return out


def find_sources(root):
    base = os.path.join(root, "parts")
    if not os.path.isdir(base):
        base = root
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE]
        for name in sorted(filenames):
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def main(argv):
    root = os.path.realpath(argv[1]) if len(argv) > 1 else \
        os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sources = find_sources(root)
    findings = []
    del TOO_DEEP[:]
    for path in sources:
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            findings.extend(check_source(stream.read(), os.path.relpath(path, root)))
    print("dead gates: %d generator source(s) scanned" % len(sources))
    if TOO_DEEP:
        print("  %d comparison(s) too deep to expand were left unjudged: %s" % (
            len(TOO_DEEP), ", ".join("%s:%d" % row for row in TOO_DEEP[:6]) + (" ..." if len(TOO_DEEP) > 6 else "")))
    if not findings:
        print("  no assertion reduces to a constant")
        print("DEAD_GATE_RESULT: PASS")
        return 0
    for path, line, rule, message in findings:
        print("  [%s] %s:%d" % (rule, path, line))
        print("        %s" % message)
    print("  A gate that cannot fire is worse than none: it produces confidence instead of")
    print("  caution. Fix the expression, or delete the assertion and say why it went.")
    print("DEAD_GATE_RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
