#!/usr/bin/env python3
"""Script to trigger domain expansion for advertisers."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.connection import get_async_db_context, init_async_db
from src.database.repositories import AdvertiserRepository
from src.tasks.domain_tasks import (
    discover_competitor_keywords,
    expand_advertiser_keywords,
    update_advertiser_spend_estimates,
)


async def list_advertisers(limit: int = 20):
    """List top advertisers by keyword count."""
    await init_async_db()

    async with get_async_db_context() as session:
        repo = AdvertiserRepository(session)
        advertisers = await repo.list_all(is_active=True, limit=limit)

        print(f"\nTop {limit} Advertisers by Keyword Count:\n")
        print(f"{'ID':<8} {'Domain':<40} {'Keywords':<10} {'Est. Spend':<12}")
        print("-" * 70)

        for adv in advertisers:
            spend = f"${adv.estimated_monthly_spend:.0f}" if adv.estimated_monthly_spend else "N/A"
            print(f"{adv.id:<8} {adv.domain[:38]:<40} {adv.total_keywords_count:<10} {spend:<12}")


async def expand_domain(domain_or_id: str):
    """Trigger expansion for a domain."""
    await init_async_db()

    async with get_async_db_context() as session:
        repo = AdvertiserRepository(session)

        # Try as ID first
        try:
            advertiser_id = int(domain_or_id)
            advertiser = await repo.get_by_id(advertiser_id)
        except ValueError:
            advertiser = await repo.get_by_domain(domain_or_id)

        if not advertiser:
            print(f"Advertiser not found: {domain_or_id}")
            return

        print(f"Queueing expansion for: {advertiser.domain}")

        # Queue the task
        task = expand_advertiser_keywords.delay(advertiser.id)
        print(f"Task ID: {task.id}")
        print("Expansion task queued. Check Celery worker logs for progress.")


async def find_competitors(domain_or_id: str):
    """Find and expand based on competitor keywords."""
    await init_async_db()

    async with get_async_db_context() as session:
        repo = AdvertiserRepository(session)

        try:
            advertiser_id = int(domain_or_id)
            advertiser = await repo.get_by_id(advertiser_id)
        except ValueError:
            advertiser = await repo.get_by_domain(domain_or_id)

        if not advertiser:
            print(f"Advertiser not found: {domain_or_id}")
            return

        # Get competitors
        competitors = await repo.get_competitors(advertiser.id, limit=10)

        print(f"\nCompetitors for {advertiser.domain}:\n")
        print(f"{'Domain':<40} {'Shared Keywords':<15}")
        print("-" * 55)

        for comp, shared in competitors:
            print(f"{comp.domain[:38]:<40} {shared:<15}")

        # Queue competitor discovery
        print(f"\nQueueing competitor keyword discovery...")
        task = discover_competitor_keywords.delay(advertiser.id)
        print(f"Task ID: {task.id}")


async def update_spend(domain_or_id: str = None):
    """Update spend estimates."""
    await init_async_db()

    async with get_async_db_context() as session:
        repo = AdvertiserRepository(session)

        if domain_or_id:
            try:
                advertiser_id = int(domain_or_id)
                advertiser = await repo.get_by_id(advertiser_id)
            except ValueError:
                advertiser = await repo.get_by_domain(domain_or_id)

            if not advertiser:
                print(f"Advertiser not found: {domain_or_id}")
                return

            print(f"Updating spend estimate for: {advertiser.domain}")
            task = update_advertiser_spend_estimates.delay(advertiser.id)
            print(f"Task ID: {task.id}")
        else:
            # Update all
            advertisers = await repo.list_all(is_active=True, limit=50)
            print(f"Queueing spend updates for {len(advertisers)} advertisers...")

            for i, adv in enumerate(advertisers):
                update_advertiser_spend_estimates.apply_async(
                    args=[adv.id],
                    countdown=i * 5,  # Stagger
                )

            print("All updates queued.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Domain expansion utilities")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    list_parser = subparsers.add_parser("list", help="List advertisers")
    list_parser.add_argument("--limit", "-l", type=int, default=20)

    # Expand command
    expand_parser = subparsers.add_parser("expand", help="Expand keywords for domain")
    expand_parser.add_argument("domain", help="Domain or advertiser ID")

    # Competitors command
    comp_parser = subparsers.add_parser("competitors", help="Find competitors")
    comp_parser.add_argument("domain", help="Domain or advertiser ID")

    # Spend command
    spend_parser = subparsers.add_parser("spend", help="Update spend estimates")
    spend_parser.add_argument("domain", nargs="?", help="Domain or advertiser ID (optional)")

    args = parser.parse_args()

    if args.command == "list":
        asyncio.run(list_advertisers(args.limit))
    elif args.command == "expand":
        asyncio.run(expand_domain(args.domain))
    elif args.command == "competitors":
        asyncio.run(find_competitors(args.domain))
    elif args.command == "spend":
        asyncio.run(update_spend(args.domain))
    else:
        parser.print_help()
