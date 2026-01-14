"""Domain parsing and normalization utilities."""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import tldextract


class DomainParser:
    """Utilities for parsing and normalizing domain names."""

    @staticmethod
    def extract_from_url(url: str) -> Tuple[str, str]:
        """
        Extract domain and root domain from a URL.

        Args:
            url: Full URL or domain string

        Returns:
            Tuple of (domain, root_domain)

        Example:
            extract_from_url("https://shop.example.co.uk/page")
            -> ("shop.example.co.uk", "example.co.uk")
        """
        # Handle URLs without protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split("/")[0]

        # Remove port if present
        host = host.split(":")[0]

        # Remove www prefix
        host = re.sub(r"^www\.", "", host, flags=re.IGNORECASE)

        # Extract root domain using tldextract
        extracted = tldextract.extract(host)

        if extracted.suffix:
            root_domain = f"{extracted.domain}.{extracted.suffix}"
            if extracted.subdomain:
                domain = f"{extracted.subdomain}.{root_domain}"
            else:
                domain = root_domain
        else:
            # Handle IPs or invalid domains
            domain = host
            root_domain = host

        return domain.lower(), root_domain.lower()

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """
        Normalize a domain for consistent storage.

        Removes:
        - Protocol (http://, https://)
        - www prefix
        - Trailing slashes
        - Port numbers
        """
        # Remove protocol
        domain = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)

        # Remove www
        domain = re.sub(r"^www\.", "", domain, flags=re.IGNORECASE)

        # Remove port
        domain = domain.split(":")[0]

        # Remove path
        domain = domain.split("/")[0]

        return domain.lower().strip()

    @staticmethod
    def extract_display_domain(display_url: str) -> str:
        """
        Extract domain from Google Ads display URL.

        Display URLs often look like:
        - "example.com"
        - "example.com › products"
        - "www.example.com/page"
        """
        # Handle breadcrumb separator
        if "›" in display_url:
            display_url = display_url.split("›")[0].strip()

        return DomainParser.normalize_domain(display_url)

    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """Check if a string is a valid domain."""
        if not domain:
            return False

        # Basic domain pattern
        pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$"

        return bool(re.match(pattern, domain))

    @staticmethod
    def extract_company_name(domain: str, headline: Optional[str] = None) -> Optional[str]:
        """
        Try to extract company name from domain or ad headline.

        This is a heuristic approach - the result should be verified.
        """
        # First try to get from headline (often contains brand name)
        if headline:
            # Look for patterns like "Brand Name - Tagline" or "Brand Name | Description"
            separators = [" - ", " | ", " – ", " — "]
            for sep in separators:
                if sep in headline:
                    potential_name = headline.split(sep)[0].strip()
                    if 2 < len(potential_name) < 50:
                        return potential_name

        # Fall back to domain-based extraction
        extracted = tldextract.extract(domain)
        if extracted.domain:
            # Convert domain to title case
            name = extracted.domain.replace("-", " ").replace("_", " ")
            return name.title()

        return None

    @staticmethod
    def get_parent_domain(domain: str) -> Optional[str]:
        """
        Get parent domain (remove one subdomain level).

        Example: "shop.store.example.com" -> "store.example.com"
        """
        extracted = tldextract.extract(domain)

        if not extracted.subdomain:
            return None

        subdomains = extracted.subdomain.split(".")
        if len(subdomains) <= 1:
            # Only one subdomain level, return root
            return f"{extracted.domain}.{extracted.suffix}"

        # Remove first subdomain
        new_subdomain = ".".join(subdomains[1:])
        return f"{new_subdomain}.{extracted.domain}.{extracted.suffix}"
