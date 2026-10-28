"""Validate shared OpenAI-compatible endpoint/key, optionally live-probe both models.

No secrets, endpoint URLs, or raw provider errors printed.
"""
import argparse
from retailiq.config import safe_status, chat_model, embeddings_model


def main():
    parser=argparse.ArgumentParser(description='RetailIQ OpenAI-compatible API checker')
    parser.add_argument('--live',action='store_true',help='Make one chat call and one embeddings call (may cost tokens)')
    args=parser.parse_args()
    status=safe_status()
    print('Provider:', 'READY' if status['provider_ready'] else status['error'])
    print('Chat model:', status.get('chat_model','(unknown)'))
    print('Embedding model:', status.get('embedding_model','(unknown)'))
    print('LangSmith:', 'enabled' if status['langsmith_enabled'] else 'disabled (optional)')
    if not args.live:
        print('DRY RUN: no remote API requests made')
        return
    if not status['provider_ready']:
        raise SystemExit('Cannot run live check: configuration missing or invalid')
    try:
        response=chat_model().invoke('Reply with the single word READY')
        print('Live chat:', 'OK' if str(response.content).strip() else 'EMPTY RESPONSE')
    except Exception as exc:
        print('Live chat: FAILED:',type(exc).__name__)
        raise SystemExit(2) from None
    try:
        vector=embeddings_model().embed_query('RetailIQ embedding health check')
        print('Live embeddings: OK; dimensions:',len(vector))
    except Exception as exc:
        print('Live embeddings: FAILED:',type(exc).__name__)
        raise SystemExit(3) from None


if __name__=='__main__':main()
