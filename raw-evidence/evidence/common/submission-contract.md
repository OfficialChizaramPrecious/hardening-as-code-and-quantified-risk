# Advanced Stage Submission Contract

This contract applies to every Advanced Stage project. A technically correct
report can still fail if its evidence cannot be verified.

## Submission root

Submit one view-only folder. Its root must contain:

1. Every filename listed in the project room.
2. `evidence-index.csv` completed from the supplied template.
3. `manifest.sha256` covering every submitted file except itself.
4. `integrity-attestation.md`, signed and dated.
5. `README.md` with tool and operating-system versions, the assigned variant,
   the evidence marker, and exact reproduction order.
6. `assessment-manifest.json`, completed from the supplied template with the
   frozen commit, clean/provision/build/test commands, test report locator,
   runtime, peak memory where required, and output hashes.
7. `continuity-record.md`, identifying the prior-stage component reused, its
   commit/interface, migrations, preserved provenance, and next-stage handoff.

Before analysis, copy the assigned archive filename, SHA-256, candidate binding,
and staff-issued manifest signature into `assessment-manifest.json`. If the
downloaded hash does not match the dashboard, stop and report it; do not repair
or silently replace the pack.

Directories may contain additional files. Do not rename required files. Do not
submit archives inside archives.

## Evidence standard

Each material claim must identify:

- the raw artifact filename;
- an exact locator: line, event ID, packet/frame, query, request ID, control ID,
  ticket, or timestamp;
- what the artifact proves;
- what it does not prove;
- confidence (`high`, `medium`, or `low`) and why;
- one plausible alternative considered and the evidence that weakened it.

Screenshots are orientation aids, not primary proof. Preserve raw exports in
their native format. A transformed file must have a documented source and
reproduction command.

## Integrity and provenance

Record SHA-256 hashes before opening the assigned pack. Keep source artifacts
read-only. Put derived files in a separate directory. Preserve timestamps and
time zones. Never backdate git commits, rewrite raw evidence, or stage a result
that was not produced by the submitted method.

Assistance from documentation, peers, or AI tools must be declared in the
attestation. Assistance is not authorship. You remain responsible for every
claim and must reproduce the work during defense.

## Defense

The panel may ask you to:

- locate a decisive artifact;
- rerun a query, control test, or proof step;
- run a public or hidden fixture from a clean state;
- apply one bounded input, schema, policy, or configuration change;
- trace the changed machine output back to raw evidence and implementation.

Failure to reproduce a central claim may reduce the affected criterion to zero.
Fabricated evidence, out-of-scope activity, or another person's work is an
integrity failure and is escalated outside ordinary grading.

## Revision progression

- Projects 1-3: one revision may be allowed within the open window.
- Projects 4-5: no revision after submission.
- A pressure task cannot repair a failed safety, integrity, scope, or proof gate.

## Hash command

From the submission root on Linux or macOS:

```bash
find . -type f ! -name manifest.sha256 -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 > manifest.sha256
```

On Windows PowerShell, record each relative path and hash:

```powershell
Get-ChildItem -Recurse -File | Where-Object Name -ne 'manifest.sha256' |
  Sort-Object FullName | ForEach-Object {
    "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)  $($_.FullName)"
  } | Set-Content manifest.sha256
```
