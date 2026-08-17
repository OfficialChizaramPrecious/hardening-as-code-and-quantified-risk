"""Shared pytest configuration for the risk-model suite.

Puts the risk-model package directory on sys.path so tests import the modules
under test directly, without requiring an installed package. This keeps the
documented clean-build command a plain `pytest` invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RISK_MODEL_DIR = Path(__file__).resolve().parent.parent
if str(RISK_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(RISK_MODEL_DIR))


@pytest.fixture
def valid_row() -> dict:
    """One risk row that violates no rule in the contract.

    Tests derive invalid rows from this by changing a single field, so each
    negative test isolates exactly one rule.
    """
    return {
        "risk_id": "RISK-SAMPLE",
        "asset_id": "ASSET-SAMPLE",
        "freq_min": 0.1,
        "freq_mode": 0.5,
        "freq_max": 2.0,
        "loss_min": 1000.0,
        "loss_mode": 5000.0,
        "loss_max": 20000.0,
        "control_min": 0.2,
        "control_max": 0.6,
        "dependency_multiplier": 1.0,
    }


@pytest.fixture
def asset_table() -> list[dict]:
    """A minimal asset table matching valid_row's asset_id."""
    return [{"asset_id": "ASSET-SAMPLE"}, {"asset_id": "ASSET-OTHER"}]
