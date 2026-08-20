# Continuity Record

## Stage 8 - Hardening as Code and Quantified Risk

Intern UBI-2026-0099, track GRC, private assignment set D5
Evidence marker: UBI-A8-0725D08E95BE

This record is required by the Advanced Portfolio Continuity Contract.

---

## 1. Previous stage and component reused

**Stage 7 - Automate an ISO 27001 Evidence Audit**
Repository: `northstar-health-iso27001-evidence-audit`
Frozen commit: **`34a34fa`**
Evidence marker: **`UBI-A7-0587AC868B8B`**

### What I reused

**The evidence-index schema.** Twelve columns, unchanged since Stage 6, which I carried forward without modifying them:

```text
claim_id, report_section, claim, artifact_path, exact_locator,
collection_time_utc, sha256, proves, does_not_prove, confidence,
alternative_considered, disposition
```

My Stage 8 `evidence-index.csv` uses the same twelve columns from the supplied template. Every claim records what the artefact proves, what it does not prove, my confidence level, an alternative I considered, and what I decided about that alternative.

I also reused the assessment-manifest structure from the same common template.

### What I reused as method rather than as code

Let me state this plainly

Stage 7's engine assigned qualitative verdicts to audit evidence. Stage 8's model calculates quantitative loss distributions from risk parameters. The two domains are different, so I did not carry the Python code across. What I carried across was the design discipline, and I can point to a specific Stage 7 component and a specific Stage 8 test for each one.

**Marker-seeded determinism.** In Stage 7, `sampler.py` derived its sample selection from the evidence marker, so the same samples came out on every run. In Stage 8, `simulate.py` derives its PCG64 seed from `SHA-256(evidence_marker + ":GRC-A4")`, so the same draws come out on every run and on any host.

**Generic rule engines driven by external data.** In Stage 7, `verdict_engine.py` loaded `severity-rules.yaml` and walked it in file order, so no verdict logic directly named a control identifier. In Stage 8, `selector.py` and `validate.py` express the rules using field names and value relationships. No implementation file contains a finding, risk, asset, or treatment identifier.

**Guard tests that protect the properties grading depends on.** Stage 7 had an allowed-verdict-set check and a rule-order-matches-precedence check. For Stage 8 I wrote `test_validator_source_contains_no_case_identifiers`, `test_selector_source_contains_no_case_identifiers`, and `test_simulation_source_contains_no_case_identifiers`. Each one reads its own module's source and fails if a case literal appears. I also added `test_results_are_invariant_to_input_row_ordering`, because the technical contract says hidden fixtures use different ordering.

**Absent evidence stays absent.** In Stage 7, my severity rules made a missing sample neither automatically conforming nor automatically a nonconformity. It still had to go through the rules. I applied the same principle twice in Stage 8. The selector returns an `infeasible` status instead of raising an error or quietly returning fewer than three treatments. The two scanner rules that still fail after remediation also have documented dispositions in `after/delta-reconciliation.txt` instead of simply being dropped from the count.

**Encoding discipline.** In Stage 7 I hit a `UnicodeEncodeError` when Python wrote to a redirected stream on Windows. I fixed it with `sys.stdout.reconfigure(encoding="utf-8")`. I put the same call at the top of `risk-model/run_model.py` before it could cause the same problem again.

---

## 2. Interface consumed and extension

**What I consumed from Stage 7:** the evidence-index column contract, unchanged.

**Backward-compatible extension to the schema:** none. I added no columns and removed none. My `report_section` values are different because the sections themselves are different. I use Setup, Baseline, Baseline integrity, Rollback, Delta, Idempotence, Service safety, Risk analysis, Decision, and Remediation. The column set and its meaning are still the same.

**Where I did extend it is in practice rather than schema.** In Stage 7 I populated the evidence index by hand, and it shipped with `PENDING-HASH` placeholders that I only noticed during review. For Stage 8 I wrote `build-evidence-index.py`, which calculates every SHA-256 from the artefact on disk and **refuses to write anything if an artefact is missing**. It is the same interface, but now the process is reproducible and that specific failure is closed.

---

## 3. Evidence that raw-to-result provenance remains intact

**I preserved the raw inputs unmodified.** The assigned archive `grc-stage-8-shared-b1.tar.gz` and its extracted contents are kept read-only in `raw-evidence/`. I verified its SHA-256 against the dashboard value **before** extraction:

