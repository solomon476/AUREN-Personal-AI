"""Regression tests for Search and Reflection API endpoints.

Verifies:
1. Canonical user.id and compatibility property user.user_id on AuthenticatedUser.
2. Search endpoint works for authenticated users without AttributeError.
3. Reflection endpoints work for authenticated users without AttributeError.
4. Authenticated user identity is strictly propagated to underlying services.
5. User A cannot substitute or act as User B (strict identity isolation).
6. Unauthenticated requests are rejected with HTTP 401.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.models.search import (
    ContradictionItem,
    OmnisearchResponse,
    RecordLinkCreate,
    RecordLinkItem,
    ReflectionInsightsResponse,
    RelationshipsResponse,
    RelationshipType,
    SourceType,
    StalenessItem,
)
from app.models.user import AuthenticatedUser
from app.services.reflection.reflection_service import ReflectionService
from app.services.search.omnisearch_service import OmnisearchService

client = TestClient(app)

USER_A_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_B_ID = UUID("22222222-2222-2222-2222-222222222222")

USER_A = AuthenticatedUser(
    id=USER_A_ID,
    email="usera@example.com",
    role="authenticated",
    token="fake-jwt-token-user-a",
)

USER_B = AuthenticatedUser(
    id=USER_B_ID,
    email="userb@example.com",
    role="authenticated",
    token="fake-jwt-token-user-b",
)


def test_authenticated_user_property_parity():
    """Verify that AuthenticatedUser exposes both canonical id and compatibility user_id."""
    test_id = uuid4()
    u = AuthenticatedUser(id=test_id, email="test@example.com")
    assert u.id == test_id
    assert u.user_id == test_id
    assert u.id is u.user_id


def test_search_endpoint_unauthenticated_rejected():
    """Verify that /api/v1/search rejects unauthenticated callers with HTTP 401."""
    app.dependency_overrides.clear()
    res = client.get("/api/v1/search?q=test")
    assert res.status_code == 401


def test_reflection_endpoints_unauthenticated_rejected():
    """Verify that all reflection endpoints reject unauthenticated callers with HTTP 401."""
    app.dependency_overrides.clear()
    res1 = client.get("/api/v1/reflection/insights")
    assert res1.status_code == 401

    res2 = client.get("/api/v1/reflection/contradictions")
    assert res2.status_code == 401

    res3 = client.get("/api/v1/reflection/staleness")
    assert res3.status_code == 401

    res4 = client.get(f"/api/v1/reflection/relationships?source_type=task&source_id={uuid4()}")
    assert res4.status_code == 401

    res5 = client.get(f"/api/v1/reflection/links?source_type=task&source_id={uuid4()}")
    assert res5.status_code == 401


@pytest.mark.asyncio
async def test_search_endpoint_authenticated_user_propagation():
    """Verify that search endpoint propagates caller's exact user.id without error."""
    app.dependency_overrides[get_current_user] = lambda: USER_A

    mock_search_res = OmnisearchResponse(
        query="python",
        sources_searched=[SourceType.task],
        results=[],
        total_count=0,
        page=1,
        page_size=20,
        has_more=False,
    )

    with patch.object(OmnisearchService, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_search_res
        res = client.get("/api/v1/search?q=python")

        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "python"

        # Verify exact user_id was passed to OmnisearchService
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["user_id"] == USER_A_ID
        assert call_kwargs["user_id"] != USER_B_ID

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reflection_endpoints_authenticated_user_propagation():
    """Verify all reflection endpoints propagate caller's exact user.id without error."""
    app.dependency_overrides[get_current_user] = lambda: USER_A

    # 1. /insights
    mock_insights = ReflectionInsightsResponse(
        contradiction_count=0,
        staleness_count=0,
        inferred_link_count=0,
        contradictions=[],
        staleness_items=[],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    with patch.object(ReflectionService, "get_insights", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = mock_insights
        res = client.get("/api/v1/reflection/insights")
        assert res.status_code == 200
        mock_fn.assert_called_once_with(USER_A_ID)

    # 2. /contradictions
    with patch.object(ReflectionService, "get_contradictions", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = []
        res = client.get("/api/v1/reflection/contradictions")
        assert res.status_code == 200
        mock_fn.assert_called_once_with(USER_A_ID)

    # 3. /staleness
    with patch.object(ReflectionService, "get_staleness", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = []
        res = client.get("/api/v1/reflection/staleness")
        assert res.status_code == 200
        mock_fn.assert_called_once_with(USER_A_ID)

    # 4. /relationships
    target_id = uuid4()
    mock_rel = RelationshipsResponse(
        source_type=SourceType.task,
        source_id=target_id,
        relationships=[],
        total_count=0,
    )
    with patch.object(ReflectionService, "get_relationships", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = mock_rel
        res = client.get(f"/api/v1/reflection/relationships?source_type=task&source_id={target_id}")
        assert res.status_code == 200
        mock_fn.assert_called_once_with(USER_A_ID, SourceType.task, target_id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_user_identity_isolation_and_no_substitution():
    """Verify that User A cannot substitute or spoof User B's identity."""
    # When User A is authenticated
    app.dependency_overrides[get_current_user] = lambda: USER_A

    with patch.object(OmnisearchService, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = OmnisearchResponse(
            query="test", sources_searched=[], results=[], total_count=0, page=1, page_size=20, has_more=False
        )
        # Even if attacker passes user_id in params or headers, backend strictly derives identity from token
        res = client.get(f"/api/v1/search?q=test&user_id={USER_B_ID}")
        assert res.status_code == 200
        assert mock_search.call_args.kwargs["user_id"] == USER_A_ID
        assert mock_search.call_args.kwargs["user_id"] != USER_B_ID

    # Switch session to User B
    app.dependency_overrides[get_current_user] = lambda: USER_B

    with patch.object(OmnisearchService, "search", new_callable=AsyncMock) as mock_search_b:
        mock_search_b.return_value = OmnisearchResponse(
            query="test", sources_searched=[], results=[], total_count=0, page=1, page_size=20, has_more=False
        )
        res = client.get("/api/v1/search?q=test")
        assert res.status_code == 200
        assert mock_search_b.call_args.kwargs["user_id"] == USER_B_ID
        assert mock_search_b.call_args.kwargs["user_id"] != USER_A_ID

    app.dependency_overrides.clear()
