#!/usr/bin/env python3
"""
Script to update article frontmatter:
1. Remove reviewer fields
2. Add reviewer_specialty based on category
3. Add subcategory and subcategory_slug by matching article content against subcategory keywords
"""

import os
import json
import re
from pathlib import Path
from collections import defaultdict

# Category to specialty mapping
CATEGORY_SPECIALTY_MAP = {
    "Cosmetic Dentistry": "Cosmetic Dentistry",
    "Orthodontics": "Orthodontics",
    "Dental Implants": "Implant Dentistry",
    "Periodontics": "Periodontics",
    "Endodontics": "Endodontics",
    "Oral Surgery": "Oral and Maxillofacial Surgery",
    "Pediatric Dentistry": "Pediatric Dentistry",
    "Prosthodontics": "Prosthodontics",
    "General Dentistry": "General Dentistry",
    "Preventive Care": "Preventive Dentistry",
    "Emergency Dentistry": "Emergency Dental Care",
    "TMJ & Sleep Dentistry": "Orofacial Pain and TMJ",
    "Dental Technology": "General Dentistry",
    "Dental Anxiety & Sedation": "Sedation Dentistry",
    "Holistic & Alternative Dentistry": "Holistic Dentistry",
    "Geriatric Dentistry": "Geriatric Dental Care",
    "Sports Dentistry": "Sports Dentistry",
    "Dental Nutrition": "Preventive Dentistry",
    "Oral Health Conditions": "General Dentistry",
    "Dental Practice & Insurance": "General Dentistry",
}

REVIEWER_FIELDS = {"reviewer_name", "reviewer_credentials", "reviewer_practice", "reviewer_location", "reviewer_url"}

def load_subcategories(json_path):
    """Load subcategories from JSON file."""
    with open(json_path, 'r') as f:
        return json.load(f)

def parse_frontmatter(content):
    """
    Parse YAML frontmatter from markdown content.
    Returns (frontmatter_dict, body_content, original_frontmatter_text)
    """
    if not content.startswith("---"):
        return {}, content, ""

    # Find the end of frontmatter
    lines = content.split('\n')
    fm_end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break

    if fm_end == -1:
        return {}, content, ""

    fm_lines = lines[1:fm_end]
    body_lines = lines[fm_end + 1:]
    original_fm_text = '\n'.join(fm_lines)

    # Parse YAML frontmatter
    fm_dict = {}
    current_key = None
    current_list = None

    for line in fm_lines:
        if line.strip() == "":
            continue

        # Check if this is a list item (starts with "  - ")
        if line.startswith("  - "):
            if current_list is None:
                current_list = []
            # Parse list item as dict
            item_content = line[4:].strip()
            if ':' in item_content:
                key, value = item_content.split(':', 1)
                if current_list and isinstance(current_list[-1], dict):
                    current_list[-1][key.strip()] = value.strip()
                else:
                    current_list.append({key.strip(): value.strip()})
            else:
                current_list.append(item_content)
        elif line.startswith("    "):
            # Continuation of a list item or nested value
            if current_list and isinstance(current_list[-1], dict):
                item_content = line[4:].strip()
                if ':' in item_content:
                    key, value = item_content.split(':', 1)
                    current_list[-1][key.strip()] = value.strip()
        else:
            # New key-value pair
            if current_list is not None and current_key:
                fm_dict[current_key] = current_list
            current_list = None

            if ':' in line:
                key, value = line.split(':', 1)
                fm_dict[key.strip()] = value.strip()
                current_key = key.strip()

    # Add final list if exists
    if current_list is not None and current_key:
        fm_dict[current_key] = current_list

    body = '\n'.join(body_lines)

    return fm_dict, body, original_fm_text

def find_matching_subcategory(category_key, article_content, article_title, subcategories):
    """
    Match article to a subcategory by searching keywords in content and title.
    Returns (subcategory_name, subcategory_slug) or (None, None) if no match.
    """
    if category_key not in subcategories:
        return None, None

    category_data = subcategories[category_key]
    search_text = (article_title + " " + article_content).lower()

    best_match = None
    best_score = 0

    for subcat in category_data.get("subcategories", []):
        keywords = subcat.get("keywords", [])
        score = 0
        for keyword in keywords:
            # Count keyword matches (case-insensitive)
            count = search_text.count(keyword.lower())
            score += count

        if score > best_score:
            best_score = score
            best_match = subcat

    if best_match:
        return best_match["name"], best_match["slug"]

    # Default to first subcategory if no keywords matched
    if category_data.get("subcategories"):
        default = category_data["subcategories"][0]
        return default["name"], default["slug"]

    return None, None