```text
9be5e36adc4d906f0fdac3b2a893da3bfb4b994e7423c0ee3cc320ca265e283b
```

**I kept derived outputs separate from raw ones.** `before/` and `after/` contain the raw scanner exports in their native format. `risk-model/output/` contains the derived results. I marked `before/**`, `after/**`, and `raw-evidence/**` as binary in `.gitattributes` so that line-ending normalisation cannot change the bytes the scanners actually produced.

**Every scored claim carries a locator.** My `evidence-index.csv` contains 21 claims. Each one has an artefact path, an exact locator, a collection time, and a computed SHA-256. No claim in the investment memorandum or the register is missing a corresponding index entry.

**Where I modified supplied source, I documented it rather than doing it silently.** I made two changes to the supplied Vagrantfile. They are recorded in `decision-log.md` as DL-002 and DL-003, and the original is preserved unmodified at `raw-evidence/evidence/lab-source/Vagrantfile`. I also made a third change to host state, the SELinux relabel, which is recorded as DL-004 and classified as environment preparation performed before baseline capture, not as remediation.

**I verified my design decisions before implementing them.** Every remediation in `lab/remediations.yml` has a `verify_precheck` command that I ran against the live host before writing the task. Four of my entries turned out to be wrong, and the `design_corrections` section records what each one was and why I changed it.

---

## 4. Migration record

The contract requires a migration record for every incompatible change. There are two.

### The Stage 7 engine could not be carried forward as code

**What I built in Stage 7:** `verdict_engine.py`, `sampler.py`, `collector.py`, and `run_audit.py`. This was a pipeline that ingested audit evidence, sampled populations deterministically, validated evidence quality, and assigned one of four qualitative verdicts using first-match precedence rules.

**What Stage 8 requires:** a Monte Carlo simulation that produces continuous loss distributions, a portfolio optimiser under a budget constraint with dependency handling, and an idempotent configuration-management role. The published risk-model contract specifies the distributions, draw count, seed derivation, percentile method, and tie-break rule.

**Why they are incompatible:** my Stage 7 verdict engine maps facts to one member of a finite verdict set. The Stage 8 model maps parameter ranges to a continuous distribution and then optimises combinations of treatments. There is no interface adaptation that makes the first one perform the second. The operations are different in kind, not just different configurations.

**What I migrated instead:** the design properties from section 1, each re-implemented for the new domain. I am stating this explicitly rather than calling it code reuse, because the continuity contract lists *"claiming reuse when only filenames or report language were copied"* as a failure condition. The evidence-index schema is genuinely reused. The engine is not, and I would rather say that clearly.

**What did not get lost in the migration:** determinism, generic rules over external data, guard tests protecting grading-relevant properties, absent evidence staying absent, and full artefact-to-claim traceability. I can point to a named test or artefact for each one.

### The supplied baseline manifest could not verify rollback

**What the lab supplies:** `capture-baseline.sh` hashes its own output into `before/manifest.sha256`, which implies that the manifest is supposed to be the rollback comparison target.

**Why I could not use it as issued:** two of the captured artefacts cannot produce the same hash twice on an unmodified host. `sysctl.txt` contains `kernel.random.uuid`, which returns a new value on every read, along with kernel counters that also change. `listeners.txt` contains process IDs and file descriptors that change on every reboot, including the snapshot restore that happens during my own lifecycle test. I proved both by capturing each artefact twice, seconds apart, without changing anything in between. The evidence is in `before/sysctl-volatility-evidence.txt` and `before/listeners-volatility-evidence.txt`.

**How I migrated it:** `before/declared-config.json` declares an explicit comparison set. It contains three artefacts that I confirmed were hash-stable through testing, and two that I excluded with a stated reason and an alternative comparison method for each. My `lifecycle.sh` verifies rollback against that declared set. I retained the supplied manifest unmodified in `before/`.

---

## 5. Handoff to Stage 9

The GRC track carries the typed control and evidence model through vendor assurance, audit, technical treatment, and breach governance. Stage 8 is technical treatment. Stage 8 is technical treatment. Stage 9 is Build a Breach Governance Engine — Recover, decide, and stand behind the result, and this is what I am handing forward.

### Residual risks

