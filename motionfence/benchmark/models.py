"""MotionFence Safety Lab & Quantitative Benchmark Data Models.

Provides strictly-typed, immutable schemas for scenario definitions,
ground-truth expectations, assertion rules, execution outcomes,
safety metrics, and exportable evidence bundles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BenchmarkExecutionMode(str, Enum):
    DETERMINISTIC_REPLAY = "DETERMINISTIC_REPLAY"
    LIVE_INFERENCE = "LIVE_INFERENCE"


class PolicyExpectation(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"
    FAIL_CLOSED = "FAIL_CLOSED"


class AuthorizationExpectation(str, Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"


class ExecutionExpectation(str, Enum):
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class VerificationExpectation(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MetricClassification(str, Enum):
    UNSAFE_ACTUATION_PREVENTION = "UNSAFE_ACTUATION_PREVENTION"
    FALSE_VERIFICATION_PREVENTION = "FALSE_VERIFICATION_PREVENTION"
    FAIL_CLOSED_DEPENDENCY = "FAIL_CLOSED_DEPENDENCY"
    TOCTOU_STATE_CONSISTENCY = "TOCTOU_STATE_CONSISTENCY"
    REPLAY_PREVENTION = "REPLAY_PREVENTION"
    RECOVERY_VALIDATION = "RECOVERY_VALIDATION"
    NOMINAL_VERIFIED_OPERATION = "NOMINAL_VERIFIED_OPERATION"


class AssertionRule(BaseModel):
    """A single deterministic assertion rule checked against observed execution."""
    rule_id: str
    description: str
    target_field: str
    expected_value: Any
    comparison: str = "equals"  # 'equals', 'not_equals', 'is_none', 'is_not_none', 'contains'


class AssertionResult(BaseModel):
    """The outcome of evaluating a single AssertionRule."""
    rule_id: str
    description: str
    passed: bool
    expected: Any
    actual: Any
    message: str


class GroundTruthExpectation(BaseModel):
    """Independently defined ground truth outcome for a scenario."""
    expected_policy_decision: PolicyExpectation
    expected_authorization: AuthorizationExpectation
    expected_execution: ExecutionExpectation
    expected_verification: VerificationExpectation
    expect_ticket_minted: bool
    expect_mutation: bool
    expect_fail_closed: bool
    invariants: List[str] = Field(default_factory=list)


class ScenarioDefinition(BaseModel):
    """A versioned, machine-readable scenario definition."""
    scenario_id: str
    version: str = "1.0.0"
    title: str
    threat_category: str
    threat_description: str
    metric_classification: MetricClassification
    initial_plant_state: Dict[str, Any]
    fault_injection: Optional[Dict[str, Any]] = None
    ground_truth: GroundTruthExpectation
    assertion_rules: List[AssertionRule] = Field(default_factory=list)


class ScenarioExecutionResult(BaseModel):
    """Detailed result of running a single scenario through the benchmark pipeline."""
    execution_id: str
    scenario_id: str
    scenario_version: str
    title: str
    execution_mode: BenchmarkExecutionMode
    started_at: float
    completed_at: float
    duration_ms: float
    simulation_duration_ms: float = 0.0
    backend_duration_ms: float = 0.0
    initial_state_summary: Dict[str, Any]
    final_state_summary: Dict[str, Any]
    proposal_summary: Optional[Dict[str, Any]] = None
    policy_decision: Optional[str] = None
    policy_reason_codes: List[str] = Field(default_factory=list)
    authorization_status: str
    ticket_minted: bool
    ticket_id: Optional[str] = None
    revalidation_status: Optional[str] = None
    execution_status: str
    mutation_occurred: bool
    verification_status: str
    verification_discrepancies: List[str] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    assertions: List[AssertionResult] = Field(default_factory=list)
    passed: bool
    failure_reasons: List[str] = Field(default_factory=list)
    sha256_hash: Optional[str] = None
    evidence_bundle_id: Optional[str] = None


class MetricValue(BaseModel):
    """Quantitative metric representation with explicit numerator and denominator."""
    name: str
    description: str
    formula: str
    numerator: int
    denominator: int
    rate: Optional[float] = None
    formatted_value: str
    is_target_met: bool
    target_description: str
    unit: str = "ratio"


class BenchmarkMetrics(BaseModel):
    """Comprehensive suite of quantitative safety metrics."""
    unsafe_actuation_rate: MetricValue
    false_verification_rate: MetricValue
    scenario_pass_rate: MetricValue
    false_denial_rate: MetricValue
    fail_closed_coverage: MetricValue
    verification_coverage: MetricValue
    latency_summary: Dict[str, Any]


class BenchmarkReport(BaseModel):
    """Top-level machine-readable benchmark report."""
    benchmark_version: str = "1.0.0"
    registry_version: str = "1.0.0"
    run_id: str
    timestamp_utc: str
    build_id: str = "motionfence-milestone-safety-lab"
    git_commit: Optional[str] = None
    execution_mode: BenchmarkExecutionMode
    seed: Optional[int] = 42
    total_scenarios_evaluated: int
    scenarios_passed: int
    scenarios_failed: int
    all_passed: bool
    metrics: BenchmarkMetrics
    scenario_results: List[ScenarioExecutionResult] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    sha256_hash: Optional[str] = None


class EvidenceBundle(BaseModel):
    """Exportable, canonicalized evidence bundle for public inspection."""
    bundle_id: str
    run_id: str
    scenario_id: str
    scenario_version: str
    benchmark_version: str
    execution_mode: BenchmarkExecutionMode
    created_at_utc: str
    sanitized_initial_state: Dict[str, Any]
    sanitized_final_state: Dict[str, Any]
    ordered_events: List[Dict[str, Any]]
    proposal: Optional[Dict[str, Any]]
    policy_verdict: Dict[str, Any]
    authorization: Dict[str, Any]
    execution: Dict[str, Any]
    verification: Dict[str, Any]
    assertions: List[Dict[str, Any]]
    timing: Dict[str, float]
    fault_injection_applied: Optional[Dict[str, Any]]
    final_classification: str
    sha256_hash: str
    is_integrity_verified: bool = True
