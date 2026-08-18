# Stage 8 — Hardening Half Runbook

Everything for the Ansible/scanner half of the project. Written to be followed
without further help.

**Deadline:** Tuesday 25 August, 18:10 WAT. No revision.
**Evidence marker:** `UBI-A8-0725D08E95BE`
**Host:** Rocky Linux 9, CIS Level 1 Server profile (your documented choice)
**Budget:** USD 85,000 (risk model half)

---

## Day plan

| Day | Work |
|---|---|
| Mon 17 Aug | VM built, tooling installed, versions pinned, clean snapshot taken |
| Tue 18 Aug | Baseline captured into `before/`; eight-plus remediations designed on paper |
| Wed 19 Aug | Hardening role implemented, applied one control at a time |
| Thu 20 Aug | Rollback role, idempotence proven, `idempotence.log` captured |
| Fri 21 Aug | testinfra suite, `service-results.xml`, after-scans into `after/` |
| Sat 22 Aug | `model-input.json` finished, `risk-register.csv` populated |
| Sun 23 Aug | `investment-memo.pdf`, full unattended lifecycle rehearsal |
| Mon 24 Aug | Record the defense video, packaging artefacts |
| Tue 25 Aug | Final verification, incognito check, submit well before 18:10 |

Two days of slack are deliberate. Use them; do not plan to submit on the 25th.

---

## Send this to staff today

You still need one answer before you can record:

> The FAQ states the recorded defense includes implementing or adjusting one
> staff-selected role control. Please confirm which control is selected for
> intern UBI-2026-0099 (set D5), or confirm that the selection is made live
> rather than in the submitted recording.

---

## Phase 1 — Build the host (Mon)

### 1.1 Fix the marker passthrough FIRST

`baseline.sh` reads `NETFORGE_MARKER`, but the supplied `Vagrantfile` provisioner
passes only `args: [name]`. Vagrant provisioners do **not** inherit your host
shell environment. Unfixed, your host is stamped `UBI-A8-STAFF-MUST-REPLACE`
and every downstream artefact is wrong.

Copy `raw-evidence/evidence/lab-source/` to a working `lab/` directory (keep the
original read-only), then edit the provisioner block:

```ruby
node.vm.provision "shell", path: "baseline.sh", args: [name],
  env: { "NETFORGE_MARKER" => ENV.fetch("NETFORGE_MARKER") }
```

Record this modification in `decision-log.md`: what you changed, why, and that
the supplied source is preserved unmodified in `raw-evidence/`.

### 1.2 Build

```powershell
cd lab
$env:NETFORGE_MARKER = "UBI-A8-0725D08E95BE"
vagrant up rocky
```

### 1.3 Verify the marker landed — do not skip

```bash
vagrant ssh rocky
curl -s http://127.0.0.1:8080/
```

Output must contain `synthetic-service-marker=UBI-A8-0725D08E95BE`.
If it shows `STAFF-MUST-REPLACE`, destroy and rebuild. Everything depends on this.

### 1.4 Install tooling

```bash
sudo dnf install -y openscap-scanner scap-security-guide
sudo dnf install -y epel-release && sudo dnf install -y lynis
sudo dnf install -y ansible-core
pip3 install --user pytest pytest-testinfra
```

### 1.5 Enumerate profiles — this is evidence, not a lookup

```bash
ls /usr/share/xml/scap/ssg/content/
oscap info /usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml | tee ~/oscap-info.txt
```

The brief explicitly warns against guessing `--profile cis` against a wildcard
path. `oscap-info.txt` is your proof you enumerated. Copy the **exact** profile
ID from that output — do not type it from memory.

Expect something of the form:
`xccdf_org.ssgproject.content_profile_cis_server_l1`

### 1.6 Pin everything

```bash
{
  cat /etc/os-release
  rpm -q openscap-scanner scap-security-guide lynis ansible-core
  oscap --version
  lynis show version
  ansible --version
  uname -a
} | tee ~/tool-versions.txt
```

On the host: `vagrant box list` — record box name and version. The lab README
also wants the base-box SHA-256 in your build manifest.

