"""Keyword expansion and generation."""

import re
from collections import Counter
from typing import List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class KeywordExpander:
    """Generate keywords to discover more ads from a specific advertiser."""

    # Common modifiers for long-tail keyword generation
    PREFIX_MODIFIERS = [
        "best", "top", "cheap", "affordable", "professional",
        "local", "online", "free", "premium", "quality",
        "trusted", "reliable", "fast", "quick", "easy",
        "buy", "get", "find", "hire", "compare",
    ]

    SUFFIX_MODIFIERS = [
        "near me", "online", "services", "company", "companies",
        "reviews", "pricing", "cost", "price", "quotes",
        "software", "tools", "solutions", "providers", "experts",
        "for business", "for small business", "for enterprise",
        "2024", "today", "now",
    ]

    QUESTION_PREFIXES = [
        "how to", "what is", "how do I", "where to",
        "why use", "when to", "which", "best way to",
    ]

    COMPARISON_PATTERNS = [
        "{brand} vs {competitor}",
        "{brand} alternative",
        "{brand} alternatives",
        "{brand} competitor",
        "{brand} competitors",
        "better than {brand}",
        "like {brand}",
        "similar to {brand}",
        "{brand} comparison",
        "{brand} review",
        "{brand} reviews",
    ]

    BRAND_MODIFIERS = [
        "{brand}",
        "{brand} reviews",
        "{brand} pricing",
        "{brand} cost",
        "{brand} free trial",
        "{brand} demo",
        "{brand} login",
        "{brand} sign up",
        "{brand} coupon",
        "{brand} discount",
        "is {brand} good",
        "is {brand} worth it",
        "{brand} pros and cons",
    ]

    # Common industry categories and their keywords
    INDUSTRY_KEYWORDS = {
        "saas": [
            "software", "platform", "tool", "app", "application",
            "cloud", "automation", "integration", "API",
        ],
        "ecommerce": [
            "buy", "shop", "store", "purchase", "order",
            "shipping", "delivery", "deals", "sale",
        ],
        "services": [
            "services", "company", "agency", "firm", "consultant",
            "professional", "expert", "specialist",
        ],
        "finance": [
            "loan", "credit", "insurance", "mortgage", "investment",
            "banking", "financial", "rates", "quotes",
        ],
        "health": [
            "doctor", "clinic", "treatment", "therapy", "medical",
            "healthcare", "wellness", "health",
        ],
        "legal": [
            "lawyer", "attorney", "law firm", "legal", "litigation",
            "counsel", "advocate",
        ],
        "education": [
            "course", "training", "learn", "certification", "class",
            "tutorial", "guide", "education",
        ],
    }

    def __init__(
        self,
        domain: str,
        company_name: Optional[str] = None,
        existing_keywords: Optional[List[str]] = None,
        competitors: Optional[List[str]] = None,
    ):
        self.domain = domain
        self.company_name = company_name or self._extract_brand_from_domain(domain)
        self.existing_keywords = existing_keywords or []
        self.competitors = competitors or []

        # Analyze existing keywords
        self._themes = self._extract_keyword_themes()
        self._industry = self._detect_industry()

    def _extract_brand_from_domain(self, domain: str) -> str:
        """Extract brand name from domain."""
        # Remove TLD and www
        brand = re.sub(r"\.(com|net|org|io|co|ai).*$", "", domain)
        brand = re.sub(r"^www\.", "", brand)
        # Convert to readable
        brand = brand.replace("-", " ").replace("_", " ")
        return brand

    def _extract_keyword_themes(self) -> List[str]:
        """Analyze existing keywords to find common themes."""
        if not self.existing_keywords:
            return []

        # Tokenize all keywords
        all_words = []
        for kw in self.existing_keywords:
            words = kw.lower().split()
            # Filter out common stopwords and short words
            words = [w for w in words if len(w) > 2 and w not in self._get_stopwords()]
            all_words.extend(words)

        # Find most common words
        word_counts = Counter(all_words)
        common_themes = [word for word, count in word_counts.most_common(20) if count > 1]

        return common_themes

    def _get_stopwords(self) -> Set[str]:
        """Get common stopwords to filter out."""
        return {
            "the", "and", "for", "with", "from", "that", "this",
            "are", "was", "were", "been", "being", "have", "has",
            "had", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "can", "our", "your", "their",
            "its", "his", "her", "any", "all", "each", "every",
            "both", "few", "more", "most", "other", "some", "such",
        }

    def _detect_industry(self) -> Optional[str]:
        """Detect industry from existing keywords."""
        if not self.existing_keywords:
            return None

        keyword_text = " ".join(self.existing_keywords).lower()

        best_match = None
        best_score = 0

        for industry, indicators in self.INDUSTRY_KEYWORDS.items():
            score = sum(1 for indicator in indicators if indicator in keyword_text)
            if score > best_score:
                best_score = score
                best_match = industry

        return best_match if best_score >= 2 else None

    def generate_expansion_keywords(self, max_keywords: int = 200) -> List[str]:
        """
        Generate keywords likely to show this advertiser's ads.

        Returns deduplicated, prioritized list of keywords.
        """
        keywords = set()

        # 1. Brand-based keywords
        brand_keywords = self._generate_brand_keywords()
        keywords.update(brand_keywords)

        # 2. Theme-based variations
        theme_keywords = self._generate_theme_variations()
        keywords.update(theme_keywords)

        # 3. Long-tail variations of existing keywords
        longtail_keywords = self._generate_longtail_variations()
        keywords.update(longtail_keywords)

        # 4. Question-format keywords
        question_keywords = self._generate_question_keywords()
        keywords.update(question_keywords)

        # 5. Competitor comparison keywords
        if self.competitors:
            comparison_keywords = self._generate_comparison_keywords()
            keywords.update(comparison_keywords)

        # 6. Industry-specific keywords
        if self._industry:
            industry_keywords = self._generate_industry_keywords()
            keywords.update(industry_keywords)

        # Remove existing keywords
        existing_set = {kw.lower().strip() for kw in self.existing_keywords}
        keywords = {kw for kw in keywords if kw.lower().strip() not in existing_set}

        # Clean and deduplicate
        keywords = self._clean_keywords(keywords)

        # Prioritize and limit
        prioritized = self._prioritize_keywords(list(keywords))

        logger.info(
            f"Generated {len(prioritized)} expansion keywords for {self.domain}"
        )

        return prioritized[:max_keywords]

    def _generate_brand_keywords(self) -> Set[str]:
        """Generate brand-related keywords."""
        keywords = set()

        for pattern in self.BRAND_MODIFIERS:
            kw = pattern.format(brand=self.company_name)
            keywords.add(kw)

        return keywords

    def _generate_theme_variations(self) -> Set[str]:
        """Generate variations based on keyword themes."""
        keywords = set()

        for theme in self._themes[:10]:  # Top 10 themes
            # Add prefix modifiers
            for prefix in self.PREFIX_MODIFIERS[:10]:
                keywords.add(f"{prefix} {theme}")

            # Add suffix modifiers
            for suffix in self.SUFFIX_MODIFIERS[:10]:
                keywords.add(f"{theme} {suffix}")

        return keywords

    def _generate_longtail_variations(self) -> Set[str]:
        """Generate long-tail variations of existing keywords."""
        keywords = set()

        # Use top existing keywords
        for base_kw in self.existing_keywords[:20]:
            base_kw = base_kw.strip()

            # Skip very long keywords
            if len(base_kw.split()) > 4:
                continue

            # Add prefixes
            for prefix in self.PREFIX_MODIFIERS[:5]:
                if prefix not in base_kw.lower():
                    keywords.add(f"{prefix} {base_kw}")

            # Add suffixes
            for suffix in self.SUFFIX_MODIFIERS[:5]:
                if suffix not in base_kw.lower():
                    keywords.add(f"{base_kw} {suffix}")

        return keywords

    def _generate_question_keywords(self) -> Set[str]:
        """Generate question-format keywords."""
        keywords = set()

        # Use themes and brand
        subjects = self._themes[:5] + [self.company_name]

        for subject in subjects:
            for prefix in self.QUESTION_PREFIXES:
                keywords.add(f"{prefix} {subject}")

        return keywords

    def _generate_comparison_keywords(self) -> Set[str]:
        """Generate competitor comparison keywords."""
        keywords = set()

        for competitor in self.competitors[:5]:
            for pattern in self.COMPARISON_PATTERNS:
                kw = pattern.format(brand=self.company_name, competitor=competitor)
                keywords.add(kw)

                # Also try with competitor as main subject
                kw = pattern.format(brand=competitor, competitor=self.company_name)
                keywords.add(kw)

        return keywords

    def _generate_industry_keywords(self) -> Set[str]:
        """Generate industry-specific keywords."""
        keywords = set()

        if not self._industry:
            return keywords

        industry_terms = self.INDUSTRY_KEYWORDS.get(self._industry, [])

        for term in industry_terms:
            # Combine with brand
            keywords.add(f"{self.company_name} {term}")
            keywords.add(f"{term} {self.company_name}")

            # Combine with themes
            for theme in self._themes[:5]:
                keywords.add(f"{theme} {term}")
                keywords.add(f"{term} {theme}")

        return keywords

    def _clean_keywords(self, keywords: Set[str]) -> Set[str]:
        """Clean and normalize keywords."""
        cleaned = set()

        for kw in keywords:
            # Normalize whitespace
            kw = " ".join(kw.split())

            # Convert to lowercase
            kw = kw.lower()

            # Remove very short keywords
            if len(kw) < 3:
                continue

            # Remove very long keywords
            if len(kw) > 80 or len(kw.split()) > 8:
                continue

            # Remove keywords with special characters
            if re.search(r"[^\w\s\-]", kw):
                continue

            cleaned.add(kw)

        return cleaned

    def _prioritize_keywords(self, keywords: List[str]) -> List[str]:
        """Sort keywords by estimated value/relevance."""

        def score_keyword(kw: str) -> int:
            score = 0

            # Brand mentions are high priority
            if self.company_name.lower() in kw.lower():
                score += 10

            # Theme matches
            for theme in self._themes[:5]:
                if theme in kw.lower():
                    score += 3

            # Buying intent indicators
            buying_signals = ["buy", "purchase", "order", "pricing", "cost", "price"]
            for signal in buying_signals:
                if signal in kw.lower():
                    score += 5

            # Moderate length is good (not too short, not too long)
            word_count = len(kw.split())
            if 2 <= word_count <= 4:
                score += 2

            return score

        return sorted(keywords, key=score_keyword, reverse=True)
