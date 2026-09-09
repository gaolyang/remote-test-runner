from backend.testcase.models import EvidencePolicy, InteractionPolicy, Step, StepRole


def make_step(role: StepRole, evidence: EvidencePolicy | None = None) -> Step:
    return Step.model_validate(
        {
            "id": 1,
            "role": role.value,
            "name": "demo",
            "action": {"type": "shell", "command": "true"},
            "evidence": evidence.model_dump() if evidence else None,
        }
    )


def test_verify_captures_by_default() -> None:
    policy = make_step(StepRole.VERIFY).resolved_evidence()
    assert policy.capture is True
    assert policy.trigger == "command_complete"


def test_setup_does_not_capture_by_default() -> None:
    assert make_step(StepRole.SETUP).resolved_evidence().capture is False


def test_explicit_policy_wins() -> None:
    policy = make_step(StepRole.VERIFY, EvidencePolicy(capture=False)).resolved_evidence()
    assert policy.capture is False


def test_interactive_step_accepts_manual_policy() -> None:
    step = Step.model_validate(
        {
            "id": 2,
            "role": "verify",
            "name": "interactive installer",
            "action": {"type": "shell", "command": "./install.sh"},
            "interaction": {"mode": "manual", "instructions": "Choose the installation mode", "timeout": 900},
        }
    )
    assert isinstance(step.interaction, InteractionPolicy)
    assert step.interaction.timeout == 900
