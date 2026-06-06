"""
Graph retriever — uses ArangoDB for policy/compliance relationships.
"""
import logging
from typing import List, Dict
from arango import ArangoClient
from configs.base import settings

logger = logging.getLogger(__name__)

_client = None
_db     = None
_db_failed = False


def _get_db():
    global _client, _db, _db_failed
    if _db_failed:
        return None
    if _db is None:
        import socket
        try:
            # Quick TCP reachability check (1.5s timeout) to prevent DNS or connection hangs
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            sock.connect((settings.ARANGODB_HOST, settings.ARANGODB_PORT))
            sock.close()
        except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
            logger.warning(
                f"ArangoDB at {settings.ARANGODB_HOST}:{settings.ARANGODB_PORT} is not reachable ({e}). "
                "Skipping Graph DB initialization."
            )
            _db_failed = True
            return None

        try:
            _client = ArangoClient(hosts=f"http://{settings.ARANGODB_HOST}:{settings.ARANGODB_PORT}")
            sys_db  = _client.db("_system", username=settings.ARANGODB_USER, password=settings.ARANGODB_PASSWORD)
            if not sys_db.has_database(settings.ARANGODB_DB):
                sys_db.create_database(settings.ARANGODB_DB)
            _db = _client.db(
                settings.ARANGODB_DB,
                username=settings.ARANGODB_USER,
                password=settings.ARANGODB_PASSWORD,
            )
            _ensure_collections()
        except Exception as e:
            logger.warning(f"ArangoDB connection failed: {e}")
            return None
    return _db


def _ensure_collections():
    db = _db
    if db is None:
        return
    for col in ["knowledge_nodes", "knowledge_edges"]:
        if not db.has_collection(col):
            if col.endswith("edges"):
                db.create_collection(col, edge=True)
            else:
                db.create_collection(col)


def store_relationship(source_id: str, target_id: str, relation_type: str, meta: dict = None):
    try:
        db = _get_db()
        if db is None:
            return
        nodes = db.collection("knowledge_nodes")
        edges = db.collection("knowledge_edges")
        for nid in [source_id, target_id]:
            if not nodes.has(nid):
                nodes.insert({"_key": nid, "node_id": nid})
        edges.insert({
            "_from": f"knowledge_nodes/{source_id}",
            "_to":   f"knowledge_nodes/{target_id}",
            "relation": relation_type,
            **(meta or {}),
        })
    except Exception as e:
        logger.warning(f"ArangoDB store_relationship failed: {e}")


def retrieve_related(query_terms: List[str], limit: int = 10) -> List[Dict]:
    try:
        db = _get_db()
        if db is None:
            return []
        results = []
        for term in query_terms[:3]:
            cursor = db.aql.execute(
                """
                FOR n IN knowledge_nodes
                    FILTER CONTAINS(LOWER(n.node_id), LOWER(@term))
                    LIMIT 5
                    FOR e IN knowledge_edges
                        FILTER e._from == n._id OR e._to == n._id
                        LIMIT @limit
                        RETURN {source: e._from, target: e._to, relation: e.relation}
                """,
                bind_vars={"term": term, "limit": limit},
            )
            results.extend(list(cursor))
        return results[:limit]
    except Exception as e:
        logger.warning(f"ArangoDB retrieve_related failed: {e}")
        return []
