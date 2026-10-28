"""RAGAS evaluation on actual vector contexts (requires RAGAS 0.4.x and API)."""
import asyncio, json, os
from pathlib import Path
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from ragas.metrics.collections import Faithfulness, AnswerRelevancy
from retailiq.assistant import ask
from retailiq.config import settings, configure_langsmith


async def main():
    if os.getenv('RETAILIQ_MODE')!='full':
        raise RuntimeError('Set RETAILIQ_MODE=full for RAGAS; offline lexical retrieval is not vector RAG')
    configure_langsmith()
    cfg=settings()
    client=AsyncOpenAI(base_url=cfg.base_url,api_key=cfg.api_key)
    # LLM and embedding model names can differ while sharing the same API client.
    llm=llm_factory(cfg.chat_model,provider='openai',client=client)
    embeddings=embedding_factory('openai',model=cfg.embedding_model,client=client)
    faith=Faithfulness(llm=llm)
    relevance=AnswerRelevancy(llm=llm,embeddings=embeddings)
    results=[]
    questions=[
        'Tell me about USB-C GaN Charger 65W',
        'What are the features of USB-C Hub 7-in-1?',
        'Tell me about AlphaBook Pro 14',
    ]
    for question in questions:
        output=ask(question)
        contexts=[ctx['text'] for ctx in output['contexts']]
        if not contexts:raise RuntimeError('Missing retrieved contexts: aborting RAGAS')
        f=await faith.ascore(user_input=question,response=output['answer'],retrieved_contexts=contexts)
        r=await relevance.ascore(user_input=question,response=output['answer'])
        results.append({'question':question,'faithfulness':float(f.value),'answer_relevancy':float(r.value),
                        'retrieved_sources':[ctx['source'] for ctx in output['contexts']]})
    target=Path(__file__).resolve().parents[1]/'data'/'ragas_results.json'
    target.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    print('RAGAS evaluation saved:',target.name,'samples:',len(results))

if __name__=='__main__':asyncio.run(main())
