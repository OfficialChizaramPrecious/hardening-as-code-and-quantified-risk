# Stage 8 - Hardening as Code and Quantified Risk

Submission package for UBI Advanced Project 4.

| | |
|---|---|
| Intern | UBI-2026-0099 |
| Track | GRC |
| Private assignment set | **D5** |
| Evidence marker | **UBI-A8-0725D08E95BE** |
| Treatment budget | USD 85,000 |
| Sensitivity band | ±30% on annual-loss ranges |

**Assigned archive:** `grc-stage-8-shared-b1.tar.gz`, 11,977 bytes
**SHA-256:** `9be5e36adc4d906f0fdac3b2a893da3bfb4b994e7423c0ee3cc320ca265e283b`

Verified against the dashboard value before extraction. Preserved unmodified in
`raw-evidence/`.

---

## Package overview

The package is divided into two independently testable areas.

**Host hardening.** An idempotent Ansible role applying eleven CIS Level 1
Server controls to a Rocky Linux 9 host, a separate rollback role that restores
the declared baseline, a testinfra acceptance suite, and before/after scanner
evidence with a rule-by-rule reconciliation.

**Quantified risk.** This is a deterministic Monte Carlo model that simulates
twelve risks derived from the supplied vulnerability export, prices candidate
treatments, and selects exactly three within the USD 85,000 budget, including a
30% uncertainty sensitivity test.

### Results

| | |
|---|---|
| OpenSCAP before | 101 fail / 159 pass / 33 n-a / 0 error |
| OpenSCAP after | 86 fail / 174 pass / 33 n-a / 0 error |
| Rules fixed | **15** (requirement: 8) |
| Regressions | **0** |
| Lynis hardening index | 66 → 70 |
| Second playbook run | `changed=0` |
| Rollback | `sshd -T` byte-identical to baseline |
| Host acceptance suite | 57 tests, 0 failures |
| Risk model suite | 183 tests, 0 failures |
| Unattended lifecycle | 8 stages, 14 checks, PASS |
| Treatments funded | R-002, R-006, R-008 - USD 73,000 |
| Selection stability | Same three at 0.70x, 1.00x, 1.30x |

---

## Environment and tooling

### Workstation (risk-model control node)

| Component | Version |
|---|---|
| OS | Microsoft Windows 11 Pro |
| Python | 3.11.9 |
| NumPy | **2.1.3** (pinned - the PCG64 stream is version-sensitive) |
| pytest | 9.1.1 |
| jsonschema | 4.26.0 |
| Vagrant | 2.4.9 |
| VirtualBox | 7.2.4 |

Exact resolved dependency set: `risk-model/requirements-lock.txt`.

### Assessed host (guest environment)

| Component | Version |
|---|---|
| OS | Rocky Linux 9.3 (Blue Onyx) |
| Kernel | 5.14.0-362.13.1.el9_3.x86_64 |
| Base box | `generic/rocky9` v4.3.12 |
| openscap-scanner | 1.3.14-1.el9_8.rocky.0.1 |
| scap-security-guide | 0.1.81-1.el9_8.rocky.1.1 |
| OpenSCAP CLI | 1.3.14 |
| Lynis | 3.1.7-1.el9 |
| ansible-core | 2.14.18-3.el9 |
| ansible.posix collection | **1.5.4** (pinned) |
| Python | 3.9.25 |
| pytest | 8.4.2 |
| pytest-testinfra | 10.2.2 |

### Pinned scanner coordinates

```
data stream: /usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml
profile:     xccdf_org.ssgproject.content_profile_cis_server_l1
```

Both scans used the exact same coordinates. The profile list was enumerated
with `oscap info` rather than guessed; that output is preserved at
`before/oscap-info.txt`.

**Note:** the bare `cis` profile ID in this data stream is **Level 2 Server**,
not Level 1. The brief warns against guessing a profile, and this is why.

---

## Reproduction procedure

Every step below is required. Under the technical assessment contract, any
manual preparation that is missing from the runbook counts as a reproduction
failure. Nothing in this procedure should therefore be completed manually.

### 1. Build the host

```powershell
cd lab
$env:NETFORGE_MARKER = "UBI-A8-0725D08E95BE"
vagrant up rocky
```

The Vagrantfile in `lab/` is the working copy. It differs from the supplied
source in two documented ways - see `decision-log.md` DL-002 and DL-003. The
original is preserved at `raw-evidence/evidence/lab-source/Vagrantfile`.

