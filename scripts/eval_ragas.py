"""Provider-backed RAGAS evaluation: no fabricated or partial reports.

Requires RETAILIQ_MODE=full, actual model/embedding credentials and indexed
Chroma data. Unit tests use injected fake evaluators separately and do not
qualify as measured RAGAS evidence.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from retailiq.assistant import ask
from retailiq.core.config import configure_langsmith, settings
from retailiq.evaluation import evaluate_questions, save_report_atomic

QUESTIONS = [
    'Tell me about USB-C GaN Charger 65W',
    'What are the features of USB-C Hub 7-in-1?',
    'Tell me about AlphaBook Pro 14',
]


async def main():
    if os.getenv('RETAILIQ_MODE') != 'full':
        raise RuntimeError('Set RETAILIQ_MODE=full for provider-backed RAGAS')
    configure_langsmith()
    cfg = settings()

    # Keep optional RAGAS imports after environment validation. All provider
    # resources are closed on metric errors, timeouts and successful runs.
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings.base import embedding_factory
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy

    client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
    try:
        llm = llm_factory(cfg.chat_model, provider='openai', client=client)
        embeddings = embedding_factory('openai', model=cfg.embedding_model, client=client)
        report = await evaluate_questions(
            QUESTIONS, ask_fn=ask,
            faithfulness_metric=Faithfulness(llm=llm),
            relevancy_metric=AnswerRelevancy(llm=llm, embeddings=embeddings))
        target = Path(__file__).resolve().parents[1] / 'data' / 'ragas_results.json'
        save_report_atomic(target, report)
    finally:
        await client.close()
    print('RAGAS report saved:', target.name, 'samples:', report['sample_count'])


if __name__ == '__main__':
    asyncio.run(main())
