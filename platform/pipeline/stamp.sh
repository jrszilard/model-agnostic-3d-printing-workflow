#!/usr/bin/env bash
# stamp.sh — artifact identity. Sourced by render.sh / slice.sh / handoff.sh.
#
# WHY
# The handoff presents a plate's gcode next to the part's preview PNGs and asks a human to approve
# what they see. Nothing tied those two together: the previews were whatever PNGs happened to be in
# preview/, rendered from whatever STL existed at the time. Regenerate the geometry, re-slice, and
# the preview on screen can be a DIFFERENT VERSION of the part than the one in the gcode — and the
# gate would still say COMPLETE, because it only ever checked that the files existed.
#
# A geom id is the first 8 hex of the STL's sha256. Every downstream artifact records the geom id
# it was made from, and handoff.sh refuses when they disagree. Identity travels with the bytes, so
# it cannot drift the way a filename or a timestamp can.
set -uo pipefail

# Normalise before hashing. c14n rewrites CadQuery STLs too (they are deterministic but not in
# canonical facet order), so if only the commit gate canonicalised, a preview stamped from the raw
# export would disagree with the committed file and the whole identity chain would drift. Hashing
# the canonical form makes the geom id independent of how the STL was produced. Idempotent.
canon_stl(){
    case "$1" in *.stl) python3 "$(dirname "${BASH_SOURCE[0]}")/generate/c14n_stl.py" "$1" >/dev/null 2>&1;; esac
}
geom_id(){ canon_stl "$1"; sha256sum "$1" 2>/dev/null | cut -c1-8; }
geom_sha(){ canon_stl "$1"; sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# One line naming the repo state, for the human reading a handoff.
version_line(){
    local br sha dirty tag
    br=$(git branch --show-current 2>/dev/null || echo '?')
    sha=$(git rev-parse --short HEAD 2>/dev/null || echo '?')
    [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty=" +dirty" || dirty=""
    tag=$(git tag --points-at HEAD 2>/dev/null | grep -E '^(passed|green)/' | head -1)
    echo "${br}@${sha}${dirty}${tag:+ · $tag}"
}

# write_stamp <artifact-or-dir> <source.stl> [extra k=v ...]
write_stamp(){
    local target=$1 src=$2; shift 2
    {
        echo "geom=$(geom_id "$src")"
        echo "sha256=$(geom_sha "$src")"
        echo "source=$src"
        echo "version=$(version_line)"
        while [ $# -gt 0 ]; do echo "$1"; shift; done
    } > "$target"
}

stamp_get(){ [ -f "$1" ] && sed -n "s/^$2=//p" "$1" | head -1; }