**The marker environment variable is required.** `baseline.sh` falls back to a
placeholder if it is unset, and Vagrant shell provisioners do not inherit the
host environment.

### 2. Confirm the marker reached the guest

```bash
vagrant ssh rocky
curl -s http://127.0.0.1:8080/
```

Must return `synthetic-service-marker=UBI-A8-0725D08E95BE`. If it returns
`UBI-A8-STAFF-MUST-REPLACE`, destroy and rebuild with the variable set.

### 3. Apply the required SELinux context

```bash
sudo semanage fcontext -a -t httpd_sys_content_t '/srv/netforge-service(/.*)?'
sudo restorecon -Rv /srv/netforge-service
curl -s http://127.0.0.1:8080/
```

`baseline.sh` creates the web root outside any standard location and does not
set an SELinux file context. On Rocky 9 with SELinux enforcing, nginx is denied
and returns HTTP 403, so the declared web service cannot pass its acceptance
check at baseline. This is environment preparation, not remediation - see
`decision-log.md` DL-004.

### 4. Provision the required tooling

```bash
bash /project/provision.sh
```

Installs openscap-scanner, scap-security-guide, EPEL, lynis, ansible-core,
python3-pip, pytest, pytest-testinfra, and `ansible.posix:1.5.4`. Also appends
`ANSIBLE_CONFIG` to `~/.bashrc`.

**`ANSIBLE_CONFIG` is required.** `/project` is a VirtualBox synced folder and
is world-writable, so Ansible refuses to read `ansible.cfg` from it without an
explicit path:

```bash
export ANSIBLE_CONFIG=/project/ansible.cfg
```

`provision.sh` is idempotent and safe to re-run.

### 5. Snapshot the provisioned baseline

```powershell
vagrant snapshot save rocky provisioned-baseline
```

### 6. Capture the baseline evidence

```bash
sudo bash /project/lab/capture-baseline.sh /project/before
sudo lynis audit system --no-colors --quiet | tee /project/before/lynis-report.txt >/dev/null
sudo cp /var/log/lynis-report.dat /project/before/
sudo oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_cis_server_l1 \
  --results /project/before/oscap-results.xml \
  --report  /project/before/oscap-report.html \
  /usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml \
  > /project/before/oscap-stdout.txt 2>&1
```

`oscap xccdf eval` exits 2 when rules fail. That is expected at baseline, not an
error.

### 7. Run the unattended lifecycle

```bash
cd /project && bash lifecycle.sh
```

Runs baseline tests, apply, second apply, service tests, rollback, baseline
verification, reapply, and the final acceptance suite. Writes `idempotence.log`
and regenerates `service-results.xml`.

Exit 0 = all stages passed. Exit 2 = a prerequisite is missing and **no stage
was executed**.

### 8. Capture the after-scans

```bash
sudo lynis audit system --no-colors --quiet | tee /project/after/lynis-report.txt >/dev/null
sudo cp /var/log/lynis-report.dat /project/after/
sudo oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_cis_server_l1 \
  --results /project/after/oscap-results.xml \
  --report  /project/after/oscap-report.html \
  /usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml \
  > /project/after/oscap-stdout.txt 2>&1
```

Identical data stream, profile, and command. `after/delta-reconciliation.txt`
records the rule-by-rule comparison.

### 9. Run the risk model

On the workstation:

```powershell
.venv\Scripts\Activate.ps1
pip install -r risk-model\requirements.txt
python -m pytest risk-model\tests -q
python risk-model\run_model.py --input risk-model\input\model-input.json --output-dir risk-model\output
```

Expect 183 tests passing, and R-002 / R-006 / R-008 selected at USD 73,000.

Runs on the guest too:

```bash
cd /project/risk-model && python3 run_model.py --input input/model-input.json --output-dir output
```

---

## Individual command reference

```bash
# apply one control at a time
cd /project && ansible-playbook site.yml --tags ssh
cd /project && ansible-playbook site.yml --tags web
cd /project && ansible-playbook site.yml --tags coredump
cd /project && ansible-playbook site.yml --tags sysctl
cd /project && ansible-playbook site.yml --tags banner
cd /project && ansible-playbook site.yml --tags umask
cd /project && ansible-playbook site.yml --tags firewall

# full apply, then prove idempotence
cd /project && ansible-playbook site.yml
cd /project && ansible-playbook site.yml          # must report changed=0

# service contract
sudo /usr/local/sbin/netforge-service-contract; echo "exit: $?"

# host acceptance suite
cd /project && python3 -m pytest molecule-or-testinfra/ -q \
  --junitxml=/project/service-results.xml

# rollback, then verify against baseline
cd /project && ansible-playbook rollback.yml
sudo sshd -T > /tmp/now.txt
diff /project/before/sshd-effective.txt /tmp/now.txt && echo "MATCHES BASELINE"
```