Modelled mean annual residual loss across the estate falls from **USD 3,229,259** to approximately **USD 1,349,398.60** after my three funded treatments.

The remaining exposure is concentrated in the deferred findings on crown-jewel and high-criticality assets. Full detail is in `risk-register.csv`.

**R-009 (dev-git-01) needs specific attention in Stage 9.** It carries inherent score 9 and stays at 9 residual. That makes it the highest residual position in my register and the only deferred risk requiring CISO acceptance. An inactive deploy key, which the export validated as still authenticating, reaches the production release path.

### Implemented and declined treatments

**Implemented (USD 73,000 of USD 85,000):**

| Risk  | Treatment                                                            |   Cost |
| ----- | -------------------------------------------------------------------- | -----: |
| R-006 | Restrict backup management interface to management VLAN, require MFA | 22,000 |
| R-002 | Enforce server-side object authorization on the payroll API          | 45,000 |
| R-008 | Reduce privileged session lifetime on the identity provider          |  6,000 |

**Declined or deferred:** nine risks. Each has an owner, an acceptance authority, a target date of 2027-02-28, and a documented review trigger in `risk-register.csv`.

Two of those deferrals should carry forward into breach governance with particular care because their severity labels and their modelled exposure are quite different. **VF-001 and VF-007 are both CVSS 9.8 Critical and I deferred both**, based on the fact that each sits on an asset with zero records and zero revenue dependency. If a breach ever occurs on either one, my reasoning is the record of why I did not treat them, and that reasoning should be examined rather than simply assumed to have been correct.

### Evidence deltas

|                       | Before | After |
| --------------------- | -----: | ----: |
| OpenSCAP fail         |    101 |    86 |
| OpenSCAP pass         |    159 |   174 |
| OpenSCAP error        |      0 |     0 |
| Lynis hardening index |     66 |    70 |

**15 rules moved from fail to pass, with zero regressions.** The rule-by-rule reconciliation is in `after/delta-reconciliation.txt`.

### Ownership

I named nine accountable roles across the register: Application Security Lead, Backup and Recovery Lead, Database Operations Lead, Endpoint Operations Lead, IT Operations Lead, Identity and Access Lead, Infrastructure Lead, Network Operations Lead, and Platform Engineering Lead.

Acceptance authority is the CISO where the inherent score is 9 or above, and the Head of IT Operations below that.

I used role titles only and named no individual.

### Accepted limitations

I am carrying these forward so that Stage 9 does not treat my figures as measured facts.

**My loss estimates are judgment.** Annual revenue dependency at 1, 5 and 20 percent with a bounded records uplift, anchored to published breach averages. They are not observed costs for this organisation, and actual incident cost data should replace them when it becomes available.

**Control effectiveness is elicited, not measured.** My ranges reflect an assessment of whether each existing control addresses the specific weakness found. Control testing evidence would replace that judgment with measurement.

**Frequency tiers are ordinal, not actuarial.** They rank findings by the quality of their exploit evidence rather than deriving rates from incident history. That is why the sensitivity result matters more than my absolute figures.

**Dependency multipliers are structural estimates.** They express that compromise of the identity provider, DNS, and backup coordinator can propagate beyond the asset. I reasoned the magnitudes; they are not derived from a formal dependency map.

**The 1-5 scores in the register are a presentation banding**, derived from the modelled frequency and loss modes using stated thresholds. They are not a second independent assessment, and the risk is not scored twice.

**Scan output is evidence of configuration state at a point in time.** I am not claiming CIS certification from it.

**My sensitivity test addresses uniform error only.** The selection is stable at ±30 percent when applied to every finding at the same time. It does not address one asset's exposure being badly misjudged relative to another's. That remains the strongest available challenge to my funding decision, and I would rather Stage 9 inherit that limitation clearly stated than discover it later.

### Component handed forward

`risk-model/` is the reusable component: a deterministic, marker-seeded, identifier-free simulation and selection engine with 183 tests. Its input schema is `risk-model/schemas/model-input.schema.json`.

A Stage 9 scenario supplying assets, risks, and treatments in that schema will run without any source modification. That is the property the hidden transfer fixture is designed to test, and it is protected by `test_selection_is_stable_under_input_reordering` and `test_results_are_invariant_to_input_row_ordering`.
