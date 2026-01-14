#!/usr/bin/env python3
"""Script to load initial seed keywords into the database."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.connection import get_async_db_context, init_async_db
from src.database.models import KeywordSource
from src.database.repositories import KeywordRepository


# Sample seed keywords by category
SEED_KEYWORDS = {
    "saas": [
        "project management software",
        "crm software",
        "email marketing tools",
        "accounting software",
        "hr software",
        "helpdesk software",
        "sales automation",
        "marketing automation platform",
        "business intelligence tools",
        "collaboration software",
    ],
    "ecommerce": [
        "buy shoes online",
        "best laptop deals",
        "cheap flights",
        "hotel booking",
        "car rental",
        "online shopping",
        "furniture store",
        "electronics store",
        "clothing store online",
        "home decor shop",
    ],
    "services": [
        "plumber near me",
        "electrician services",
        "house cleaning service",
        "lawn care services",
        "pest control",
        "moving company",
        "storage units",
        "car repair shop",
        "roof repair",
        "hvac service",
    ],
    "legal": [
        "personal injury lawyer",
        "divorce attorney",
        "criminal defense lawyer",
        "immigration lawyer",
        "business lawyer",
        "real estate attorney",
        "tax attorney",
        "bankruptcy lawyer",
        "employment lawyer",
        "estate planning attorney",
    ],
    "finance": [
        "business loans",
        "personal loans",
        "mortgage rates",
        "car insurance quotes",
        "life insurance",
        "credit cards",
        "investment advisor",
        "financial planning",
        "tax preparation",
        "debt consolidation",
    ],
    "health": [
        "dentist near me",
        "urgent care",
        "therapy services",
        "dermatologist",
        "chiropractor",
        "physical therapy",
        "weight loss programs",
        "addiction treatment",
        "mental health services",
        "pediatrician",
    ],
}


async def seed_keywords(categories: list[str] = None, dry_run: bool = False):
    """
    Seed the database with initial keywords.

    Args:
        categories: List of categories to seed (None = all)
        dry_run: If True, only print what would be added
    """
    print("Initializing database...")
    await init_async_db()

    categories_to_seed = categories or list(SEED_KEYWORDS.keys())

    total_added = 0
    total_skipped = 0

    async with get_async_db_context() as session:
        repo = KeywordRepository(session)

        for category in categories_to_seed:
            if category not in SEED_KEYWORDS:
                print(f"Unknown category: {category}")
                continue

            keywords = SEED_KEYWORDS[category]
            print(f"\n{'[DRY RUN] ' if dry_run else ''}Seeding {len(keywords)} keywords for category: {category}")

            for kw in keywords:
                if dry_run:
                    print(f"  Would add: {kw}")
                    total_added += 1
                    continue

                _, was_created = await repo.get_or_create(
                    kw,
                    source=KeywordSource.SEED,
                    category=category,
                    crawl_priority=5,
                )

                if was_created:
                    print(f"  Added: {kw}")
                    total_added += 1
                else:
                    print(f"  Skipped (exists): {kw}")
                    total_skipped += 1

        if not dry_run:
            await session.commit()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Added: {total_added}")
    print(f"  Skipped: {total_skipped}")
    print(f"  Total: {total_added + total_skipped}")


async def add_custom_keywords(keywords: list[str], category: str = None):
    """Add custom keywords from command line."""
    await init_async_db()

    async with get_async_db_context() as session:
        repo = KeywordRepository(session)

        added = 0
        for kw in keywords:
            _, was_created = await repo.get_or_create(
                kw,
                source=KeywordSource.SEED,
                category=category,
            )
            if was_created:
                print(f"Added: {kw}")
                added += 1
            else:
                print(f"Exists: {kw}")

        await session.commit()
        print(f"\nAdded {added} new keywords")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed keywords into the database")
    parser.add_argument(
        "--categories",
        "-c",
        nargs="+",
        help="Categories to seed (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be added without making changes",
    )
    parser.add_argument(
        "--keywords",
        "-k",
        nargs="+",
        help="Custom keywords to add",
    )
    parser.add_argument(
        "--category",
        help="Category for custom keywords",
    )
    parser.add_argument(
        "--list-categories",
        "-l",
        action="store_true",
        help="List available categories",
    )

    args = parser.parse_args()

    if args.list_categories:
        print("Available categories:")
        for cat, keywords in SEED_KEYWORDS.items():
            print(f"  {cat}: {len(keywords)} keywords")
        sys.exit(0)

    if args.keywords:
        asyncio.run(add_custom_keywords(args.keywords, args.category))
    else:
        asyncio.run(seed_keywords(args.categories, args.dry_run))
