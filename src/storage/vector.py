"""Qdrant vector store wrapper — per-tenant collections (§6.3, §9.2)."""

from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.config import get_settings


@dataclass
class VectorPoint:
    id: str           # chunk_id
    vector: list[float]
    payload: dict     # chunk_id, document_id, collection_tags, page_number, section_heading


class VectorStore:
    """Thin async wrapper around Qdrant.

    Each tenant gets its own Qdrant collection named `tenant_{tenant_id}`.
    RBAC pre-filtering is done via payload filters — collection_tags are stored
    in each vector's payload and filtered BEFORE similarity ranking (§6.2).
    """

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    @staticmethod
    def collection_name(tenant_id: str) -> str:
        return f"tenant_{tenant_id}"

    async def ensure_collection(
        self,
        tenant_id: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> None:
        name = self.collection_name(tenant_id)
        # collection_exists() is O(1); the old get_collections() approach was O(n-tenants).
        if not await self._client.collection_exists(name):
            await self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )
            # Payload indexes make filter checks O(log n) not O(n-vectors).
            # Required for any tenant with significant document volume.
            for field_name in ("document_id", "document_status", "collection_tags"):
                await self._client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                )

    async def upsert(self, tenant_id: str, points: list[VectorPoint]) -> None:
        await self._client.upsert(
            collection_name=self.collection_name(tenant_id),
            points=[
                PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                for p in points
            ],
        )

    async def search(
        self,
        tenant_id: str,
        query_vector: list[float],
        *,
        top_k: int = 20,
        collection_tags: list[str] | None = None,
        document_ids: list[str] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        """RBAC-aware vector search using indexed payload filters.

        Filter precedence (all use indexed fields → O(log n) per filter):
          1. document_status="ready"  — always applied; excludes in-progress docs.
          2. collection_tags           — applied when caller specifies a scope.
          3. document_ids              — applied ONLY when the planner targets
                                        specific documents (not for general search).
                                        Kept small by design — never dump all tenant IDs here.

        Per-tenant collection (`tenant_{id}`) already provides tenant isolation so
        no tenant_id filter is needed at the Qdrant level.
        """
        must: list = [
            FieldCondition(key="document_status", match=MatchValue(value="ready")),
        ]

        if collection_tags:
            must.append(
                FieldCondition(key="collection_tags", match=MatchAny(any=collection_tags))
            )

        if document_ids:
            must.append(
                FieldCondition(key="document_id", match=MatchAny(any=document_ids))
            )

        response = await self._client.query_points(
            collection_name=self.collection_name(tenant_id),
            query=query_vector,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
            score_threshold=score_threshold,
        )
        return [{"id": str(r.id), "score": r.score, **r.payload} for r in response.points]

    async def delete_by_document(
        self, tenant_id: str, document_id: str, ingestion_version: int | None = None
    ) -> None:
        """Delete all vectors for a document (with optional version pinning for replay cleanup).

        If the tenant's Qdrant collection does not exist yet (e.g. the document was
        uploaded but ingestion never completed), there are no vectors to remove and
        this method returns silently rather than raising a 404.
        """
        collection = self.collection_name(tenant_id)
        if not await self._client.collection_exists(collection):
            return

        must = [FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        if ingestion_version is not None:
            must.append(
                FieldCondition(
                    key="ingestion_version", match=MatchValue(value=ingestion_version)
                )
            )
        await self._client.delete(
            collection_name=collection,
            points_selector=Filter(must=must),
        )

    async def delete_collection(self, tenant_id: str) -> None:
        await self._client.delete_collection(self.collection_name(tenant_id))


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    s = get_settings()
    return AsyncQdrantClient(
        host=s.qdrant_host,
        port=s.qdrant_port,
        api_key=s.qdrant_api_key or None,
    )


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return VectorStore(get_qdrant_client())
