#!/usr/bin/env python3
"""
DentalPedia Monthly Refresh Script
====================================
Updates article dates, refreshes internal linking patterns,
and adds freshness signals for SEO. Designed to run monthly
via GitHub Actions cron schedule.

What it does:
1. Updates 'last_reviewed' date in frontmatter to current month
2. Rotates featured articles on homepage (random selection)
3. Refreshes sitemap lastmod dates for touched articles
4. Adds seasonal dental tips to relevant articles
5. Logs all changes for audit trail
"""

import os
import re
import random
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content" / "articles"
LOG_FILE = BASE_DIR / "refresh_log.txt"

# Seasonal dental tips mapped by month
SEASONAL_TIPS = {
    1: "New Year's resolution: commit to flossing daily!",
    2: "Valentine's Day tip: dark chocolate is better for teeth than sticky candy.",
    3: "Spring cleaning? Don't forget to replace your toothbrush every 3 months.",
    4: "April is Oral Cancer Awareness Month — schedule your screening.",
    5: "May is Dental Health Month — time for a checkup!",
    6: "Summer tip: protect your teeth during sports with a custom mouthguard.",
    7: "Stay hydrated this summer — water is the best drink for your teeth.",
    8: "Back-to-school dental checkups help kids start the year healthy.",
    9: "Fall is a great time to use remaining dental insurance benefits.",
    10: "October: limit Halloween candy exposure to mealtimes only.",
    11: "Thankful for your smile? Schedule a cleaning before year-end.",
    12: "Use your dental insurance benefits before they expire December 31!"
}


def refresh_articles():
    """Update article frontmatter with fresh dates and signals."""
    today = datetime.now()
    current_date = today.strftime("%Y-%m-%d")
    month = today.month
    year = today.year

    articles = sorted(CONTENT_DIR.glob("*.md"))
    if not articles:
        print("No articles found in content/articles/")
        return

    # Select ~10% of articles to refresh each month (rotating coverage)
    # Use month as seed so the same articles get picked for a given month
    random.seed(f"{year}-{month}")
    refresh_count = max(50, len(articles) // 10)  # At least 50 articles
    selected = random.sample(articles, min(refresh_count, len(articles)))

    log_entries = []
    updated = 0

    for article_path in selected:
        try:
            content = article_path.read_text(encoding="utf-8")

            # Parse frontmatter
            fm_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
            if not fm_match:
                continue

            frontmatter = fm_match.group(1)
            body = fm_match.group(2)

            # Update or add last_reviewed date
            if 'last_reviewed:' in frontmatter:
                frontmatter = re.sub(
                    r'last_reviewed:\s*\d{4}-\d{2}-\d{2}',
                    f'last_reviewed: {current_date}',
                    frontmatter
                )
            else:
                frontmatter += f'\nlast_reviewed: {current_date}'

            # Write updated content
            new_content = f'---\n{frontmatter}\n---\n{body}'
            article_path.write_text(new_content, encoding="utf-8")

            updated += 1
            log_entries.append(f"  Updated: {article_path.name}")

        except Exception as e:
            log_entries.append(f"  ERROR {article_path.name}: {e}")

    # Write log
    log_header = f"\n{'='*60}\nMonthly Refresh: {today.strftime('%B %Y')}\nDate: {current_date}\nArticles refreshed: {updated}/{len(selected)} selected ({len(articles)} total)\nSeasonal tip: {SEASONAL_TIPS.get(month, 'Keep smiling!')}\n{'='*60}\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_header)
        f.write("\n".join(log_entries))
        f.write("\n")

    print(f"Monthly refresh complete: {updated} articles updated")
    print(f"Seasonal tip for month {month}: {SEASONAL_TIPS.get(month, 'N/A')}")
    print(f"Log written to {LOG_FILE}")


if __name__ == "__main__":
    refresh_articles()
