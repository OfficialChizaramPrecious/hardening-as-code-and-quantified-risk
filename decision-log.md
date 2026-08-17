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

**Verification (performed):** after `vagrant up rocky`,
`curl -s http://127.0.0.1:8080/` returned
`synthetic-service-marker=UBI-A8-0725D08E95BE`.

## DL-003 - Host-only private network disabled

**Decision:** commented out the private network interface in the working
Vagrantfile. The guest runs with NAT only.

**Change:**

    - node.vm.network "private_network", ip: settings[:ip]
    + # node.vm.network "private_network", ip: settings[:ip]  # DL-003

**Why:** VirtualBox 7.2.4 on the host workstation failed to start the VM with
`VERR_INTNET_FLT_IF_NOT_FOUND`. The host-only adapter existed (VirtualBox
Host-Only Ethernet Adapter #2, 192.168.84.1, status Up) but the NDIS filter
driver was not bound to it. Hyper-V was confirmed absent
(`HyperVisorPresent: False`), so this is a driver-binding fault rather than a
hypervisor conflict.

**Why this does not affect assessed work:** the private address serves
host-to-guest convenience only. Every assessed operation runs inside the guest:
the `web` check in `service-contract.yml` targets `http://127.0.0.1:8080/`,
Ansible runs against localhost, testinfra runs locally, and both scanners run on
the host under test. Guest access is via `vagrant ssh` over NAT on port 2222.
No requirement in brief.md or `service-contract.yml` references the private
address.

**Alternative considered:** repairing the VirtualBox installation to rebind the
network filter driver. Weakened because it carries no benefit to the assessed
work, is not guaranteed to succeed if driver installation is being blocked at
the operating-system level, and would consume schedule time on the build day.

**Review trigger:** any later requirement for host-to-guest network access.

## DL-004 - SELinux relabel required before the declared service would serve

**Observation:** `baseline.sh` creates `/srv/netforge-service` outside any
standard web root and does not set an SELinux file context. On Rocky Linux 9
with SELinux enforcing, the directory and file inherited `var_t`. nginx runs in
the `httpd_t` domain and was denied `getattr`, returning HTTP 403. The `web`
acceptance check in `service-contract.yml` could not pass at baseline.

**Evidence:** AVC denial recorded at 2026-08-17T22:57:45Z -
`scontext=system_u:system_r:httpd_t:s0`,
`tcontext=unconfined_u:object_r:var_t:s0`, `tclass=file`, path
`/srv/netforge-service/index.html`, `permissive=0`. nginx error log records
"is forbidden (13: Permission denied)".

**Action:**

    sudo semanage fcontext -a -t httpd_sys_content_t '/srv/netforge-service(/.*)?'
    sudo restorecon -Rv /srv/netforge-service

**Classification:** environment preparation, not remediation. The declared
service must be available before a baseline is meaningful, since the project is
measured on zero service regressions against that baseline. Applied before the
clean snapshot and before any `before/` capture, and recorded in the README
reproduction order so that a clean rebuild reaches the same state.

**Supporting observation:** `baseline.sh` installs
`policycoreutils-python-utils`, which provides `semanage`. This indicates the
relabel was anticipated by the lab design but omitted from the script.

**Not affected:** the `0666` mode on `index.html` remains in place as a planted
baseline defect for remediation under HR-003. SELinux context and Unix
permissions are independent controls; relabelling did not alter the mode.

**Verification (performed):** after relabel,
`curl -s http://127.0.0.1:8080/` returned
`synthetic-service-marker=UBI-A8-0725D08E95BE`, and `ls -laZ` confirmed
`httpd_sys_content_t` with mode `-rw-rw-rw-` retained.

## DL-005 - OpenSSH upgraded during provisioning

**Observation:** `baseline.sh` runs a package transaction that upgraded OpenSSH
from 8.7p1-34.el9 to 9.9p1-9.el9_8.rocky.0.1, writing
`/etc/ssh/sshd_config.rpmnew` and `/etc/sysconfig/sshd.rpmnew`.

**Why recorded:** the baseline host runs a different SSH version from the base
box image, and the packaged default configuration was preserved rather than
replaced. Both facts are pinned in `before/tool-versions.txt` so the
before/after comparison is like for like, and so a reviewer can account for
`.rpmnew` files present on the host at baseline.
