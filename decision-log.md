# Stage 8 Decision Log

Intern: UBI-2026-0099 - Set D5 - Evidence marker: UBI-A8-0725D08E95BE

## DL-001 - Host OS and OpenSCAP profile selected by the candidate

**Decision:** Rocky Linux 9 with the CIS Level 1 Server profile from the
distribution's SCAP Security Guide.

**Why this was a decision at all:** brief.md instructs the candidate to "choose
the profile specified in the private assignment", but the D5 overlay specifies
only the treatment budget (USD 85,000) and the 30% uncertainty sensitivity test.
No OS or profile ID appears in the overlay or anywhere in the assigned archive.
The project FAQ resolves this: "Use a fresh Debian 12 or Rocky Linux 9 VM with
the appropriate pinned OpenSCAP or SCAP Security Guide profile... Record the
exact OS image and tool or profile versions." The selection is therefore the
candidate's, and the requirement is to pin and record it.

**Evidence used:** the overlay, brief.md, the project FAQ, and the enumerated
profile list captured in `before/oscap-info.txt`.

**Alternatives considered and why weakened:**
- *Debian 12* - SCAP Security Guide profile coverage for Debian is thinner than
  for RHEL 9 derivatives. Measurable delta is 15% of the rubric and depends on
  the profile surfacing enough remediable findings to compare.
- *CIS Level 2 / STIG* - both contain rules that conflict with the declared
  service contract and produce a much larger finding set, making the before/after
  delta harder to reconcile rule by rule. Level 1 is designed to be applied to a
  working server without breaking it, which matches the zero-service-regression
  constraint.

**Review trigger:** staff issue a specific profile for set D5.

## DL-002 - Vagrantfile modified to pass the evidence marker to the guest

**Decision:** added an `env:` mapping to the shell provisioner so
`NETFORGE_MARKER` reaches `baseline.sh` inside the VM.

**Change:**

    - node.vm.provision "shell", path: "baseline.sh", args: [name]
    + node.vm.provision "shell", path: "baseline.sh", args: [name],
    +   env: { "NETFORGE_MARKER" => ENV.fetch("NETFORGE_MARKER") }

**Why:** `baseline.sh` reads `NETFORGE_MARKER` and falls back to
`UBI-A8-STAFF-MUST-REPLACE`. Vagrant shell provisioners do not inherit the host
shell environment, so the supplied Vagrantfile would have stamped the fallback
value into `/srv/netforge-service/index.html` - the string the web service
acceptance test greps for. The overlay requires the assigned marker to appear in
setup evidence, the evidence index, and the integrity attestation.

**Provenance:** the supplied source is preserved unmodified and read-only in
`raw-evidence/evidence/lab-source/`. The working copy is `lab/`.

**Verification:** after `vagrant up rocky`, `curl -s http://127.0.0.1:8080/`
must return `synthetic-service-marker=UBI-A8-0725D08E95BE`.
