"""Tests for domain parsing utilities."""

import pytest

from src.utils.domain_parser import DomainParser


class TestDomainParser:
    """Tests for DomainParser class."""

    def test_extract_from_url_simple(self):
        """Test extraction from simple URL."""
        domain, root_domain = DomainParser.extract_from_url("https://example.com/page")
        assert domain == "example.com"
        assert root_domain == "example.com"

    def test_extract_from_url_with_subdomain(self):
        """Test extraction from URL with subdomain."""
        domain, root_domain = DomainParser.extract_from_url("https://shop.example.com/products")
        assert domain == "shop.example.com"
        assert root_domain == "example.com"

    def test_extract_from_url_with_www(self):
        """Test extraction removes www prefix."""
        domain, root_domain = DomainParser.extract_from_url("https://www.example.com")
        assert domain == "example.com"
        assert root_domain == "example.com"

    def test_extract_from_url_country_tld(self):
        """Test extraction with country code TLD."""
        domain, root_domain = DomainParser.extract_from_url("https://shop.example.co.uk/page")
        assert domain == "shop.example.co.uk"
        assert root_domain == "example.co.uk"

    def test_extract_from_url_without_protocol(self):
        """Test extraction from URL without protocol."""
        domain, root_domain = DomainParser.extract_from_url("example.com/page")
        assert domain == "example.com"
        assert root_domain == "example.com"

    def test_extract_from_url_with_port(self):
        """Test extraction removes port number."""
        domain, root_domain = DomainParser.extract_from_url("https://example.com:8080/page")
        assert domain == "example.com"
        assert root_domain == "example.com"

    def test_normalize_domain(self):
        """Test domain normalization."""
        assert DomainParser.normalize_domain("https://www.example.com/page") == "example.com"
        assert DomainParser.normalize_domain("HTTP://EXAMPLE.COM") == "example.com"
        assert DomainParser.normalize_domain("example.com:8080/path") == "example.com"

    def test_extract_display_domain(self):
        """Test display domain extraction from Google ads."""
        assert DomainParser.extract_display_domain("example.com › products") == "example.com"
        assert DomainParser.extract_display_domain("www.example.com/shop") == "example.com"
        assert DomainParser.extract_display_domain("example.com") == "example.com"

    def test_is_valid_domain(self):
        """Test domain validation."""
        assert DomainParser.is_valid_domain("example.com") is True
        assert DomainParser.is_valid_domain("sub.example.com") is True
        assert DomainParser.is_valid_domain("example.co.uk") is True
        assert DomainParser.is_valid_domain("") is False
        assert DomainParser.is_valid_domain("not-a-domain") is False
        assert DomainParser.is_valid_domain("http://example.com") is False  # Has protocol

    def test_extract_company_name_from_domain(self):
        """Test company name extraction from domain."""
        assert DomainParser.extract_company_name("shoestore.com") == "Shoestore"
        assert DomainParser.extract_company_name("my-company.com") == "My Company"
        assert DomainParser.extract_company_name("example_site.com") == "Example Site"

    def test_extract_company_name_from_headline(self):
        """Test company name extraction from ad headline."""
        name = DomainParser.extract_company_name(
            "example.com",
            headline="ShoeStore - Buy Shoes Online"
        )
        assert name == "ShoeStore"

        name = DomainParser.extract_company_name(
            "example.com",
            headline="Best Shoes | Premium Footwear"
        )
        assert name == "Best Shoes"

    def test_get_parent_domain(self):
        """Test parent domain extraction."""
        assert DomainParser.get_parent_domain("shop.store.example.com") == "store.example.com"
        assert DomainParser.get_parent_domain("shop.example.com") == "example.com"
        assert DomainParser.get_parent_domain("example.com") is None
