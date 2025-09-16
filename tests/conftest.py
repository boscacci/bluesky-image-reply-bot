"""
Pytest configuration and fixtures for Bluesky Bot tests
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch


@pytest.fixture
def temp_directory():
    """Create a temporary directory for tests"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def mock_ssm_client():
    """Mock SSM client for testing"""
    with patch('boto3.client') as mock_boto:
        mock_ssm = Mock()
        mock_boto.return_value = mock_ssm
        yield mock_ssm


@pytest.fixture
def mock_bluesky_client():
    """Mock Bluesky client for testing"""
    with patch('atproto.Client') as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def sample_post_data():
    """Sample post data for testing"""
    return {
        'text': 'Test post with sample content',
        'handle': 'test.bsky.social',
        'display_name': 'Test User',
        'indexed_at': '2024-01-01T00:00:00Z',
        'uri': 'at://did:plc:123/post1'
    }


@pytest.fixture
def sample_image_data():
    """Sample image data for testing"""
    return {
        'url': 'https://example.com/test-image.jpg',
        'alt_text': 'Test image description',
        'content': b'fake_image_binary_data'
    }
