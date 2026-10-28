"""Build/update Chroma explicitly before full-mode queries (requires embeddings)."""
from retailiq.rag.indexing import sync_index

if __name__ == '__main__':
    print(sync_index())
