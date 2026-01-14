"""AI-powered ad copy generator using Claude."""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import anthropic

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAd:
    """Generated ad copy data."""
    headline_1: str
    headline_2: str
    headline_3: Optional[str]
    description_1: str
    description_2: Optional[str]
    display_path_1: Optional[str]
    display_path_2: Optional[str]
    call_to_action: Optional[str]
    target_audience: Optional[str]
    unique_selling_points: List[str]
    tone: str
    conversion_focus: str
    quality_score: int

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "headline_1": self.headline_1,
            "headline_2": self.headline_2,
            "headline_3": self.headline_3,
            "description_1": self.description_1,
            "description_2": self.description_2,
            "display_path_1": self.display_path_1,
            "display_path_2": self.display_path_2,
            "call_to_action": self.call_to_action,
            "target_audience": self.target_audience,
            "unique_selling_points": self.unique_selling_points,
            "tone": self.tone,
            "conversion_focus": self.conversion_focus,
            "quality_score": self.quality_score,
        }


class AdCopyGenerator:
    """Generate high-conversion ad copies using AI."""

    TONES = [
        "professional",
        "friendly",
        "urgent",
        "luxurious",
        "casual",
        "authoritative",
        "playful",
        "trustworthy",
    ]

    CONVERSION_FOCUSES = [
        "clicks",
        "leads",
        "sales",
        "brand_awareness",
        "sign_ups",
        "downloads",
        "calls",
        "store_visits",
    ]

    def __init__(self):
        """Initialize the ad copy generator."""
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set - AI generation will fail")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_ad_copies(
        self,
        keyword: str,
        business_name: Optional[str] = None,
        business_description: Optional[str] = None,
        target_audience: Optional[str] = None,
        tone: str = "professional",
        conversion_focus: str = "clicks",
        competitor_ads: Optional[List[Dict[str, Any]]] = None,
        num_variations: int = 3,
        unique_selling_points: Optional[List[str]] = None,
    ) -> List[GeneratedAd]:
        """
        Generate multiple ad copy variations for a keyword.

        Args:
            keyword: Target keyword for the ad
            business_name: Name of the business
            business_description: Description of what the business offers
            target_audience: Who the ads should target
            tone: Tone of the ad copy (professional, friendly, urgent, etc.)
            conversion_focus: What the ad should optimize for
            competitor_ads: List of competitor ad data for inspiration
            num_variations: Number of ad variations to generate
            unique_selling_points: USPs to highlight

        Returns:
            List of GeneratedAd objects
        """
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        # Build the prompt
        prompt = self._build_generation_prompt(
            keyword=keyword,
            business_name=business_name,
            business_description=business_description,
            target_audience=target_audience,
            tone=tone,
            conversion_focus=conversion_focus,
            competitor_ads=competitor_ads,
            num_variations=num_variations,
            unique_selling_points=unique_selling_points,
        )

        try:
            # Call Claude API
            message = self.client.messages.create(
                model=settings.AI_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Parse the response
            response_text = message.content[0].text
            ads = self._parse_response(response_text, tone, conversion_focus)

            logger.info(f"Generated {len(ads)} ad variations for keyword: {keyword}")
            return ads

        except Exception as e:
            logger.error(f"Error generating ad copies: {e}")
            raise

    def _build_generation_prompt(
        self,
        keyword: str,
        business_name: Optional[str],
        business_description: Optional[str],
        target_audience: Optional[str],
        tone: str,
        conversion_focus: str,
        competitor_ads: Optional[List[Dict[str, Any]]],
        num_variations: int,
        unique_selling_points: Optional[List[str]],
    ) -> str:
        """Build the prompt for ad copy generation."""

        competitor_section = ""
        if competitor_ads:
            competitor_section = "\n## Competitor Ads (for inspiration and differentiation):\n"
            for i, ad in enumerate(competitor_ads[:5], 1):  # Limit to 5 competitors
                competitor_section += f"""
Ad {i}:
- Headline: {ad.get('headline', 'N/A')}
- Description: {ad.get('description', 'N/A')}
- Domain: {ad.get('domain', 'N/A')}
"""

        usps_section = ""
        if unique_selling_points:
            usps_section = f"\n## Unique Selling Points to highlight:\n- " + "\n- ".join(unique_selling_points)

        prompt = f"""You are an expert Google Ads copywriter specializing in high-conversion ad copy.

Generate {num_variations} unique Google Ads variations for the following:

## Target Keyword: {keyword}

## Business Information:
- Business Name: {business_name or '[Not specified - create generic but compelling copy]'}
- Description: {business_description or '[Not specified - infer from keyword]'}
- Target Audience: {target_audience or '[General audience interested in this keyword]'}

## Ad Requirements:
- Tone: {tone}
- Optimization Goal: {conversion_focus}
{usps_section}
{competitor_section}

## Google Ads Character Limits (STRICT):
- Headlines: MAX 30 characters each (you MUST stay under this limit)
- Descriptions: MAX 90 characters each (you MUST stay under this limit)
- Display paths: MAX 15 characters each

## Output Format:
Return a JSON array with {num_variations} ad objects. Each ad should have:
- headline_1: Primary headline (max 30 chars) - most important, include keyword
- headline_2: Secondary headline (max 30 chars) - value proposition
- headline_3: Tertiary headline (max 30 chars) - call to action or differentiator
- description_1: Primary description (max 90 chars) - main selling point
- description_2: Secondary description (max 90 chars) - supporting details/CTA
- display_path_1: URL path hint (max 15 chars)
- display_path_2: URL path hint (max 15 chars)
- call_to_action: Suggested CTA
- target_audience: Who this ad targets
- unique_selling_points: Array of 2-3 USPs used
- quality_score: Self-assessed quality 1-10

## Guidelines for High Conversion:
1. Include the keyword naturally in headline_1
2. Create urgency or scarcity when appropriate
3. Highlight unique benefits over features
4. Use power words: Free, New, Proven, Guaranteed, Exclusive, Limited
5. Include numbers and specifics when possible
6. Make the CTA clear and actionable
7. Differentiate from competitor ads if provided
8. Match the specified tone consistently

Return ONLY the JSON array, no other text. Ensure all character limits are strictly followed."""

        return prompt

    def _parse_response(
        self,
        response_text: str,
        tone: str,
        conversion_focus: str
    ) -> List[GeneratedAd]:
        """Parse the AI response into GeneratedAd objects."""
        ads = []

        try:
            # Extract JSON from response (handle potential markdown code blocks)
            json_str = response_text.strip()
            if json_str.startswith("```"):
                # Remove markdown code blocks
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])

            ad_data_list = json.loads(json_str)

            for ad_data in ad_data_list:
                # Validate and truncate if needed
                ad = GeneratedAd(
                    headline_1=self._truncate(ad_data.get("headline_1", ""), 30),
                    headline_2=self._truncate(ad_data.get("headline_2", ""), 30),
                    headline_3=self._truncate(ad_data.get("headline_3"), 30),
                    description_1=self._truncate(ad_data.get("description_1", ""), 90),
                    description_2=self._truncate(ad_data.get("description_2"), 90),
                    display_path_1=self._truncate(ad_data.get("display_path_1"), 15),
                    display_path_2=self._truncate(ad_data.get("display_path_2"), 15),
                    call_to_action=ad_data.get("call_to_action"),
                    target_audience=ad_data.get("target_audience"),
                    unique_selling_points=ad_data.get("unique_selling_points", []),
                    tone=tone,
                    conversion_focus=conversion_focus,
                    quality_score=min(10, max(1, ad_data.get("quality_score", 7))),
                )
                ads.append(ad)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise ValueError(f"Invalid AI response format: {e}")

        return ads

    def _truncate(self, text: Optional[str], max_length: int) -> Optional[str]:
        """Truncate text to max length."""
        if text is None:
            return None
        return text[:max_length] if len(text) > max_length else text

    async def improve_ad_copy(
        self,
        original_headline: str,
        original_description: str,
        keyword: str,
        improvement_goal: str = "higher_ctr",
    ) -> GeneratedAd:
        """
        Improve an existing ad copy.

        Args:
            original_headline: The original headline
            original_description: The original description
            keyword: Target keyword
            improvement_goal: What to improve (higher_ctr, more_conversions, better_quality_score)

        Returns:
            Improved GeneratedAd
        """
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        prompt = f"""You are an expert Google Ads copywriter. Improve this ad copy for better {improvement_goal}.

Original Ad:
- Headline: {original_headline}
- Description: {original_description}
- Keyword: {keyword}

Improvement Goal: {improvement_goal}

Create ONE improved version following Google Ads limits:
- Headlines: MAX 30 characters
- Descriptions: MAX 90 characters

Return a JSON object with:
- headline_1, headline_2, headline_3 (max 30 chars each)
- description_1, description_2 (max 90 chars each)
- display_path_1, display_path_2 (max 15 chars each)
- call_to_action
- target_audience
- unique_selling_points (array)
- quality_score (1-10)
- improvement_notes (what was improved and why)

Return ONLY the JSON object."""

        try:
            message = self.client.messages.create(
                model=settings.AI_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text
            json_str = response_text.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])

            ad_data = json.loads(json_str)

            return GeneratedAd(
                headline_1=self._truncate(ad_data.get("headline_1", ""), 30),
                headline_2=self._truncate(ad_data.get("headline_2", ""), 30),
                headline_3=self._truncate(ad_data.get("headline_3"), 30),
                description_1=self._truncate(ad_data.get("description_1", ""), 90),
                description_2=self._truncate(ad_data.get("description_2"), 90),
                display_path_1=self._truncate(ad_data.get("display_path_1"), 15),
                display_path_2=self._truncate(ad_data.get("display_path_2"), 15),
                call_to_action=ad_data.get("call_to_action"),
                target_audience=ad_data.get("target_audience"),
                unique_selling_points=ad_data.get("unique_selling_points", []),
                tone="professional",
                conversion_focus=improvement_goal,
                quality_score=min(10, max(1, ad_data.get("quality_score", 7))),
            )

        except Exception as e:
            logger.error(f"Error improving ad copy: {e}")
            raise
