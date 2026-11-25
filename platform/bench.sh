#!/usr/bin/env bash
# bench.sh — the change-safety workflow for a repo whose deliverables are BINARY.
#
# WHY THIS IS A SCRIPT AND NOT A CONVENTION
# The same reason handoff.sh is a script. A rule that lives only in prose gets rationalised away
# mid-flow ("this tweak is small, I'll just commit it to main"), and the tweak that regenerates
# 107 STLs is exactly the one you want to be able to walk back from. These verbs refuse.
#
# THE MODEL
#   main            the last state that was GOOD ON THE BENCH. Stays printable at all times.
#   rev/<slug>      one revision's work. Checkpoint freely — cheap, disposable, local.
#   green/<slug>-N  tag: the fast digital loop went green (docs/workflow.md ②). Machine-checkable.
#   passed/<slug>-N tag: cleared the REALITY / FUNCTIONAL gate (④). This is "the last version that
#                   worked". Like APPROVED=1, it is the human's to type — CONFIRMED=1 required.
#   landed/<slug>   a revision that shipped to main, its checkpoints kept for KEEP_REVS more
#                   revisions, then swept by `prune`. Tags outlive the sweep; saves do not.
#   abandoned/<slug> a revision you walked away from. Never deleted, only renamed out of the way.
#
# THE ONE HARD RULE: SOURCE IS THE MERGE UNIT; GEOMETRY IS REGENERATED, NEVER MERGED.
# stl/step/3mf/png are binary. Git cannot three-way-merge them, and neither can you. If both sides
# touched the same geometry, the resolution is always "take the branch's source, rebuild" — never
# a hand-edit of a mesh. `land` refuses rather than guessing, and tells you which is which.
#
# Usage:
#   bench.sh start <slug>                branch off main for a revision  (refuses a dirty tree)
#
# ALL WORK HAPPENS IN THIS CHECKOUT, ai-projects/3d-printing. Never a sibling folder: no
# `git worktree add`, no ai-projects/3d-printing-<anything>. Justin's rule, 2026-09-18, after agents
# kept leaving parts in 3d-printing-lap-shim / 3d-printing-rev-* copies that prepare and handoff
# then refuse to build from. `--worktree` used to create exactly those folders; it now refuses.
#   bench.sh save "<note>"               checkpoint on the branch        (runs test.sh)
#   bench.sh green "<note>"              tag: digital loop is green
#   bench.sh passed "<note>" <qa-record> tag: physical gate cleared      (CONFIRMED=1 required)
#   bench.sh land -m "<message>"         squash the revision onto main   (runs test.sh)
#   bench.sh land --continue -m "<msg>"  finish a land after resolving conflicts
#   bench.sh back [<tag|ref>]            list the restore ladder, or restore one (never destroys)
#   bench.sh drop                        abandon this revision; main untouched
#   bench.sh status                      where am I, what is pinned, what would prune drop
#   bench.sh prune                       sweep old landed/* refs + gc    (CONFIRMED=1 required)
#
# Env: SKIP_TESTS=1 (save only)  KEEP_REVS=n (default 2)  CONFIRMED=1 (passed, prune)
# Exit: 2 usage · 3 wrong state · 4 dirty tree · 5 tests failed · 6 conflicts · 9 not confirmed
set -uo pipefail
. "$(dirname "$(readlink -f "$0")")/pipeline/gates.sh"

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not a git repo" >&2; exit 2; }
cd "$ROOT" || exit 2
GITDIR=$(git rev-parse --git-dir)
MAIN=main
KEEP_REVS=${KEEP_REVS:-2}
BIN_RE='\.(stl|step|stp|3mf|FCStd|png|jpg|jpeg|pdf|gcode|bgcode)$'