### 1.7 Snapshot before anything changes

```powershell
vagrant snapshot save rocky clean-baseline
```

This is what the Friday lifecycle restores to. Take it now.

---

## Phase 2 — Baseline (Tue morning)

### 2.1 Run the supplied capture script

```bash
sudo bash /vagrant/lab-source/capture-baseline.sh /vagrant/before
```

Then the scans:

```bash
sudo lynis audit system --no-colors | tee /vagrant/before/lynis-report.txt
sudo cp /var/log/lynis-report.dat /vagrant/before/

sudo oscap xccdf eval \
  --profile <EXACT_PROFILE_ID> \
  --results /vagrant/before/oscap-results.xml \
  --report /vagrant/before/oscap-report.html \
  /usr/share/xml/scap/ssg/content/ssg-rl9-ds.xml \
  | tee /vagrant/before/oscap-stdout.txt
```

`oscap xccdf eval` exits non-zero when rules fail. That is normal, not an error.

### 2.2 THE SYSCTL TRAP — read this before designing rollback

`capture-baseline.sh` hashes everything it captures, including `sysctl -a` output.
`kernel.random.uuid` returns a **different value on every single read**.
`kernel.random.boot_id` changes across reboots, and your lifecycle restores a
snapshot, which is a reboot.

**A whole-file hash of `sysctl.txt` can never match twice.** If you build rollback
verification on the supplied manifest as-is, it fails 100% of the time — and a
failed rollback test fails technical completion outright.

Fix: declare an explicit comparison set of stable configuration facts:

- `sshd -T` output (the effective SSH configuration)
- `listeners.txt` (listening sockets)
- `enabled-services.txt`
- `file-permissions.csv`
- **only the specific sysctl keys your role changes**, extracted individually

Write `before/declared-config.json` listing exactly which facts are compared and
which are excluded as volatile, with the reason. That documented exclusion is
strong evidence work, not a workaround. Put it in `decision-log.md` too.

---

## Phase 3 — Design the remediations (Tue afternoon)

Five defects are planted by `baseline.sh`:

| # | Defect | Location |
|---|---|---|
| 1 | `PermitRootLogin yes` | `/etc/ssh/sshd_config.d/90-netforge-baseline.conf` |
| 2 | `PasswordAuthentication yes` | same file |
| 3 | `chmod 0666` on web content | `/srv/netforge-service/index.html` |
| 4 | `* soft core unlimited` | `/etc/security/limits.d/` |
| 5 | `net.ipv4.conf.all.accept_redirects=1` | runtime only (`sysctl -w`) |

You need **at least eight**, so source three-plus from your actual CIS L1 scan.
Safe additions that will not touch the declared services:

- `net.ipv4.conf.all.send_redirects=0`
- `net.ipv4.conf.all.accept_source_route=0`
- `kernel.randomize_va_space=2`
- `/etc/ssh/sshd_config` permissions `0600`
- SSH `MaxAuthTries`, `LoginGraceTime`, `ClientAliveInterval`
- `umask 027` via `/etc/profile.d/`
- Cron file permissions (`/etc/crontab`, `/etc/cron.*` to `0600`/`0700`)
- Password quality requirements via `pam_pwquality`

Note on defect 5: it is applied with `sysctl -w` only, never persisted to
`/etc/sysctl.d/`. It does not survive a reboot. Mention this in your write-up —
a naive before/after across a reboot would show it "fixed" with no work done.
That observation is exactly the evidence-quality thinking being graded.

### 3.1 The service conflict

`service-contract.yml` requires four checks to stay green:

| id | check | passes when |
|---|---|---|
| `web` | `curl --fail -s http://127.0.0.1:8080/` | output contains `synthetic-service-marker=` |
| `audit` | `systemctl is-active auditd` | exit 0 |
| `time` | `systemctl is-active chronyd` | exit 0 |
| `ssh-effective` | `sshd -T` | output contains `port 22` |

**Defect 3 is your parameterization case.** `baseline.sh` chowns
`/srv/netforge-service` to the nginx user and sets `index.html` to `0666`.
World-writable web content is a real defect you must fix. But nginx still needs
to **read** it. `chmod 0600`, `chown root:root`, or a blanket
`find /srv -type f -exec chmod 0640` all break the `web` check.

