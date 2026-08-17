# Quantitative Risk Model Contract

Use Python 3.11, NumPy 2.1.x, `numpy.random.Generator(PCG64(seed))`, and exactly
50,000 simulation draws. Derive `seed` from the first unsigned 64 bits of
`SHA-256(evidence_marker + ":GRC-A4")` in big-endian order.

For each risk row and draw:

1. Sample annual event frequency from `triangular(freq_min, freq_mode, freq_max)`.
2. Sample loss magnitude from `triangular(loss_min, loss_mode, loss_max)`.
3. Sample control effectiveness from `uniform(control_min, control_max)`.
4. Compute `inherent = frequency * loss_magnitude * dependency_multiplier`.
5. Compute `residual = inherent * (1 - control_effectiveness)`.

Aggregate and emit mean, p50, and p90 inherent/residual annual loss. Percentiles
use NumPy's default linear method. Round only final currency outputs to two
decimal places using round-half-even. Reject inverted ranges, values outside
`0 <= control <= 1`, nonpositive dependency multipliers, duplicate risk IDs,
or missing asset IDs.

Treatment selection must choose exactly three options whose total cost does not
exceed the supplied budget and whose dependencies are satisfied. Optimize the
sum of mean annual residual-loss reduction. If two portfolios differ by less
than one cent, choose the lexicographically smaller ordered treatment-ID list.

Submit unit tests for validation, deterministic seeding, arithmetic, dependency
handling, budget boundaries, and tie-breaking. Staff provide a hidden asset,
budget, and treatment fixture using this exact interface.
