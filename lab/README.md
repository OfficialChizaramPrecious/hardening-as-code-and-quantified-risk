# GRC-A4 Debian/Rocky Hardening Lab Source

This source builds two isolated baseline hosts with equivalent synthetic
services and deliberately documented control defects. It does not contain a
pre-completed hardening role. Candidates receive the baseline snapshots,
service contract, scan export, and risk-model inputs, then implement the
required Ansible role themselves.

Build with `vagrant up debian rocky`. Capture baseline snapshots only after the
candidate-specific marker and defect profile have been injected. Preserve the
base-box version and SHA-256 in the submitted build manifest.
