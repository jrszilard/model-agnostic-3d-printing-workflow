# Start or resume a 3D-printing task — any model, any client

No special agent, memory service or plugin required. If this client doesn't load instructions, open the owner's `AGENTS.md` and the [portable contract](../AGENTS.md) explicitly. Use [workflow.md](../../docs/workflow.md) for design and [preparation.md](../../docs/preparation.md) for preparation. This card routes to those authorities; it doesn't replace them.

**New design?** Identify the intended use, mating parts, units, physical unknowns and requested deliverable (concept, editable project, fit test, or release). Mark measured vs proposed. Start in the owner's checkout. Open the real exported views for a design decision; a model without vision should ask for a human to review them, not describe an unseen render.

**Existing job?** Identify the exact part or plate from the request and evidence, not just a nickname or a date. If two versions plausibly match, pass both directories to the command below. It lists their states and evidence but never picks the newest or greenest. Name them to the operator by contents, not by demanding they know a filesystem path. From the bench root, replacing `PATH` with that directory:

```sh
python3 platform/pipeline/next_action.py PATH --json
```

Read **`action`, `stop`, `blockers`, `unknown`, `evidence`, `review_paths`**. `schema: 1` is a read-only snapshot, not a send token; exit 0 means *inspected*. `stop: true` means do not advance the job unattended. You may read evidence or present it. Even `stop: false` only suggests a digital step. No shell? Ask the operator to run that command and paste its JSON. No files or exact path? Ask for them; do not invent status. No context left? Save the card below instead of the whole transcript.

| `action` | What to do now |
|---|---|
| `clarify_target`, `clarify_scope` | State the competing versions or held contents and ask the one question in `question`. Do not guess, revise, slice or ask for print approval. A selection is not an approval. |
| `identify_target`, `locate_recipe` | Resolve the missing owner, directory or recipe. One part’s `prepare.sh` is **not** a two-primary kit runner. |
| `review_project` | Present the 3MF; no adjacent verified G-code was found. Keep unsliced, material variants and installed assemblies separate. |
| `capture_inventory`, `register_inventory_models` | Use the independently requested IDs/quantities, then the named single-piece meshes. Requested is not sliced. Do not fill either from the finished plate. |
| `preflight`, `prepare_handoff` | Run the owning read-only preflight or the real digital handoff as indicated. These do not upload. |
| `inspect_blocker`, `escalate`, `inspect_preparation` | Read the named log/exit; fix the cause with the owner. One changed-input repair, then escalate. Do not clean an unrelated tree or run the same failure again. |
| `rebuild_handoff` | Review bytes/identity changed or are missing. Reverify and present the new packet. Old approval does not transfer. |
| `review_handoff` | Present exact project, G-code, views, support and verification paths, quantities, material, time and physical debt. **Stop for fresh per-plate human approval.** Upload and start are separate intents. |
| `inspect_receipt`, `do_not_resend`, `await_observation` | Reconcile uncertain sends without another upload; respect a matching receipt. A start receipt is not live status, a finished print, or measured fit. |

**Inventory before handoff:** Record the **requested** piece IDs and quantities from the selected brief before slicing (`plate_inventory.py request`). Register a named, single-piece CAD mesh for each distinct ID (`catalog`). Never derive the request from the slice, STL input rows, weight or number of STEP solids. `handoff.sh` compares the final 3MF **and actual model extrusion in the final G-code** by ID. Show its table. Exit 19: `python3 platform/pipeline/plate_inventory.py check PATH --json` explains the mismatch or missing evidence. Fix the input/registration or ask which quantity was intended; don't change the request to make the report green. [Commands, example and supported scope](README.md#requested-versus-sliced-inventory).

**Who decides?**

| If the missing answer is… | Next move |
|---|---|
| In the files (counts on a plan, material preset, exact bytes, prior send) | Run the checker or read the manifest/receipt. Report the evidence; don't ask the operator to reconstruct it. A planned or sliced count is not the number of usable pieces off the bed. |
| A choice that changes the result (which version, parts/quantities, mate, material, or deliverable) | Say what is known, give the actual options, ask **one** question, and wait on the affected work. For geometry use the labelled drawing. If the request and files already settle it, proceed with the permitted digital step without asking again. |
| A physical fact or permission (actual fit, load, approval to upload, request to start) | Ask the observing operator only for what's missing. Do not pass approval to another plate or treat an upload as a start request. |

If an **existing plate** is parked, persist the reason and the question with `python3 platform/pipeline/plate_scope.py hold PATH --reason '...' --question '...?'`. No known target yet? Compare candidates read-only or ask; don't park unrelated plates. On a later model switch rerun `next_action.py`; never act from an old JSON snapshot. If the answer selects different contents, leave the old plate held and use a new scoped output. If it explicitly confirms this same, unsent scope, `plate_scope.py reopen-for-review PATH --answer 'actual reply'` archives the prior handoff and question. Recheck and present a fresh handoff; clarifying scope does not authorize transfer. [Command contract](README.md#when-a-ready-plate-is-not-the-requested-plate).

**Look up, don't memorize:** `python3 platform/pipeline/gates.py exit 15` explains a refusal. Before expensive work on a part headed to print, `python3 platform/pipeline/verify/qualification_check.py part PART_DIR` checks its design/status contract; for a kit check *each* authored part. The real handoff will check again. Never substitute one model's judgment for a failed gate.

**For a model switch:** Put this small card in the session note, or paste it into a new client. Treat it as a pointer, not authority. Record changed intent immediately (e.g. PLA replaces PETG); derive the current action again from disk.

```text
Goal / requested deliverable:
Owner + exact part/plate directory:
User constraints (material/preset, preserve geometry/other people's work):
Evidence to reopen (paths and relevant short hashes):
Unresolved physical or design question; next actor:
```

Keep session notes in your consumer repository's local workflow/notes location (or your own knowledge base). Never carry approval flags, credentials or a claim of physical qualification in a resume card.

[Cold-start and model-swap trial](agent-trials/README.md) · [Gate registry](gates.txt)