---

## Package structure

```
hardening-role/            eleven CIS L1 controls, idempotent
rollback/                  restores the declared baseline
molecule-or-testinfra/     57 host acceptance tests
before/                    24 baseline artefacts
after/                     after-scans and delta reconciliation
service-results.xml        junit output, 57 tests
idempotence.log            unattended lifecycle transcript
risk-model/                simulation, selector, validator, 183 tests
risk-register.csv          twelve risks against the supplied template
investment-memo.pdf        the funding decision and its defence
video-url.txt              recorded defense
manifest.sha256            hashes of every submitted file
evidence-index.csv         claim to artefact to locator
integrity-attestation.md   signed
assessment-manifest.json   frozen commit, versions, output hashes
continuity-record.md       Stage 7 component reuse and handoff

site.yml / rollback.yml    playbook entry points
provision.sh               tooling install, required before lifecycle.sh
lifecycle.sh               the unattended sequence
ansible.cfg / inventory.ini
decision-log.md            DL-001 to DL-005
lab/                       working Vagrantfile, service contract, remediations.yml
raw-evidence/              the assigned archive, unmodified
```

---

## Findings affecting reproduction

These findings are recorded because they affect reproduction, rather than as
complaints.

**The evidence marker does not reach the guest as supplied.** `baseline.sh`
reads `NETFORGE_MARKER` with a placeholder fallback; the supplied Vagrantfile
provisioner does not pass it through. DL-002.

**The declared web service cannot serve at baseline on Rocky 9.** `baseline.sh`
creates content outside any standard web root without setting an SELinux
context. nginx is denied and returns HTTP 403. The script installs
`policycoreutils-python-utils`, which provides `semanage`, suggesting the
relabel was anticipated and omitted. DL-004.

**Two baseline artefacts cannot be hash-compared.** `sysctl.txt` contains
`kernel.random.uuid`, which changes on every read, plus drifting kernel
counters. `listeners.txt` embeds process IDs that change on every reboot -
including the snapshot restore in the lifecycle. Both proven by capturing each
twice on an unmodified host. `before/declared-config.json` records the
comparison set actually used and the exclusions with reasons.

**The host-only private network was disabled.** VirtualBox reported
`VERR_INTNET_FLT_IF_NOT_FOUND`; Hyper-V was confirmed absent. Nothing assessed
requires it - every check runs inside the guest on loopback. DL-003.

---

## After-scan dispositions

Two rules still report `fail` after remediation, both deliberately.

**`package_nginx_removed`** - false positive. The rule's own rationale is
conditional on the web server not being needed; `service-contract.yml` requires
nginx on 8080 and lists disabling it as a forbidden regression. No
parameterisation satisfies both. Evidence:
`before/false-positive-analysis.txt`.

**`sshd_disable_root_login`** - scanner blind spot. `sshd -T` reports
`permitrootlogin no`; the host is compliant. The rule checks for the setting in
`00-complianceascode-hardening.conf` specifically and cannot see the drop-in the
assigned baseline created. Recorded in `after/delta-reconciliation.txt`.

**Automated scan output is evidence of configuration state at a point in time.
No CIS certification is claimed from it.**

---

## Risk-model reproducibility

Deterministic results depend on four factors:

1. **NumPy pinned to 2.1.3.** The `PCG64` stream is version-sensitive; a
   different NumPy silently changes every figure.
2. **Seed derived from the evidence marker** - the first unsigned 64 bits of
   `SHA-256(evidence_marker + ":GRC-A4")` big-endian, giving
   `512818773672660033`.
3. **Canonical row ordering.** Rows are sorted by `risk_id` before any draw, so
   results do not depend on input file ordering.
4. **Exactly 50,000 draws per risk**, as the contract specifies.

183 unit tests cover validation, seed derivation, draw order, arithmetic,
percentile method, dependency handling, budget boundaries, tie-breaking, and
order-invariance. All eight published fixtures reproduce exactly.