Correct answer: parameterised owner and mode.

```yaml
# defaults/main.yml
netforge_web_root: /srv/netforge-service
netforge_web_owner: nginx
netforge_web_file_mode: "0644"
```

The control still applies. The service still works. That is what "correctly
parameterized" means, and your acceptance suite must show both.

**Second conflict to avoid:** any firewall remediation with a default-deny policy
closes 8080. `forbidden_regressions` also bans opening a new listening port.
If you add firewalld, the allowed port must be a role variable.

**Do not** move SSH off port 22 — `ssh-effective` requires `port 22` in `sshd -T`.

### 3.2 Finding the false positive

One scanner item is not a real defect on this host. You identify it by checking
host state directly rather than trusting the check's verdict. Typical mechanisms:

- A rule reads `/etc/ssh/sshd_config` directly and cannot see settings applied
  through `sshd_config.d/*.conf` drop-ins — the host is compliant, the check
  is blind to where the setting lives.
- A partitioning rule (separate `/tmp`, `/var`) that a single-partition Vagrant
  box cannot satisfy and that is not a defect in this deployment model.
- A rule whose remediation the declared service contract forbids.

Method: for each candidate, run the underlying check by hand
(`sshd -T | grep <setting>`, `mount | grep tmp`), compare to the rule's intent,
and record: what the scanner claims, what the host actually does, what evidence
weakened the claim.

Document it. **Do not remediate it.** Chasing a perfect scan score loses marks
here, and your acceptance suite must distinguish the false positive from the
service conflict.

### 3.3 Record each remediation before writing any YAML

For all eight-plus, in a structured file (`remediations.yml`):

```yaml
- id: HR-001
  finding: "SSH permits direct root login"
  scanner_ref: "<rule id from oscap-results.xml or Lynis test id>"
  desired_state: "PermitRootLogin no"
  precheck: "sshd -T | grep -i permitrootlogin"
  change: "template 90-netforge-baseline.conf with hardened values"
  service_risk: "none - vagrant user has sudo, key auth unaffected"
  rollback: "restore baseline template"
  acceptance_test: "test_sshd_permit_root_login_disabled"
  expected_scanner_effect: "rule <id> moves fail -> pass"
```

This file is the checkpoint the build sequence asks for, and it feeds
`evidence-index.csv` later.

---

## Phase 4 — The role (Wed)

```
hardening-role/
├── defaults/main.yml      # every tunable, no literals in tasks
├── vars/main.yml
├── tasks/main.yml
├── handlers/main.yml
├── templates/
│   ├── 90-netforge-baseline.conf.j2
│   └── 99-netforge-hardening.conf.j2
└── meta/main.yml

rollback/
├── defaults/main.yml
├── tasks/main.yml
├── handlers/main.yml
└── templates/
    └── 90-netforge-baseline.conf.j2   # the BASELINE values
```

### 4.1 Idempotence rules — this is where projects fail

The FAQ names the cheat explicitly: *"hiding changed output or using
`changed_when: false` without a real invariant does not count."*

- **Use `template` or `copy` for whole config files.** Deterministic and
  idempotent. Avoid `lineinfile` — unanchored regexes re-match their own output
  and report `changed` forever.
- **Never use `command`/`shell` without `creates:` or a real `changed_when:`.**
- Use the `ansible.posix.sysctl` module with `sysctl_file:` and `reload: yes` —
  it is idempotent and it persists, unlike the baseline's `sysctl -w`.
- Use `ansible.builtin.file` for modes and ownership.
- Handlers fire only on change; do not put unconditional restarts in tasks.

### 4.2 Apply one control at a time

The brief requires it: *"Apply changes one at a time, rerun service tests, and
record regressions."*

```bash
ansible-playbook site.yml --tags hr-001
pytest molecule-or-testinfra/ -q          # services still green?
ansible-playbook site.yml --tags hr-002
pytest molecule-or-testinfra/ -q
```

Tag every task block. When one breaks a service you will know exactly which.

