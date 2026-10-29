"""Prevent evaluation-only packages from blocking the RetailIQ chat install."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_runtime_does_not_require_evaluation_only_packages():
    runtime = (ROOT / 'requirements-full.txt').read_text(encoding='utf8')
    declared = [line.split('#', 1)[0].strip().lower() for line in runtime.splitlines()]
    assert not any(line.startswith('ragas') or line.startswith('scikit-network') for line in declared)
    assert not any(line.startswith('langchain-community') for line in declared)
    assert any(line.startswith('langgraph-checkpoint-sqlite') for line in declared)
    assert any(line.startswith('langchain-chroma') for line in declared)


def test_evaluation_keeps_ragas_and_runtime_dependencies():
    evaluation = (ROOT / 'requirements-eval.txt').read_text(encoding='utf8')
    assert '-r requirements-full.txt' in evaluation
    assert 'ragas>=0.4,<0.5' in evaluation
    assert 'langchain-community==0.4.1' in evaluation
