"""Tests for security utilities."""

import pytest
from scp_shared.common.security import mask_connection_url


class TestMaskConnectionUrl:
    """Test connection URL masking for safe logging."""
    
    def test_masks_postgresql_url_with_credentials(self):
        """Masks password in PostgreSQL URL while preserving username."""
        url = "postgresql://user:password123@localhost:5432/mydb"
        masked = mask_connection_url(url)
        
        assert masked == "postgresql://user:***@localhost:5432/mydb"
        assert "password123" not in masked
        assert "user" in masked
    
    def test_masks_redis_url_with_credentials(self):
        """Masks password in Redis URL."""
        url = "redis://:secretpass@localhost:6379"
        masked = mask_connection_url(url)
        
        assert masked == "redis://:***@localhost:6379"
        assert "secretpass" not in masked
    
    def test_masks_redis_url_with_username_and_password(self):
        """Masks password in Redis URL with username."""
        url = "redis://admin:admin123@localhost:6379/0"
        masked = mask_connection_url(url)
        
        assert masked == "redis://admin:***@localhost:6379/0"
        assert "admin123" not in masked
        assert "admin" in masked
    
    def test_handles_url_without_credentials(self):
        """Returns URL unchanged if no credentials present."""
        url = "postgresql://localhost:5432/mydb"
        masked = mask_connection_url(url)
        
        assert masked == url
    
    def test_handles_url_with_username_only(self):
        """Handles URL with username but no password - preserves username."""
        url = "postgresql://user@localhost:5432/mydb"
        masked = mask_connection_url(url)
        
        # Username is not sensitive, so it should be preserved
        assert masked == url
        assert "user" in masked
        assert "***" not in masked
    
    def test_handles_invalid_url_gracefully(self):
        """Returns safe message if URL parsing fails."""
        url = "not a valid url at all!!!"
        masked = mask_connection_url(url)
        
        assert masked == "<connection_url_masked>"
    
    def test_preserves_url_structure(self):
        """Preserves scheme, host, port, path, and query parameters."""
        url = "postgresql://user:pass@host.example.com:5432/mydb?sslmode=require"
        masked = mask_connection_url(url)
        
        assert masked.startswith("postgresql://")
        assert "host.example.com" in masked
        assert ":5432" in masked
        assert "/mydb" in masked
        assert "sslmode=require" in masked
        assert "pass" not in masked

