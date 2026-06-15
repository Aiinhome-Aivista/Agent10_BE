"""
rag/retriever.py — Semantic (ChromaDB) and graph (ArangoDB) retrieval
"""
import logging
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_community.embeddings import HuggingFaceEmbeddings
from arango import ArangoClient
from configs.base import BaseConfig

logger = logging.getLogger(__name__)
config = BaseConfig()


class RagRetriever:
    def __init__(self):
        self.chroma_client = chromadb.HttpClient(
            host=config.CHROMADB_HOST,
            port=config.CHROMADB_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=config.CHROMADB_COLLECTION
        )
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.arango = ArangoClient(
            hosts=f"http://{config.ARANGODB_HOST}:{config.ARANGODB_PORT}"
        )

    async def retrieve_chunks(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic retrieval from ChromaDB."""
        query_embedding = self.embeddings.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({
                "text": doc,
                "source": meta.get("source", "unknown") if meta else "unknown",
                "title": meta.get("title", "") if meta else "",
                "similarity": round(1 - dist, 4),
            })
        return chunks

    async def retrieve_graph_relations(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve related graph nodes from ArangoDB."""
        try:
            db = self.arango.db(
                config.ARANGODB_DB,
                username=config.ARANGODB_USER,
                password=config.ARANGODB_PASSWORD,
            )
            # Simple keyword-based graph traversal
            aql = """
                FOR doc IN kb_nodes
                    FILTER CONTAINS(LOWER(doc.content), LOWER(@query))
                    LIMIT 5
                    RETURN {id: doc._id, label: doc.label, content: doc.content}
            """
            cursor = db.aql.execute(aql, bind_vars={"query": query[:50]})
            return list(cursor)
        except Exception as e:
            logger.warning("ArangoDB retrieval failed: %s", e)
            return []
