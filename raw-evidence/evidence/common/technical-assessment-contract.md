# Advanced Stage Technical Assessment Contract

This contract applies to every project in addition to its track brief.

## Build standard

Submit a version-controlled repository that builds from a clean supported host
using one documented entry command. Pin dependencies, validate configuration,
preserve raw inputs, and emit machine-readable results. A report is evidence of
the build; it is not a substitute for the build.

## Test standard

The repository must contain unattended positive, negative, malformed-input,
and clean-state tests. Published fixtures establish the interface. Staff run a
deterministic hidden fixture with the same schema but different identifiers,
ordering, values, and edge conditions. Hidden tests do not introduce an
undocumented requirement.

## Reproduction standard

Staff execute the documented build and test commands on a clean environment.
Outputs must be deterministic where the brief requires exact hashes or counts.
Every result must retain a locator to its source evidence. Manual preparation
that is absent from the runbook is treated as a reproduction failure.

## Technical gates

- A missing runnable implementation caps the project at 49.
- Failure of the published acceptance suite caps the project at 59.
- Failure of the hidden transfer fixture caps the project at 69.
- Hard-coded variant answers, identifiers, flags, or one-run state cap the
  project at 49 and trigger an integrity review when concealment is indicated.
- Unsafe or out-of-scope execution remains an automatic fail.

The panel may select any published test or raw result for live reproduction.
