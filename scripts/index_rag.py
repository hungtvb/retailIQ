"""CLI: inspect or re-index local product knowledge files."""
import argparse
import json
from retailiq.rag.indexing import plan_chunks, sync_index


def main():
    parser = argparse.ArgumentParser(description='RetailIQ RAG document ingestion')
    parser.add_argument('--dry-run', action='store_true', help='Parse/chunk without API or VectorDB')
    parser.add_argument('--force', action='store_true', help='Re-embed every supported file')
    args = parser.parse_args()
    if args.dry_run:
        docs, errors = plan_chunks(strict=False)
        result = {'files':len(docs), 'chunks':sum(len(v) for v in docs.values()),
                  'by_format': {ext:sum(path.endswith(ext) for path in docs)
                                for ext in ['.md','.txt','.pdf','.docx','.csv','.xlsx','.json','.html','.htm']},
                  'errors':errors}
    else:
        result = sync_index(force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
