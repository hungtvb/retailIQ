"""Pure contracts for provider-backed RAG evaluation reporting.

The evaluator is external and may fail. Never turn incomplete, non-finite,
mock or partially written measurements into a successful RAGAS report.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

EVALUATION_METRICS = ('faithfulness', 'answer_relevancy')
MIN_CASES = 3


class EvaluationDataError(ValueError):
    """Evaluation evidence is incomplete, inconsistent or not measurable."""


def checked_score(value: object, metric: str) -> float:
    """Scores are probabilities in [0,1]; reject NaN/inf and booleans."""
    if metric not in EVALUATION_METRICS:
        raise EvaluationDataError('Unknown evaluation metric')
    if isinstance(value, bool):
        raise EvaluationDataError(f'Invalid {metric} score')
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvaluationDataError(f'Invalid {metric} score') from exc
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise EvaluationDataError(f'Out-of-range {metric} score')
    return score


def checked_case(question: str, output: dict) -> dict:
    """Validate actual RAG answer/context shape; return no raw text to disk."""
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
        raise EvaluationDataError('Invalid evaluation question')
    if not isinstance(output, dict):
        raise EvaluationDataError('Missing agent response')
    answer = output.get('answer')
    contexts = output.get('contexts')
    if not isinstance(answer, str) or not answer.strip():
        raise EvaluationDataError('Empty answer cannot be evaluated')
    if not isinstance(contexts, list) or not contexts:
        raise EvaluationDataError('Missing retrieved contexts')
    if len(contexts) > 10:
        raise EvaluationDataError('Unexpected number of retrieved contexts')
    for context in contexts:
        if not isinstance(context, dict):
            raise EvaluationDataError('Malformed context')
        if (not isinstance(context.get('text'), str) or not context['text'].strip()
                or not isinstance(context.get('source'), str)
                or not context['source'].strip()):
            raise EvaluationDataError('Missing context content or provenance')
    # Preserve only stable case fingerprint and data counts in the public report.
    # No raw prompts, generated answers, chunks or source document paths.
    return {
        'case_id': sha256(question.strip().encode('utf8')).hexdigest()[:16],
        'source_count': len(contexts),
    }


def checked_measurement(case: dict, faithfulness: object,
                        answer_relevancy: object) -> dict:
    if (not isinstance(case, dict) or
            not isinstance(case.get('case_id'), str) or
            not isinstance(case.get('source_count'), int) or
            case['source_count'] < 1):
        raise EvaluationDataError('Invalid evaluation case descriptor')
    return {
        'case_id': case['case_id'],
        'source_count': case['source_count'],
        'faithfulness': checked_score(faithfulness, 'faithfulness'),
        'answer_relevancy': checked_score(answer_relevancy, 'answer_relevancy'),
    }


def build_report(samples: list[dict], *, evaluator: str, execution_mode: str) -> dict:
    """No partial, duplicate, simulated or unmeasured run can be accepted."""
    if execution_mode != 'full' or evaluator != 'ragas':
        raise EvaluationDataError('This report requires real full-mode RAGAS evaluation')
    if not isinstance(samples, list) or len(samples) < MIN_CASES:
        raise EvaluationDataError('Too few evaluated cases for the configured dataset')
    ids = set()
    normalized = []
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {
                'case_id', 'source_count', *EVALUATION_METRICS}:
            raise EvaluationDataError('Malformed evaluation sample')
        case_id = sample['case_id']
        if not isinstance(case_id, str) or not re.fullmatch(r'[0-9a-f]{16}', case_id) or case_id in ids:
            raise EvaluationDataError('Duplicate or invalid evaluation case ID')
        ids.add(case_id)
        normalized.append(checked_measurement(
            sample, sample['faithfulness'], sample['answer_relevancy']))
    summary = {
        metric: {
            'mean': sum(sample[metric] for sample in normalized) / len(normalized),
            'min': min(sample[metric] for sample in normalized),
        }
        for metric in EVALUATION_METRICS
    }
    return {
        'schema_version': 1,
        'run_id': uuid4().hex,
        'evaluated_at': datetime.now(timezone.utc).isoformat(),
        'execution_mode': execution_mode,
        'evaluator': evaluator,
        'sample_count': len(normalized),
        'summary': summary,
        'samples': normalized,
        'note': 'Provider-backed evaluation; scores are not a production quality certification.',
    }


def save_report_atomic(target: Path, report: dict) -> None:
    """Write only a complete validated report; keep previous result on failure."""
    required = {'schema_version', 'run_id', 'evaluated_at', 'execution_mode',
                'evaluator', 'sample_count', 'summary', 'samples', 'note'}
    if not isinstance(report, dict) or set(report) != required or report.get('schema_version') != 1:
        raise EvaluationDataError('Invalid report schema')
    if not isinstance(report.get('run_id'), str) or not re.fullmatch(r'[0-9a-f]{32}', report['run_id']):
        raise EvaluationDataError('Invalid report ID')
    try:
        stamp = datetime.fromisoformat(report['evaluated_at'])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('Timezone required')
    except (TypeError, ValueError, KeyError) as error:
        raise EvaluationDataError('Invalid evaluation timestamp') from error
    if report.get('note') != 'Provider-backed evaluation; scores are not a production quality certification.':
        raise EvaluationDataError('Invalid report note')
    computed = build_report(report['samples'], evaluator=report.get('evaluator'),
                            execution_mode=report.get('execution_mode'))
    if (report['sample_count'] != computed['sample_count'] or
            report['summary'] != computed['summary'] or
            report['samples'] != computed['samples']):
        raise EvaluationDataError('Inconsistent evaluation report')
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    candidate = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', dir=target.parent, prefix=target.name + '.',
                suffix='.tmp', encoding='utf8', delete=False) as handle:
            candidate = Path(handle.name)
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                pass
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        candidate.replace(target)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)


async def evaluate_questions(questions: list[str], *, ask_fn,
                             faithfulness_metric, relevancy_metric) -> dict:
    """Execute all cases before producing any report; propagate evaluator errors.

    The caller supplies provider-backed evaluators. This function intentionally
    does not catch remote timeouts or synthesize replacement scores.
    """
    if not isinstance(questions, list) or len(questions) < MIN_CASES:
        raise EvaluationDataError('Evaluation dataset is too small')
    measurements = []
    for question in questions:
        output = ask_fn(question)
        descriptor = checked_case(question, output)
        contexts = [item['text'] for item in output['contexts']]
        faithfulness = await faithfulness_metric.ascore(
            user_input=question, response=output['answer'], retrieved_contexts=contexts)
        relevancy = await relevancy_metric.ascore(
            user_input=question, response=output['answer'])
        measurements.append(checked_measurement(
            descriptor, getattr(faithfulness, 'value', None),
            getattr(relevancy, 'value', None)))
    return build_report(measurements, evaluator='ragas', execution_mode='full')
