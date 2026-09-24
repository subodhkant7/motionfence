"""Comprehensive test suite validating standard corpus Scenarios A through L."""

import pytest

from motionfence.adversarial.corpus import (
    CORPUS_REGISTRY,
    get_scenario,
    list_corpus_scenarios,
)
from motionfence.adversarial.executor import AdversarialScenarioExecutor
from motionfence.adversarial.models import ScenarioOutcome
from motionfence.adversarial.scenarios import scenario_from_json, scenario_to_json


class TestStandardScenarioCorpus:
    """Validate Scenarios A through L from the standard deterministic adversarial corpus."""

    @pytest.fixture
    def executor(self):
        return AdversarialScenarioExecutor()

    def test_corpus_contains_12_standard_scenarios(self):
        scenarios = list_corpus_scenarios()
        assert len(scenarios) == 12
        scenario_ids = [s.scenario_id for s in scenarios]
        assert "SCENARIO_A_HUMAN_TOCTOU" in scenario_ids
        assert "SCENARIO_B_PUMP_ACTIVATION" in scenario_ids
        assert "SCENARIO_C_COOLING_DEGRADATION" in scenario_ids
        assert "SCENARIO_D_SENSOR_STUCK" in scenario_ids
        assert "SCENARIO_E_SENSOR_CONTRADICTION" in scenario_ids
        assert "SCENARIO_F_TARGET_OCCLUSION" in scenario_ids
        assert "SCENARIO_G_ACTUATOR_JAM" in scenario_ids
        assert "SCENARIO_H_ACTUATOR_PARTIAL" in scenario_ids
        assert "SCENARIO_I_KNOWLEDGE_STALE" in scenario_ids
        assert "SCENARIO_J_POLICY_DRIFT" in scenario_ids
        assert "SCENARIO_K_COMPOUND_TWO_FAULTS" in scenario_ids
        assert "SCENARIO_L_COMPOUND_THREE_FAULTS" in scenario_ids

    def test_scenario_a_human_toctou(self, executor):
        sc = get_scenario("SCENARIO_A_HUMAN_TOCTOU")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False
        assert res.execution_success is False

    def test_scenario_b_pump_activation(self, executor):
        sc = get_scenario("SCENARIO_B_PUMP_ACTIVATION")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False

    def test_scenario_c_cooling_degradation(self, executor):
        sc = get_scenario("SCENARIO_C_COOLING_DEGRADATION")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome in (ScenarioOutcome.SAFE_DENY, ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE)
        assert res.unsafe_allow is False

    def test_scenario_d_sensor_stuck(self, executor):
        sc = get_scenario("SCENARIO_D_SENSOR_STUCK")
        assert sc is not None
        res = executor.execute(sc)
        assert res.unsafe_allow is False

    def test_scenario_e_sensor_contradiction(self, executor):
        sc = get_scenario("SCENARIO_E_SENSOR_CONTRADICTION")
        assert sc is not None
        res = executor.execute(sc)
        assert res.unsafe_allow is False

    def test_scenario_f_target_occlusion(self, executor):
        sc = get_scenario("SCENARIO_F_TARGET_OCCLUSION")
        assert sc is not None
        res = executor.execute(sc)
        assert res.unsafe_allow is False

    def test_scenario_g_actuator_jam(self, executor):
        sc = get_scenario("SCENARIO_G_ACTUATOR_JAM")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.VERIFICATION_FAILURE
        assert res.unsafe_allow is False

    def test_scenario_h_actuator_partial(self, executor):
        sc = get_scenario("SCENARIO_H_ACTUATOR_PARTIAL")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.VERIFICATION_FAILURE
        assert res.unsafe_allow is False

    def test_scenario_i_knowledge_stale(self, executor):
        sc = get_scenario("SCENARIO_I_KNOWLEDGE_STALE")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False

    def test_scenario_j_policy_drift(self, executor):
        sc = get_scenario("SCENARIO_J_POLICY_DRIFT")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False

    def test_scenario_k_compound_two_faults(self, executor):
        sc = get_scenario("SCENARIO_K_COMPOUND_TWO_FAULTS")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False

    def test_scenario_l_compound_three_faults(self, executor):
        sc = get_scenario("SCENARIO_L_COMPOUND_THREE_FAULTS")
        assert sc is not None
        res = executor.execute(sc)
        assert res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res.unsafe_allow is False

    def test_all_corpus_scenarios_have_zero_unsafe_allows(self, executor):
        """Global invariant: Unsafe ALLOW count must be strictly 0 across all 12 corpus scenarios."""
        unsafe_count = 0
        for sc in list_corpus_scenarios():
            res = executor.execute(sc)
            if res.unsafe_allow:
                unsafe_count += 1
        assert unsafe_count == 0

    def test_scenario_json_serialization_roundtrip(self):
        for sc in list_corpus_scenarios():
            serialized = scenario_to_json(sc)
            deserialized = scenario_from_json(serialized)
            assert deserialized.scenario_id == sc.scenario_id
            assert len(deserialized.fault_schedule) == len(sc.fault_schedule)
            assert deserialized.seed == sc.seed