### 4.3 Rollback is a restore, not an undo

> *"Reverting the VM snapshot does not prove the submitted rollback automation."*

The rollback role declares the **baseline** as its desired state — the same
template mechanism, baseline values. That makes it idempotent too, and it
restores the declared config and service hashes rather than reversing steps.

Rollback must restore `index.html` to `0666`. That feels wrong; it is correct.
Rollback returns the host to its baseline, defects included.

---

## Phase 5 — Tests and proof (Thu–Fri)

### 5.1 testinfra, not molecule

`service-results.xml` is required as XML, and `pytest --junitxml` produces it
directly. Molecule would need extra plumbing for the same result.

```
molecule-or-testinfra/
├── conftest.py
├── test_service_contract.py    # the four contract checks
├── test_remediations.py        # one test per HR-nnn
├── test_false_positive.py      # asserts it was NOT remediated
└── test_rollback.py            # baseline state restored
```

```bash
pytest molecule-or-testinfra/ -q \
  --junitxml=/vagrant/service-results.xml
```

`test_false_positive.py` matters: it proves you deliberately left a real thing
alone, which distinguishes judgment from an incomplete role.

### 5.2 The unattended lifecycle

The required sequence, from the brief:

```
baseline tests → apply → second apply → service tests
→ rollback → baseline hash verification → reapply → final scan
```

Script it end to end and capture `idempotence.log`:

```bash
ansible-playbook site.yml | tee -a idempotence.log
ansible-playbook site.yml | tee -a idempotence.log   # MUST show changed=0
```

The second run's recap must read `changed=0`. Anything else fails.

### 5.3 After-scans

Same profile, same data stream, same commands, into `after/`. Then reconcile
every difference: rules that moved fail→pass, rules still failing and why, the
false positive still failing by design, and any new finding.

At least eight expected deltas with zero service regressions.

**Never claim CIS certification from scan output.** The brief lists it as a
technical hold. A passing profile scan evidences configuration state; it is not
a certification.

---

## Phase 6 — Packaging

Submission root, exactly these 17:

```
hardening-role/          molecule-or-testinfra/   rollback/
before/                  after/                   service-results.xml
idempotence.log          risk-model/              risk-register.csv
investment-memo.pdf      video-url.txt            manifest.sha256
evidence-index.csv       integrity-attestation.md README.md
assessment-manifest.json continuity-record.md
```

Order matters at the end:

1. All content final
2. `evidence-index.csv` — every scored claim gets a locator, real hashes, no
   `PENDING-HASH` placeholders (this bit you in Stage 7)
3. `assessment-manifest.json` — frozen commit, measured runtime, real output
   hashes, the archive SHA-256 `9be5e36a...265e283b` with
   `verified_before_use: true`
4. `integrity-attestation.md` — signed with a real UTC timestamp, AI assistance
   declared
5. `manifest.sha256` — **last**, covering every file except itself
6. Upload, set Anyone-with-link/Viewer, verify in incognito

`continuity-record.md` needs your Stage 7 commit (`34a34fa`) and the component
reused — the evidence-index discipline and verification-engine pattern carried
into technical treatment.

The FAQ also requires an **executive summary typed into the submission form**.
It is not one of the 17. Draft it in advance.

---

## Traps, collected

1. Vagrantfile does not pass `NETFORGE_MARKER` to the guest
2. `sysctl.txt` cannot hash identically twice — `kernel.random.uuid` changes per read
3. Web file permissions are the service-conflict parameterization case
4. Firewall default-deny would close 8080; SSH must stay on port 22
5. `changed_when: false` without an invariant is named as a non-qualifying cheat
6. Rollback restores the baseline, defects included; snapshot revert proves nothing
7. Do not submit `oscap xccdf generate fix --fix-type ansible` output as your role
8. `manifest.sha256` generates last, after the URL in `video-url.txt` is final

---

## If something goes wrong

Preserve state, do not repair silently. Send UTC time, stage, environment, exact
error, sanitized logs to programme support. Continue only after written
disposition when the issue affects scope, safety, assignment identity, or
evidence integrity.