die(){ echo "REFUSING: $1" >&2; shift; while [ $# -gt 0 ]; do [ -n "$1" ] && echo "  $1" >&2 || echo >&2; shift; done; }
cur_branch(){ git branch --show-current; }
slug_of(){ cur_branch | sed -E 's#^(rev|restore|landed|abandoned)/##'; }

require_clean(){
    [ -z "$(git status --porcelain)" ] && return 0
    die "the working tree is dirty — a change-safety workflow can't start by losing changes." \
        "" "  git status --short" "" \
        "if it is YOUR work: checkpoint it (bench.sh save \"...\")." \
        "if it is ANOTHER session's work: do not stash it, do not make a worktree or a sibling" \
        "folder. Branch in place, 'git switch -c rev/<slug>', and stage only your own paths."
    exit 4
}
require_rev(){
    case "$(cur_branch)" in
        rev/*|restore/*) return 0 ;;
        "") die "detached HEAD — 'bench.sh back <ref>' makes a branch instead."; exit 3 ;;
        *) die "you are on '$(cur_branch)', not a revision branch." \
               "" "  bench.sh start <slug>    to open one"; exit 3 ;;
    esac
}
# Canonicalise at the COMMIT gate, not only at the build gate. build.sh applies c14n, but every
# part README documents running the exporter directly (`~/cadquery-env/bin/python src/<part>.py`),
# and on that path OCCT's wall-clock STEP header and OpenSCAD's random facet order go straight into
# git — which is exactly the churn untracking regenerable geometry was meant to end. Whatever route
# the bytes took, they get normalised before they are committed.
canonicalise_geometry(){
    local gen="platform/pipeline/generate" n
    n=$(git status --porcelain -- '*.step' '*.stl' | awk '{print $NF}' | grep -c . ) || n=0
    [ "$n" = 0 ] && return 0
    git status --porcelain -- '*.step' | awk '{print $NF}' | tr '\n' '\0' \
        | xargs -0 -r python3 "$gen/c14n_step.py" >/dev/null 2>&1
    git status --porcelain -- '*.stl' | awk '{print $NF}' | tr '\n' '\0' \
        | xargs -0 -r python3 "$gen/c14n_stl.py" >/dev/null 2>&1
    echo "canonicalised $n changed geometry file(s) before staging"
}
run_tests(){
    echo "=== platform/pipeline/test.sh ==="
    if ! platform/pipeline/test.sh; then
        die "tests are red. main must stay printable, so this does not proceed." \
            "" "  fix them, or (checkpoints only) SKIP_TESTS=1 bench.sh save \"...\""
        exit 5
    fi
}
# Tag names auto-increment per slug so a revision can hold several gates without collision.
next_tag(){  # next_tag <kind> <slug>
    local n=1
    while git rev-parse -q --verify "refs/tags/$1/$2-$n" >/dev/null; do n=$((n+1)); done
    echo "$1/$2-$n"
}
tag_gate(){  # tag_gate <note> <kind>
    require_rev
    local slug note tag; slug=$(slug_of); note=${1:?}
    tag=$(next_tag "$2" "$slug")
    git tag -a "$tag" -m "$note" || exit 3
    echo "pinned $tag -> $(git rev-parse --short HEAD)"
    echo "  $note"
    echo
    echo "tags are permanent — 'bench.sh prune' never removes them."
}

case "${1:-}" in

start)
    slug=${2:?usage: bench.sh start <slug>}
    if [ "${3:-}" = "--worktree" ]; then
        die "--worktree is retired: all work happens in ai-projects/3d-printing itself." \
            "" "  A sibling copy (ai-projects/3d-printing-rev-*) is not a delivery root: prepare and" \
            "  handoff refuse to build from it, and parts left there get lost. Branch in place."
        exit 2
    fi
    slug=$(echo "$slug" | tr ' _' '--' | tr -cd '[:alnum:]-')
    [ -n "$slug" ] || { echo "empty slug" >&2; exit 2; }
    git rev-parse -q --verify "refs/heads/rev/$slug" >/dev/null && {
        die "rev/$slug already exists." "" "  git switch rev/$slug     to resume it"; exit 3; }
    require_clean
    [ "$(cur_branch)" = "$MAIN" ] || { die "start from $MAIN (you are on $(cur_branch))."; exit 3; }
    git switch -c "rev/$slug" || exit 3
    echo
    echo "on rev/$slug, based at $(git rev-parse --short "$MAIN"). $MAIN is now frozen good."
    echo "  bench.sh save \"<note>\"    checkpoint (as often as you like)"
    echo "  bench.sh land -m \"<msg>\"  when it is good"
    ;;

save)
    note=${2:?usage: bench.sh save \"<note>\"}
    require_rev
    [ -n "$(git status --porcelain)" ] || { echo "nothing to checkpoint (tree is clean)."; exit 0; }
    [ "${SKIP_TESTS:-0}" = 1 ] && echo "NOTE: SKIP_TESTS=1 — this checkpoint is unverified." || run_tests
    canonicalise_geometry
    git add -A || exit 3
    git commit -q -m "$note" || exit 3
    echo "checkpoint $(git rev-parse --short HEAD) on $(cur_branch): $note"
    ;;

green)   tag_gate "${2:?usage: bench.sh green \"<note>\"}" green ;;

passed)
    note=${2:?usage: bench.sh passed \"<note>\" <qa-record>}
    # Deliberately mirrors send.sh's APPROVED=1. "It passed the reality gate" is a claim about a
    # PHYSICAL object — a machine cannot check it and an agent must never assert it. This is the
    # tag `bench.sh back` will offer as the last known-good version, so it has to be earned.
    if [ "${CONFIRMED:-0}" != 1 ]; then
        die "'passed' asserts a physical gate was cleared — that is the human's to type." \
            "" "  CONFIRMED=1 bench.sh passed \"$note\" <qa-record>"
        exit 9
    fi
    evidence=${3:?usage: bench.sh passed \"<note>\" <qa-record>}
    require_rev
    require_clean
    evidence_abs=$(readlink -f "$evidence" 2>/dev/null) || true
    case "$evidence_abs" in
        "$ROOT"/*) evidence_rel=${evidence_abs#"$ROOT"/} ;;
        *) die "physical evidence must live inside this repository: $evidence"; exit 2 ;;
    esac
    [ -f "$evidence_abs" ] || { die "physical evidence does not exist: $evidence"; exit 2; }
    git ls-files --error-unmatch "$evidence_rel" >/dev/null 2>&1 || {
        die "physical evidence is not committed; the passed tag would not contain it." \
            "" "  bench.sh save \"record physical result\""; exit 3; }
    _qcheck=$(python3 "$ROOT/platform/pipeline/verify/qualification_check.py" record \
        "$evidence_abs" --require-state passed --require-current 2>&1)
    printf '%s\n' "$_qcheck"
    gate_allows QUALIFICATION_RECORD_RESULT "$_qcheck" || {
        die "the named record does not prove a complete, current human physical pass."; exit 5; }
    evidence_sha=$(sha256sum "$evidence_abs" | awk '{print $1}')
    tag_gate "$note

Physical evidence: $evidence_rel
Physical evidence SHA256: $evidence_sha
evidence=$evidence_rel
evidence_sha256=$evidence_sha" passed
    ;;

land)
    shift
    CONT=0; MSG=""
    while [ $# -gt 0 ]; do case "$1" in
        --continue) CONT=1 ;;
        -m) shift; MSG=${1:-} ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac; shift; done

    if [ "$CONT" = 1 ]; then
        [ "$(cur_branch)" = "$MAIN" ] || { die "--continue runs on $MAIN, mid-land."; exit 3; }
        slug=$(cat "$GITDIR/bench-landing" 2>/dev/null) || true
        [ -n "$slug" ] || { die "no land in progress."; exit 3; }
        if ! git rev-parse -q --verify "refs/heads/rev/$slug" >/dev/null; then
            rm -f "$GITDIR/bench-landing"
            die "stale land marker for rev/$slug — that branch is gone. Cleared it." ; exit 3
        fi
        [ -n "$MSG" ] || { die "-m \"<message>\" is required."; exit 2; }
        # Check BEFORE staging: `git add -A` on a conflicted file marks it resolved and commits the
        # conflict markers verbatim, so staging first destroys the very evidence being tested for.
        if git diff --diff-filter=U --name-only | grep -q .; then
            die "still unmerged — resolve these, then re-run:" ""
            git diff --diff-filter=U --name-only | sed 's/^/    /' >&2
            exit 6
        fi
        git add -A || exit 3
        run_tests
        git commit -q -m "$MSG" || exit 3
        git branch -m "rev/$slug" "landed/$slug" 2>/dev/null
        rm -f "$GITDIR/bench-landing"
        echo "landed rev/$slug -> $MAIN as $(git rev-parse --short HEAD)"
        exit 0
    fi

    require_rev
    require_clean
    slug=$(slug_of); branch=$(cur_branch)
    base=$(git merge-base "$MAIN" HEAD)
    [ "$base" != "$(git rev-parse HEAD)" ] || { die "no commits on $branch to land."; exit 3; }
    [ -n "$MSG" ] || MSG=$(git log -1 --pretty=%s)
    run_tests

    n=$(git rev-list --count "$MAIN..HEAD")
    if [ "${branch#restore/}" = "$branch" ]; then
        git tag -l "passed/$slug-*" | grep -q . || \
            echo "NOTE: no passed/$slug tag — landing a revision no physical gate has cleared."
    fi

    # A ROLLBACK IS NOT A MERGE. Landing restore/* by merging would conflict on every binary
    # (both sides moved from the base), and "resolve" would mean hand-picking meshes. The correct
    # semantic is "main's tree becomes THIS tree, exactly" — one commit, zero conflicts, and the
    # commits being backed out stay in history, reachable, un-rewritten.
    if [ "${branch#restore/}" != "$branch" ]; then
        tree=$(git rev-parse "HEAD^{tree}")
        # Only commits main has that this tree does not represent. Using merge-base here listed the
        # very commit being restored to as "backed out", because a squash landing shares no parent.
        dropped=$(git log --oneline --cherry-pick --right-only "HEAD...$MAIN" 2>/dev/null)
        if ! git switch -q "$MAIN" 2>/dev/null; then
            die "cannot check out $MAIN here — it is checked out in another worktree."; exit 3
        fi
        if [ -n "$dropped" ]; then
            echo "backing out of these — they stay in history, they just stop being current:"
            echo "$dropped" | sed 's/^/  /'
            echo
        fi
        git read-tree -u --reset "$tree" || exit 3
        git commit -q -m "$MSG" || { die "$MAIN already has exactly this tree — nothing to roll back."; git switch -q "$branch"; exit 3; }
        git branch -m "$branch" "landed/$slug" 2>/dev/null
        echo "rolled $MAIN back to $branch as $(git rev-parse --short HEAD)"
        echo "  every geometry file now matches that state; nothing was rewritten."
        echo "  kept as landed/$slug"
        exit 0
    fi

    if ! git switch -q "$MAIN" 2>/dev/null; then
        die "cannot check out $MAIN here — it is checked out in another worktree." \
            "" "  git worktree list" "  land from the worktree that holds $MAIN."
        exit 3
    fi
    if [ "$base" = "$(git rev-parse "$MAIN")" ]; then
        git merge --squash "$branch" >/dev/null || { git reset --hard HEAD >/dev/null 2>&1; exit 3; }
    else
        echo "$MAIN moved since this revision started — attempting the squash."
        if ! git merge --squash "$branch" >/dev/null 2>&1; then
            echo "$slug" > "$GITDIR/bench-landing"
            conflicts=$(git diff --name-only --diff-filter=U)
            echo
            die "conflicts. Geometry is never merged — it is regenerated." ""
            echo "  TEXT (resolve by hand):" >&2
            echo "$conflicts" | grep -Ev "$BIN_RE" | sed 's/^/    /' >&2
            echo "  BINARY (take the revision's, then rebuild from src/):" >&2
            echo "$conflicts" | grep -E "$BIN_RE" | sed 's/^/    /' >&2
            echo >&2
            echo "  git checkout --theirs <binary paths> && git add <them>" >&2
            echo "  # regenerate: platform/pipeline/generate/build.sh <src> <outdir>" >&2
            echo "  bench.sh land --continue -m \"$MSG\"" >&2
            echo "  # or back out entirely:  git reset --hard HEAD && git switch $branch" >&2
            echo "  #   (a squash merge writes no MERGE_HEAD, so there is nothing for git to abort)" >&2
            exit 6
        fi
    fi
    git commit -q -m "$MSG" || { die "nothing staged — did the branch change anything?"; exit 3; }
    git branch -m "$branch" "landed/$slug" 2>/dev/null
    echo "landed $branch -> $MAIN as $(git rev-parse --short HEAD)"
    echo "  $n checkpoint(s) squashed into one commit; full detail kept on landed/$slug"
    echo "  tags on this revision:" $(git tag -l "green/$slug-*" "passed/$slug-*" | tr '\n' ' ')
    ;;

back)
    if [ -z "${2:-}" ]; then
        echo "=== the restore ladder (newest first) ==="
        echo
        echo "PASSED — cleared a physical gate. These are the known-good versions:"
        git for-each-ref --sort=-creatordate --format='  %(refname:short)  %(creatordate:short)  %(contents:subject)' refs/tags/passed 2>/dev/null | grep . || echo "  (none yet)"
        echo
        echo "GREEN — digital loop only, not physically proven:"
        git for-each-ref --sort=-creatordate --format='  %(refname:short)  %(creatordate:short)  %(contents:subject)' refs/tags/green 2>/dev/null | grep . || echo "  (none yet)"
        echo
        echo "LANDED — full checkpoint detail, kept for the last $KEEP_REVS revisions:"
        git for-each-ref --sort=-committerdate --format='  %(refname:short)  %(committerdate:short)' refs/heads/landed 2>/dev/null | grep . || echo "  (none yet)"
        echo
        echo "restore one:  bench.sh back <name>     (opens restore/<name>; nothing is destroyed)"
        exit 0
    fi
    ref=$2
    git rev-parse -q --verify "$ref" >/dev/null || { die "no such tag/ref: $ref" "" "  bench.sh back    lists them"; exit 3; }
    require_clean
    name="restore/$(echo "$ref" | tr '/' '-')"
    i=1; while git rev-parse -q --verify "refs/heads/$name" >/dev/null; do i=$((i+1)); name="restore/$(echo "$ref" | tr '/' '-')-$i"; done
    git switch -c "$name" "$ref" || exit 3
    echo
    echo "on $name at $ref — $MAIN is untouched and still has everything newer."
    echo "  to make this the current state:  bench.sh land -m \"back out to $ref: <why>\""
    ;;

drop)
    require_rev
    slug=$(slug_of); branch=$(cur_branch)
    require_clean
    git switch -q "$MAIN" || exit 3
    dest="abandoned/$slug"; i=1
    while git rev-parse -q --verify "refs/heads/$dest" >/dev/null; do i=$((i+1)); dest="abandoned/$slug-$i"; done
    git branch -m "$branch" "$dest" || exit 3
    echo "abandoned: $branch -> $dest (kept, not deleted). $MAIN never saw it."
    ;;

status)
    b=$(cur_branch); echo "branch:   ${b:-<detached>}"
    case "$b" in
        rev/*|restore/*)
            slug=$(slug_of)
            echo "base:     $(git rev-parse --short "$(git merge-base "$MAIN" HEAD)") on $MAIN"
            echo "saves:    $(git rev-list --count "$MAIN..HEAD") checkpoint(s) since"
            echo "pinned:  " $(git tag -l "green/$slug-*" "passed/$slug-*" | tr '\n' ' ')
            ;;
        "$MAIN") echo "state:    frozen good — 'bench.sh start <slug>' to change anything geometric" ;;
    esac
    d=$(git status --porcelain | wc -l); echo "dirty:    $d file(s)"
    echo
    kg=$(git for-each-ref --sort=-creatordate --format='%(refname:short)' refs/tags/passed 2>/dev/null | head -1)
    echo "known-good: ${kg:-none yet — nothing has cleared a physical gate under this workflow}"
    stale=$(git for-each-ref --sort=-committerdate --format='%(refname:short)' refs/heads/landed 2>/dev/null | tail -n +$((KEEP_REVS+1)))
    echo "prune would drop:" $([ -n "$stale" ] && echo "$stale" | tr '\n' ' ' || echo "nothing")
    ;;

prune)
    stale=$(git for-each-ref --sort=-committerdate --format='%(refname:short)' refs/heads/landed 2>/dev/null | tail -n +$((KEEP_REVS+1)))
    if [ -z "$stale" ]; then
        echo "nothing to sweep (keeping the newest $KEEP_REVS landed/* refs)."
    else
        echo "these landed revisions drop their intermediate checkpoints:"
        echo "$stale" | sed 's/^/  /'
        echo
        echo "their green/ and passed/ tags SURVIVE — only unapproved saves go."
        if [ "${CONFIRMED:-0}" != 1 ]; then
            die "this deletes refs. Confirm it." "" "  CONFIRMED=1 bench.sh prune"; exit 9
        fi
        echo "$stale" | while read -r r; do [ -n "$r" ] && git branch -D "$r"; done
    fi
    echo; echo "packing..."
    # A bare `git gc` honours gc.pruneExpire=2.weeks and keeps unreachable objects still named by
    # the HEAD reflog for 30 days, so the geometry behind a just-swept landed/* would survive and
    # the verb would do nothing it claims. Expire first, then prune for real.
    git reflog expire --expire-unreachable=now --all
    git gc --prune=now
    git count-objects -vH | grep -E 'size-pack|count'
    ;;

*)
    sed -n '/^# Usage:/,/^# Exit:/p' "$0" | sed 's/^# \{0,1\}//'
    exit 2 ;;
esac
