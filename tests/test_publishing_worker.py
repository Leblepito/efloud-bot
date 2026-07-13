"""Test publishing worker - approved draft processing and platform publishing."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from backend.social.publishing_worker import PublishingWorker
from backend.social.content_queue import ContentDraft, ContentStatus
from backend.social.queue_storage import save_draft, load_draft


@pytest.fixture
def mock_db():
    """Mock database pool."""
    db = Mock()
    db.pool = Mock()
    return db


@pytest.fixture
def sample_draft():
    """Sample approved content draft."""
    return ContentDraft(
        draft_id="test-draft-001",
        body="Test signal content for #BTCUSDT",
        lang="en",
        post_type="signal",
        status=ContentStatus.APPROVED,
        meta={
            "platforms": ["x"],
            "chart_url": "https://example.com/chart.png"
        },
        created_at=datetime.now(timezone.utc).isoformat(),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        reviewer_id="test-reviewer",
        rejection_reason=None
    )


@pytest.fixture
def worker():
    """Publishing worker instance."""
    return PublishingWorker()


class TestPublishingWorker:
    """Test publishing worker functionality."""

    @pytest.mark.asyncio
    async def test_worker_initialization(self, worker):
        """Test worker initializes correctly."""
        assert worker is not None
        assert worker._running is False
        assert worker._task is None

    @pytest.mark.asyncio
    async def test_process_approved_drafts_empty(self, worker, mock_db):
        """Test processing when no approved drafts exist."""
        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[]):
            count = await worker.process_approved_drafts()
            assert count == 0

    @pytest.mark.asyncio
    async def test_process_draft_x_success(self, worker, mock_db, sample_draft):
        """Test successful draft publishing to X."""
        # Mock the clients
        mock_x_client = Mock()
        mock_x_client.is_active.return_value = True
        mock_x_client.post_draft.return_value = Mock(
            ok=True,
            post_id="123456",
            post_url="https://x.com/user/status/123456"
        )

        worker._x_client = mock_x_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[sample_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            count = await worker.process_approved_drafts()
            assert count == 1

    @pytest.mark.asyncio
    async def test_process_draft_x_failure(self, worker, mock_db, sample_draft):
        """Test draft publishing failure to X."""
        # Mock the clients to fail
        mock_x_client = Mock()
        mock_x_client.is_active.return_value = True
        mock_x_client.post_draft.return_value = Mock(
            ok=False,
            stderr="Rate limit exceeded"
        )

        worker._x_client = mock_x_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[sample_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            count = await worker.process_approved_drafts()
            assert count == 1  # Still processed (attempted)

    @pytest.mark.asyncio
    async def test_process_draft_multi_platform(self, worker, mock_db):
        """Test draft publishing to multiple platforms."""
        multi_platform_draft = ContentDraft(
            draft_id="test-draft-002",
            body="Multi-platform test content",
            lang="en",
            post_type="signal",
            status=ContentStatus.APPROVED,
            meta={
                "platforms": ["x", "instagram"],
                "chart_url": "https://example.com/chart.png"
            },
            created_at=datetime.now(timezone.utc).isoformat(),
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            reviewer_id="test-reviewer",
            rejection_reason=None
        )

        # Mock clients
        mock_x_client = Mock()
        mock_x_client.is_active.return_value = True
        mock_x_client.post_draft.return_value = Mock(ok=True, post_id="x-123")

        mock_instagram_client = Mock()
        mock_instagram_client.is_active.return_value = True
        mock_instagram_client.post_draft.return_value = Mock(
            ok=True,
            post_id="ig-456",
            post_url="https://instagram.com/p/456"
        )

        worker._x_client = mock_x_client
        worker._instagram_client = mock_instagram_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[multi_platform_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            count = await worker.process_approved_drafts()
            assert count == 1

    @pytest.mark.asyncio
    async def test_process_draft_skip_already_published(self, worker, mock_db):
        """Test that already published drafts are skipped."""
        # Draft with successful publish results
        published_draft = ContentDraft(
            draft_id="test-draft-003",
            body="Already published content",
            lang="en",
            post_type="signal",
            status=ContentStatus.APPROVED,
            meta={
                "platforms": ["x"],
                "publish_results": {
                    "x": {"ok": True, "post_id": "123456"}
                }
            },
            created_at=datetime.now(timezone.utc).isoformat(),
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            reviewer_id="test-reviewer",
            rejection_reason=None
        )

        mock_x_client = Mock()
        mock_x_client.is_active.return_value = True
        worker._x_client = mock_x_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[published_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            count = await worker.process_approved_drafts()
            # Should process but skip X platform (already published)
            assert count == 1

    @pytest.mark.asyncio
    async def test_process_draft_inactive_platform(self, worker, mock_db, sample_draft):
        """Test draft publishing when platform is inactive."""
        # Mock inactive client
        mock_x_client = Mock()
        mock_x_client.is_active.return_value = False

        worker._x_client = mock_x_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[sample_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            count = await worker.process_approved_drafts()
            assert count == 1  # Still processed (attempted)

    def test_worker_stop(self, worker):
        """Test worker stops correctly."""
        worker._running = True
        worker.stop()
        assert worker._running is False


class TestWorkerIntegration:
    """Integration tests for publishing worker."""

    @pytest.mark.asyncio
    async def test_worker_get_clients_lazy_initialization(self, worker):
        """Test that clients are lazily initialized."""
        # Before calling _get_clients, clients should be None
        assert worker._x_client is None
        assert worker._instagram_client is None
        assert worker._youtube_client is None

        # After calling _get_clients, clients should be initialized (even if inactive)
        clients = worker._get_clients()
        assert "x" in clients
        assert "instagram" in clients
        assert "youtube" in clients

    @pytest.mark.asyncio
    async def test_worker_error_handling(self, worker, mock_db):
        """Test error handling in worker processing."""
        # Create a draft that will cause an error
        error_draft = ContentDraft(
            draft_id="test-draft-error",
            body="Error test",
            lang="en",
            post_type="signal",
            status=ContentStatus.APPROVED,
            meta={"platforms": ["x"]},
            created_at=datetime.now(timezone.utc).isoformat(),
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            reviewer_id="test-reviewer",
            rejection_reason=None
        )

        # Mock client to raise exception
        mock_x_client = Mock()
        mock_x_client.is_active.return_value = True
        mock_x_client.post_draft.side_effect = Exception("Network error")

        worker._x_client = mock_x_client

        with patch('backend.social.publishing_worker.db', mock_db), \
             patch('backend.social.publishing_worker.list_by_status', return_value=[error_draft]), \
             patch('backend.social.publishing_worker.save_draft'):
            # Should not raise, should handle error gracefully
            count = await worker.process_approved_drafts()
            assert count == 1  # Still counts as processed (attempted)
