"""Le juge Jev est testé à travers le vrai SDK, contre un faux serveur HTTP (httpx2.MockTransport)."""

import copy
import json

import httpx2
import pytest
from typesafe_sdk import TypeSafeAuthenticationError, TypeSafeClient

from jev_zork.judges import MOCK_MODEL, ConfigError, JevJudge, JudgeError, MockJudge
from jev_zork.questions import INTENTS, build_questions

OPTIONS = ("open mailbox", "north", "south", "west")

BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "action": {
            "type": "choice",
            "choice": "open mailbox",
            "confidence": 0.42,
            "probabilities": {"open mailbox": 0.61, "north": 0.35, "south": 0.04, "west": 0.0},
        },
        "danger": {"type": "noul", "noul": 0.03},
        "intent": {
            "type": "choice",
            "choice": "investigate",
            "confidence": 0.5,
            "probabilities": {
                "explore": 0.3,
                "collect": 0.05,
                "investigate": 0.6,
                "puzzle": 0.05,
                "fight": 0.0,
                "escape": 0.0,
            },
        },
    },
    "usage": {"input_tokens": 612, "output_tokens": 41},
}


class FakeClock:
    def __init__(self, *values):
        self._values = list(values)

    def __call__(self):
        return self._values.pop(0)


def body_with(**answers):
    body = copy.deepcopy(BODY)
    for name, answer in answers.items():
        if answer is None:
            del body["answers"][name]
        else:
            body["answers"][name] = answer
    return body


def judge_answering(body, seen=None, status=200):
    def handler(request):
        if seen is not None:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
        return httpx2.Response(status, headers={"x-typesafe-request-id": "req_42"}, json=body)

    client = TypeSafeClient(api_key="test-key", transport=httpx2.MockTransport(handler))
    return JevJudge(client, clock=FakeClock(10.0, 10.25))


def ask(judge):
    state = {"location": "West of House"}
    return judge.judge(state, build_questions(OPTIONS, {}), OPTIONS)


def test_jev_judge_sends_state_and_questions_and_reads_every_answer():
    seen = {}
    judgement = ask(judge_answering(BODY, seen))
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["authorization"] == "Bearer test-key"
    assert seen["body"]["state"] == {"location": "West of House"}
    assert list(seen["body"]["questions"]["action"]["criteria"]) == list(OPTIONS)
    assert judgement.choice == "open mailbox"
    assert judgement.probabilities == pytest.approx(
        {"open mailbox": 0.61, "north": 0.35, "south": 0.04, "west": 0.0}
    )
    assert judgement.confidence == 0.42
    assert judgement.danger == 0.03
    assert judgement.intent["investigate"] == pytest.approx(0.6)
    assert judgement.latency_ms == 250
    assert (judgement.input_tokens, judgement.output_tokens) == (612, 41)
    assert judgement.model == "jev-1.13.0"
    assert judgement.request_id == "req_42"
    assert judgement.warnings == ()


def test_probabilities_are_renormalized_when_rounding_leaves_a_gap():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["probabilities"] = {"open mailbox": 0.6, "north": 0.3, "south": 0.05, "west": 0.04}
    judgement = ask(judge_answering(body_with(action=action)))
    assert sum(judgement.probabilities.values()) == pytest.approx(1.0)


def test_an_unknown_option_stops_the_game():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["probabilities"]["xyzzy"] = 0.1
    with pytest.raises(JudgeError, match="xyzzy"):
        ask(judge_answering(body_with(action=action)))


def test_a_choice_outside_the_options_stops_the_game():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["choice"] = "east"
    with pytest.raises(JudgeError, match="east"):
        ask(judge_answering(body_with(action=action)))


def test_a_missing_option_counts_as_zero_with_a_warning():
    action = copy.deepcopy(BODY["answers"]["action"])
    del action["probabilities"]["west"]
    judgement = ask(judge_answering(body_with(action=action)))
    assert judgement.probabilities["west"] == 0.0
    assert "west" in judgement.warnings[0]


def test_a_confidence_out_of_range_stops_the_game():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["confidence"] = 1.5
    with pytest.raises(JudgeError, match="Confiance"):
        ask(judge_answering(body_with(action=action)))


def test_an_invalid_probability_stops_the_game():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["probabilities"]["north"] = -0.2
    with pytest.raises(JudgeError, match="north"):
        ask(judge_answering(body_with(action=action)))


def test_all_zero_probabilities_stop_the_game():
    action = copy.deepcopy(BODY["answers"]["action"])
    action["probabilities"] = {option: 0.0 for option in OPTIONS}
    with pytest.raises(JudgeError, match="nulles"):
        ask(judge_answering(body_with(action=action)))


def test_a_missing_action_answer_stops_the_game():
    with pytest.raises(JudgeError, match="action"):
        ask(judge_answering(body_with(action=None)))


def test_missing_danger_and_intent_only_leave_warnings():
    judgement = ask(judge_answering(body_with(danger=None, intent=None)))
    assert judgement.danger is None
    assert judgement.intent == {}
    assert len(judgement.warnings) == 2


def test_an_invalid_intent_distribution_only_leaves_a_warning():
    intent = copy.deepcopy(BODY["answers"]["intent"])
    intent["probabilities"]["explore"] = 7.0
    judgement = ask(judge_answering(body_with(intent=intent)))
    assert judgement.intent == {}
    assert judgement.warnings == ("distribution d'intentions invalide",)


def test_a_danger_out_of_range_only_leaves_a_warning():
    judgement = ask(judge_answering(body_with(danger={"type": "noul", "noul": 1.7})))
    assert judgement.danger is None
    assert "danger" in judgement.warnings[0]


def test_an_authentication_error_reaches_the_caller_as_an_expected_error():
    judge = judge_answering({"detail": "Invalid API key"}, status=401)
    with pytest.raises(TypeSafeAuthenticationError) as caught:
        ask(judge)
    assert isinstance(caught.value, judge.errors)


def test_from_env_without_a_key_explains_what_to_do(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="--mock"):
        JevJudge.from_env(model="jev-latest")


def test_from_env_with_a_key_builds_a_closable_judge(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    judge = JevJudge.from_env(model="jev-latest")
    assert judge.kind == "jev"
    judge.close()


def test_the_mock_judge_is_reproducible_and_says_what_it_is():
    questions = build_questions(OPTIONS, {})
    first = MockJudge(seed=7).judge({}, questions, OPTIONS)
    second = MockJudge(seed=7).judge({}, questions, OPTIONS)
    assert first == second
    assert first.model == MOCK_MODEL
    assert sum(first.probabilities.values()) == pytest.approx(1.0)
    assert first.choice == max(OPTIONS, key=lambda option: first.probabilities[option])
    assert set(first.intent) == set(INTENTS)
    assert 0.0 <= first.danger <= 1.0
    assert 0.0 <= first.confidence <= 1.0


def test_the_mock_judge_needs_options():
    with pytest.raises(JudgeError):
        MockJudge(seed=1).judge({}, {}, ())