def write_frontmatter(fm_dict, body):
    """
    Write frontmatter dict back to YAML format with proper structure.
    """
    lines = ["---"]

    # Preserve order: simple fields first, then complex ones
    simple_fields = []
    complex_fields = {}

    for key, value in fm_dict.items():
        if isinstance(value, list):
            complex_fields[key] = value
        else:
            simple_fields.append((key, value))

    # Write simple fields
    for key, value in simple_fields:
        lines.append(f"{key}: {value}")

    # Write complex fields (lists)
    for key, items in complex_fields.items():
        lines.append(f"{key}:")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for subkey, subvalue in item.items():
                        lines.append(f"  - {subkey}: {subvalue}")
                else:
                    lines.append(f"  - {item}")

    lines.append("---")

    return '\n'.join(lines) + '\n' + body

def process_articles(articles_dir, subcategories_path):
    """
    Process all article files in the directory.
    """
    subcategories = load_subcategories(subcategories_path)

    # Get all markdown files
    articles_path = Path(articles_dir)
    md_files = sorted(articles_path.glob("*.md"))

    stats = {
        'total_files': len(md_files),
        'files_updated': 0,
        'reviewer_fields_removed': 0,
        'subcategory_distribution': defaultdict(int),
        'errors': []
    }

    for idx, md_file in enumerate(md_files, 1):
        try:
            if idx % 100 == 0:
                print(f"Processing {idx}/{len(md_files)}...")

            # Read file
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse frontmatter and body
            fm_dict, body, original_fm = parse_frontmatter(content)

            if not fm_dict:
                continue

            original_fm_dict = fm_dict.copy()

            # Get category for specialty mapping
            category = fm_dict.get('category', 'General Dentistry')
            category_slug = fm_dict.get('category_slug', 'general-dentistry')

            # Add reviewer_specialty based on category
            specialty = CATEGORY_SPECIALTY_MAP.get(category, "General Dentistry")
            fm_dict['reviewer_specialty'] = specialty

            # Remove reviewer fields
            removed_count = 0
            for field in REVIEWER_FIELDS:
                if field in fm_dict:
                    del fm_dict[field]
                    removed_count += 1

            if removed_count > 0:
                stats['reviewer_fields_removed'] += removed_count

            # Find matching subcategory
            article_title = fm_dict.get('title', md_file.stem)
            subcat_name, subcat_slug = find_matching_subcategory(
                category_slug,
                body[:2000],  # Use first 2000 chars of body to avoid processing entire content
                article_title,
                subcategories
            )

            if subcat_name:
                fm_dict['subcategory'] = subcat_name
                fm_dict['subcategory_slug'] = subcat_slug
                stats['subcategory_distribution'][f"{category_slug}/{subcat_slug}"] += 1

            # Write back to file if changes were made
            if fm_dict != original_fm_dict:
                updated_content = write_frontmatter(fm_dict, body)
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                stats['files_updated'] += 1

        except Exception as e:
            stats['errors'].append(f"{md_file.name}: {str(e)}")

    return stats

def print_stats(stats):
    """Print summary statistics."""
    print("\n" + "="*70)
    print("FRONTMATTER UPDATE SUMMARY")
    print("="*70)
    print(f"Total files processed: {stats['total_files']}")
    print(f"Files updated: {stats['files_updated']}")
    print(f"Reviewer fields removed: {stats['reviewer_fields_removed']}")
    print(f"\nSubcategory Distribution (Top 20):")
    print("-" * 70)

    sorted_subcats = sorted(
        stats['subcategory_distribution'].items(),
        key=lambda x: x[1],
        reverse=True
    )

    for subcat, count in sorted_subcats[:20]:
        print(f"  {subcat}: {count}")

    if len(sorted_subcats) > 20:
        print(f"  ... and {len(sorted_subcats) - 20} more")

    print(f"\nTotal unique subcategories: {len(stats['subcategory_distribution'])}")

    if stats['errors']:
        print(f"\nErrors ({len(stats['errors'])}):")
        for error in stats['errors'][:10]:
            print(f"  {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    print("="*70)

if __name__ == "__main__":
    articles_dir = "/sessions/loving-gifted-franklin/dentalpedia-push/content/articles"
    subcategories_path = "/sessions/loving-gifted-franklin/dentalpedia-push/data/subcategories.json"

    stats = process_articles(articles_dir, subcategories_path)
    print_stats(stats)
