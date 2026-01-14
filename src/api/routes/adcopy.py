"""API routes for AI ad copy generation."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    AdCopyGenerateRequest,
    AdCopyImproveRequest,
    GeneratedAdCopyResponse,
)
from src.config import settings
from src.database.connection import get_async_session
from src.database.models import (
    AdAppearance,
    GeneratedAdCopy,
    Keyword,
)
from src.generation.ad_copy_generator import AdCopyGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/adcopy", tags=["adcopy"])

# Initialize generator
ad_generator = AdCopyGenerator()


@router.post(
    "/generate/{keyword_id}",
    response_model=List[GeneratedAdCopyResponse],
    summary="Generate Ad Copies",
    description="Generate AI-powered ad copies for a specific keyword"
)
async def generate_ad_copies(
    keyword_id: int,
    request: AdCopyGenerateRequest,
    save: bool = Query(default=True, description="Save generated copies to database"),
    session: AsyncSession = Depends(get_async_session),
) -> List[GeneratedAdCopyResponse]:
    """Generate ad copies for a keyword using AI."""

    # Check if API key is configured
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI generation not available - ANTHROPIC_API_KEY not configured"
        )

    # Get keyword
    result = await session.execute(
        select(Keyword).where(Keyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()

    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Get competitor ads if requested
    competitor_ads = None
    if request.use_competitor_insights:
        ad_result = await session.execute(
            select(AdAppearance)
            .where(AdAppearance.keyword_id == keyword_id)
            .order_by(AdAppearance.scraped_at.desc())
            .limit(10)
        )
        appearances = ad_result.scalars().all()

        if appearances:
            competitor_ads = [
                {
                    "headline": ad.headline,
                    "description": ad.description,
                    "domain": ad.display_url,
                }
                for ad in appearances
            ]

    try:
        # Generate ad copies
        generated_ads = await ad_generator.generate_ad_copies(
            keyword=keyword.keyword,
            business_name=request.business_name,
            business_description=request.business_description,
            target_audience=request.target_audience,
            tone=request.tone,
            conversion_focus=request.conversion_focus,
            competitor_ads=competitor_ads,
            num_variations=request.num_variations,
            unique_selling_points=request.unique_selling_points,
        )

        responses = []
        for gen_ad in generated_ads:
            # Create response
            ad_response = GeneratedAdCopyResponse(
                keyword_id=keyword_id,
                headline_1=gen_ad.headline_1,
                headline_2=gen_ad.headline_2,
                headline_3=gen_ad.headline_3,
                description_1=gen_ad.description_1,
                description_2=gen_ad.description_2,
                display_path_1=gen_ad.display_path_1,
                display_path_2=gen_ad.display_path_2,
                call_to_action=gen_ad.call_to_action,
                target_audience=gen_ad.target_audience,
                unique_selling_points=gen_ad.unique_selling_points,
                tone=gen_ad.tone,
                conversion_focus=gen_ad.conversion_focus,
                quality_score=gen_ad.quality_score,
                created_at=datetime.utcnow(),
            )

            # Save to database if requested
            if save:
                db_ad = GeneratedAdCopy(
                    keyword_id=keyword_id,
                    headline_1=gen_ad.headline_1,
                    headline_2=gen_ad.headline_2,
                    headline_3=gen_ad.headline_3,
                    description_1=gen_ad.description_1,
                    description_2=gen_ad.description_2,
                    display_path_1=gen_ad.display_path_1,
                    display_path_2=gen_ad.display_path_2,
                    call_to_action=gen_ad.call_to_action,
                    target_audience=gen_ad.target_audience,
                    unique_selling_points=gen_ad.unique_selling_points,
                    tone=gen_ad.tone,
                    conversion_focus=gen_ad.conversion_focus,
                    quality_score=gen_ad.quality_score,
                    competitor_insights_used={"used": request.use_competitor_insights, "count": len(competitor_ads or [])},
                )
                session.add(db_ad)
                await session.flush()
                ad_response.id = db_ad.id

            responses.append(ad_response)

        if save:
            await session.commit()

        logger.info(f"Generated {len(responses)} ad copies for keyword {keyword_id}")
        return responses

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating ad copies: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate ad copies")


@router.get(
    "/{keyword_id}",
    response_model=List[GeneratedAdCopyResponse],
    summary="List Generated Ad Copies",
    description="Get all generated ad copies for a keyword"
)
async def list_generated_copies(
    keyword_id: int,
    favorites_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
) -> List[GeneratedAdCopyResponse]:
    """List generated ad copies for a keyword."""

    query = select(GeneratedAdCopy).where(
        GeneratedAdCopy.keyword_id == keyword_id
    )

    if favorites_only:
        query = query.where(GeneratedAdCopy.is_favorite == True)

    query = query.order_by(GeneratedAdCopy.created_at.desc()).limit(limit)

    result = await session.execute(query)
    copies = result.scalars().all()

    return [GeneratedAdCopyResponse.model_validate(copy) for copy in copies]


@router.post(
    "/improve/{keyword_id}",
    response_model=GeneratedAdCopyResponse,
    summary="Improve Ad Copy",
    description="Improve an existing ad copy using AI"
)
async def improve_ad_copy(
    keyword_id: int,
    request: AdCopyImproveRequest,
    save: bool = Query(default=True),
    session: AsyncSession = Depends(get_async_session),
) -> GeneratedAdCopyResponse:
    """Improve an existing ad copy."""

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI generation not available - ANTHROPIC_API_KEY not configured"
        )

    # Get keyword
    result = await session.execute(
        select(Keyword).where(Keyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()

    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    try:
        improved_ad = await ad_generator.improve_ad_copy(
            original_headline=request.original_headline,
            original_description=request.original_description,
            keyword=keyword.keyword,
            improvement_goal=request.improvement_goal,
        )

        ad_response = GeneratedAdCopyResponse(
            keyword_id=keyword_id,
            headline_1=improved_ad.headline_1,
            headline_2=improved_ad.headline_2,
            headline_3=improved_ad.headline_3,
            description_1=improved_ad.description_1,
            description_2=improved_ad.description_2,
            display_path_1=improved_ad.display_path_1,
            display_path_2=improved_ad.display_path_2,
            call_to_action=improved_ad.call_to_action,
            target_audience=improved_ad.target_audience,
            unique_selling_points=improved_ad.unique_selling_points,
            tone=improved_ad.tone,
            conversion_focus=improved_ad.conversion_focus,
            quality_score=improved_ad.quality_score,
            created_at=datetime.utcnow(),
        )

        if save:
            db_ad = GeneratedAdCopy(
                keyword_id=keyword_id,
                headline_1=improved_ad.headline_1,
                headline_2=improved_ad.headline_2,
                headline_3=improved_ad.headline_3,
                description_1=improved_ad.description_1,
                description_2=improved_ad.description_2,
                display_path_1=improved_ad.display_path_1,
                display_path_2=improved_ad.display_path_2,
                call_to_action=improved_ad.call_to_action,
                target_audience=improved_ad.target_audience,
                unique_selling_points=improved_ad.unique_selling_points,
                tone=improved_ad.tone,
                conversion_focus=improved_ad.conversion_focus,
                quality_score=improved_ad.quality_score,
            )
            session.add(db_ad)
            await session.commit()
            await session.refresh(db_ad)
            ad_response.id = db_ad.id

        return ad_response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error improving ad copy: {e}")
        raise HTTPException(status_code=500, detail="Failed to improve ad copy")


@router.patch(
    "/{ad_copy_id}/favorite",
    response_model=GeneratedAdCopyResponse,
    summary="Toggle Favorite",
    description="Toggle favorite status of a generated ad copy"
)
async def toggle_favorite(
    ad_copy_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> GeneratedAdCopyResponse:
    """Toggle favorite status of an ad copy."""

    result = await session.execute(
        select(GeneratedAdCopy).where(GeneratedAdCopy.id == ad_copy_id)
    )
    ad_copy = result.scalar_one_or_none()

    if not ad_copy:
        raise HTTPException(status_code=404, detail="Ad copy not found")

    ad_copy.is_favorite = not ad_copy.is_favorite
    await session.commit()
    await session.refresh(ad_copy)

    return GeneratedAdCopyResponse.model_validate(ad_copy)


@router.delete(
    "/{ad_copy_id}",
    summary="Delete Ad Copy",
    description="Delete a generated ad copy"
)
async def delete_ad_copy(
    ad_copy_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Delete a generated ad copy."""

    result = await session.execute(
        select(GeneratedAdCopy).where(GeneratedAdCopy.id == ad_copy_id)
    )
    ad_copy = result.scalar_one_or_none()

    if not ad_copy:
        raise HTTPException(status_code=404, detail="Ad copy not found")

    await session.delete(ad_copy)
    await session.commit()

    return {"status": "deleted", "id": ad_copy_id}


@router.get(
    "/tones",
    summary="Get Available Tones",
    description="Get list of available ad copy tones"
)
async def get_tones() -> dict:
    """Get available ad copy tones."""
    return {
        "tones": AdCopyGenerator.TONES,
        "description": "Available tones for ad copy generation"
    }


@router.get(
    "/conversion-focuses",
    summary="Get Conversion Focuses",
    description="Get list of available conversion optimization goals"
)
async def get_conversion_focuses() -> dict:
    """Get available conversion focuses."""
    return {
        "conversion_focuses": AdCopyGenerator.CONVERSION_FOCUSES,
        "description": "Available optimization goals for ad copy generation"
    }
