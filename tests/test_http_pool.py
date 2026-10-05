"""Pooled outbound HTTP client + embedding cache (services/http.py, services/llm.py).

Pure logic — no network, no services. These guard two things that fail silently:
a client reused across a dead event loop, and a cache that serves a stale vector.
"""

import asyncio

from api.services.http import close_shared_client, shared_client
from api.services.llm import _LRU


async def test_same_loop_reuses_one_client():
    a = shared_client(30.0)
    b = shared_client(30.0)
    assert a is b, "a second call in the same loop must reuse the pooled client"
    await close_shared_client()


def test_new_event_loop_gets_a_fresh_client():
    """
    An AsyncClient binds to the loop that created it. Celery runs each task under a fresh
    asyncio.run() loop, so a globally cached client would be handed to a dead loop.
    """
    ids = []

    async def grab():
        client = shared_client(30.0)
        ids.append(id(client))
        # Deliberately do NOT close: this simulates a worker loop exiting mid-flight.

    asyncio.run(grab())
    asyncio.run(grab())
    assert len(ids) == 2
    assert ids[0] != ids[1], "each event loop must get its own client"


async def test_closed_client_is_replaced():
    first = shared_client(30.0)
    await first.aclose()
    second = shared_client(30.0)
    assert second is not first, "a closed client must not be handed out again"
    assert not second.is_closed
    await close_shared_client()


async def test_close_is_idempotent():
    shared_client(30.0)
    await close_shared_client()
    await close_shared_client()  # must not raise on an already-drained pool


# --- embedding cache ---------------------------------------------------------------

def test_cache_returns_stored_vector_and_counts_hits():
    cache = _LRU(maxsize=4)
    key = ("retrieval.query", "max allowable pressure")
    assert cache.get(key) is None
    assert cache.misses == 1

    cache.put(key, [0.1, 0.2, 0.3])
    assert cache.get(key) == [0.1, 0.2, 0.3]
    assert cache.hits == 1


def test_cache_never_stores_a_failed_embedding():
    """A failed Jina call returns []. Caching that would poison every later search."""
    cache = _LRU()
    cache.put(("retrieval.query", "q"), [])
    assert len(cache) == 0
    assert cache.get(("retrieval.query", "q")) is None


def test_cache_evicts_least_recently_used():
    cache = _LRU(maxsize=2)
    cache.put(("t", "a"), [1.0])
    cache.put(("t", "b"), [2.0])
    cache.get(("t", "a"))            # 'a' becomes most recent
    cache.put(("t", "c"), [3.0])     # evicts 'b'
    assert cache.get(("t", "a")) == [1.0]
    assert cache.get(("t", "b")) is None
    assert cache.get(("t", "c")) == [3.0]


def test_task_is_part_of_the_cache_key():
    """jina-embeddings-v3 returns different vectors per task — keys must not collide."""
    cache = _LRU()
    cache.put(("retrieval.query", "seal failure"), [1.0])
    cache.put(("retrieval.passage", "seal failure"), [2.0])
    assert cache.get(("retrieval.query", "seal failure")) == [1.0]
    assert cache.get(("retrieval.passage", "seal failure")) == [2.0]
