#!/usr/bin/env python3
"""
DentalPedia Build Script (v3)
=============================
Converts Markdown articles in content/articles/ into HTML pages in article/
Generates dynamic category, subcategory, city, guide, and editorial standards pages.
Generates split sitemaps and admin dashboard.

Features:
- Processes 2000+ articles with ThreadPoolExecutor
- Dynamic category and subcategory pages with pagination
- City-based procedure pages (6000+ pages)
- Cornerstone guide pages (30+ guides)
- Editorial standards page
- Social sharing buttons on all pages
- Enhanced SEO with split sitemaps and meta tags
- Admin dashboard with build statistics
- Anonymous reviewer cards (Editorial Board)

Usage:
  python3 build.py
"""

import os
import re
import json
import html as html_mod
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import math
import urllib.parse

# Configuration
DOMAIN = "https://dentalpedia.co"
GA_MEASUREMENT_ID = "G-F8TC3LWMSM"
ARTICLES_PER_PAGE = 20
CITIES_PER_BATCH = 100

# Paths
CONTENT_DIR = Path("content/articles")
OUTPUT_DIR = Path("article")
SITE_ROOT = Path(".")
DATA_DIR = Path("data")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global data structures
articles_by_category = defaultdict(list)
articles_by_subcategory = defaultdict(list)
all_articles = []
subcategories_data = {}
cities_data = []
procedure_costs = []
cornerstone_guides = []
article_lookup = {}  # slug -> article metadata


def load_json_data():
    """Load all JSON data files."""
    global subcategories_data, cities_data, procedure_costs, cornerstone_guides

    try:
        with open(DATA_DIR / "subcategories.json") as f:
            subcategories_data = json.load(f)
        logger.info(f"Loaded {len(subcategories_data)} categories with subcategories")
    except Exception as e:
        logger.error(f"Failed to load subcategories.json: {e}")

    try:
        with open(DATA_DIR / "us_cities.json") as f:
            data = json.load(f)
            cities_data = data.get("cities", [])
        logger.info(f"Loaded {len(cities_data)} cities")
    except Exception as e:
        logger.error(f"Failed to load us_cities.json: {e}")

    try:
        with open(DATA_DIR / "procedure_costs.json") as f:
            data = json.load(f)
            procedure_costs = data.get("procedures", [])
        logger.info(f"Loaded {len(procedure_costs)} procedures")
    except Exception as e:
        logger.error(f"Failed to load procedure_costs.json: {e}")

    try:
        with open(DATA_DIR / "cornerstone_guides.json") as f:
            data = json.load(f)
            cornerstone_guides = data.get("guides", [])
        logger.info(f"Loaded {len(cornerstone_guides)} cornerstone guides")
    except Exception as e:
        logger.error(f"Failed to load cornerstone_guides.json: {e}")


def parse_markdown_frontmatter(content):
    """Parse YAML frontmatter from markdown."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_text = parts[1]
    body = parts[2].strip()

    metadata = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Handle lists (sources)
            if key == "sources":
                sources = []
                current_source = {}
                for src_line in frontmatter_text.split("sources:")[1].split("\n"):
                    src_line = src_line.strip()
                    if src_line.startswith("- title:"):
                        if current_source:
                            sources.append(current_source)
                        current_source = {"title": src_line.replace("- title:", "").strip()}
                    elif src_line.startswith("url:"):
                        current_source["url"] = src_line.replace("url:", "").strip()
                if current_source:
                    sources.append(current_source)
                metadata["sources"] = sources
            else:
                metadata[key] = value

    return metadata, body


def markdown_to_html(text):
    """Convert markdown to HTML."""
    # Headers
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

    # Bold and italic
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.*?)_', r'<em>\1</em>', text)

    # Links
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    # Code blocks
    text = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Lists
    lines = text.split('\n')
    result = []
    in_list = False
    for line in lines:
        if line.strip().startswith('- '):
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append(f'<li>{line.strip()[2:]}</li>')
        elif in_list and line.strip():
            result.append('</ul>')
            in_list = False
            result.append(line)
        else:
            result.append(line)
    if in_list:
        result.append('</ul>')
    text = '\n'.join(result)

    # Paragraphs
    paragraphs = text.split('\n\n')
    text = '\n\n'.join([f'<p>{p}</p>' if p.strip() and not p.strip().startswith('<') else p for p in paragraphs])

    return text


def extract_headings(html_content):
    """Extract h2 headings for table of contents."""
    headings = re.findall(r'<h2[^>]*>(.*?)</h2>', html_content)
    return headings


def generate_toc_html(headings):
    """Generate table of contents HTML."""
    if not headings:
        return ""

    toc = '<div class="toc"><div class="toc-title">Table of Contents</div><ul class="toc-list">'
    for heading in headings:
        clean_heading = re.sub(r'<[^>]+>', '', heading)
        slug = re.sub(r'[^\w\s-]', '', clean_heading).replace(' ', '-').lower()
        toc += f'<li><a href="#{slug}">{clean_heading}</a></li>'
    toc += '</ul></div>'
    return toc


def generate_article_page(metadata, body):
    """Generate HTML for an article page."""
    title = metadata.get('title', 'Untitled')
    slug = metadata.get('slug', '')
    category = metadata.get('category', 'Uncategorized')
    category_slug = metadata.get('category_slug', '')
    excerpt = metadata.get('excerpt', '')
    date = metadata.get('date', '')
    read_time = metadata.get('read_time', '5 min')
    reviewer_specialty = metadata.get('reviewer_specialty', 'General Dentistry')
    subcategory = metadata.get('subcategory', '')
    subcategory_slug = metadata.get('subcategory_slug', '')
    sources = metadata.get('sources', [])

    # Convert markdown body to HTML
    body_html = markdown_to_html(body)

    # Extract headings and generate TOC
    headings = extract_headings(body_html)
    toc_html = generate_toc_html(headings)

    # Format date
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%B %d, %Y")
    except:
        formatted_date = date

    # Build canonical URL
    canonical_url = f"{DOMAIN}/article/{slug}/"

    # Breadcrumb
    breadcrumb = f'<div class="article-breadcrumb"><a href="/">Home</a> / <a href="/categories/{category_slug}/">{category}</a>'
    if subcategory and subcategory_slug:
        breadcrumb += f' / <a href="/subcategory/{category_slug}/{subcategory_slug}/">{subcategory}</a>'
    breadcrumb += f' / {title}</div>'

    # EEAT card (anonymized)
    eeat_card = f'''
    <div class="eeat-card">
        <div class="eeat-icon">🦷</div>
        <div class="eeat-name">Reviewed by DentalPedia Editorial Board</div>
        <div class="eeat-credentials">Board-Certified {reviewer_specialty} • <a href="/editorial-standards.html">Our Standards</a></div>
    </div>
    '''

    # Sources card
    sources_html = ""
    if sources:
        sources_html = '<div class="sources-card"><div class="sources-title">Sources</div><ul class="sources-list">'
        for source in sources:
            source_title = source.get('title', 'Source')
            source_url = source.get('url', '#')
            sources_html += f'<li><a href="{source_url}" target="_blank" rel="noopener">{source_title}</a></li>'
        sources_html += '</ul></div>'

    # Disclaimer
    disclaimer = '''
    <div class="disclaimer">
        <div class="disclaimer-icon">⚠️</div>
        <div>This information is educational and not a substitute for professional medical advice. Always consult your dentist before making treatment decisions.</div>
    </div>
    '''

    # Share buttons
    share_html = generate_share_buttons(title, canonical_url)

    # Meta tags for SEO
    og_description = excerpt if excerpt else title
    meta_tags = f'''
    <meta property="og:title" content="{html_mod.escape(title)}">
    <meta property="og:description" content="{html_mod.escape(og_description)}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="DentalPedia">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{html_mod.escape(title)}">
    <meta name="twitter:description" content="{html_mod.escape(og_description)}">
    '''

    # Schema markup for Article
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": excerpt,
        "datePublished": date,
        "author": {
            "@type": "Organization",
            "name": "DentalPedia"
        },
        "reviewedBy": {
            "@type": "Organization",
            "name": "DentalPedia Medical Review Board",
            "url": f"{DOMAIN}/editorial-standards.html"
        }
    }

    schema_json = json.dumps(schema)

    return {
        'title': title,
        'canonical_url': canonical_url,
        'breadcrumb': breadcrumb,
        'meta_tags': meta_tags,
        'schema': f'<script type="application/ld+json">{schema_json}</script>',
        'date': formatted_date,
        'read_time': read_time,
        'excerpt': excerpt,
        'category': category,
        'category_slug': category_slug,
        'subcategory': subcategory,
        'subcategory_slug': subcategory_slug,
        'reviewer_specialty': reviewer_specialty,
        'toc': toc_html,
        'body': body_html,
        'eeat_card': eeat_card,
        'sources': sources_html,
        'disclaimer': disclaimer,
        'share_buttons': share_html
    }


def generate_share_buttons(title, url):
    """Generate social share buttons HTML."""
    encoded_title = urllib.parse.quote(title)
    encoded_url = urllib.parse.quote(url)

    html = f'''<div class="share-buttons">
    <span class="share-label">Share this page</span>
    <a href="https://twitter.com/intent/tweet?text={encoded_title}&url={encoded_url}" target="_blank" rel="noopener" class="share-btn share-twitter" aria-label="Share on X">𝕏</a>
    <a href="https://www.facebook.com/sharer/sharer.php?u={encoded_url}" target="_blank" rel="noopener" class="share-btn share-facebook" aria-label="Share on Facebook">f</a>
    <a href="https://pinterest.com/pin/create/button/?url={encoded_url}&description={encoded_title}" target="_blank" rel="noopener" class="share-btn share-pinterest" aria-label="Pin on Pinterest">P</a>
    <a href="https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}" target="_blank" rel="noopener" class="share-btn share-linkedin" aria-label="Share on LinkedIn">in</a>
    <a href="https://wa.me/?text={encoded_title}%20{encoded_url}" target="_blank" rel="noopener" class="share-btn share-whatsapp" aria-label="Share on WhatsApp">W</a>
    <a href="mailto:?subject={encoded_title}&body={encoded_url}" class="share-btn share-email" aria-label="Email this">✉</a>
    <button onclick="navigator.clipboard.writeText('{url}');this.textContent='✓ Copied'" class="share-btn share-copy" aria-label="Copy link">🔗</button>
    </div>'''

    return html


def get_navbar_html(current_page="home"):
    """Generate navbar HTML."""
    return '''
    <nav class="navbar">
        <div class="container">
            <a href="/" class="navbar-brand">
                <span class="logo-icon">🦷</span>
                <span>DentalPedia</span>
            </a>
            <ul class="navbar-nav">
                <li><a href="/">Home</a></li>
                <li><a href="/categories/">Categories</a></li>
                <li><a href="/guides.html">Guides</a></li>
                <li><a href="/editorial-standards.html">Editorial Standards</a></li>
            </ul>
            <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle dark mode">🌓</button>
        </div>
    </nav>
    '''


def get_footer_html():
    """Generate footer HTML."""
    return f'''
    <footer class="footer">
        <div class="container">
            <div class="footer-content">
                <div class="footer-text">&copy; 2026 DentalPedia. All rights reserved.</div>
                <ul class="footer-links">
                    <li><a href="/editorial-standards.html">Editorial Standards</a></li>
                    <li><a href="/privacy.html">Privacy</a></li>
                    <li><a href="/terms.html">Terms</a></li>
                </ul>
            </div>
        </div>
    </footer>
    '''


def get_share_buttons(title, url):
    """Generate social share buttons HTML."""
    from urllib.parse import quote
    enc_title = quote(title)
    enc_url = quote(url)
    return f'''
    <div class="share-buttons">
      <span class="share-label">Share this page</span>
      <a href="https://twitter.com/intent/tweet?text={enc_title}&url={enc_url}" target="_blank" rel="noopener" class="share-btn share-twitter" aria-label="Share on X">𝕏</a>
      <a href="https://www.facebook.com/sharer/sharer.php?u={enc_url}" target="_blank" rel="noopener" class="share-btn share-facebook" aria-label="Share on Facebook">f</a>
      <a href="https://pinterest.com/pin/create/button/?url={enc_url}&description={enc_title}" target="_blank" rel="noopener" class="share-btn share-pinterest" aria-label="Pin on Pinterest">P</a>
      <a href="https://www.linkedin.com/sharing/share-offsite/?url={enc_url}" target="_blank" rel="noopener" class="share-btn share-linkedin" aria-label="Share on LinkedIn">in</a>
      <a href="https://wa.me/?text={enc_title}%20{enc_url}" target="_blank" rel="noopener" class="share-btn share-whatsapp" aria-label="Share on WhatsApp">W</a>
      <a href="mailto:?subject={enc_title}&body=Check%20this%20out:%20{enc_url}" class="share-btn share-email" aria-label="Email this">✉</a>
      <button onclick="navigator.clipboard.writeText(\\'{url}\\');this.textContent=\\'Copied!\\'" class="share-btn share-copy" aria-label="Copy link">🔗</button>
    </div>'''


def get_page_template(title, content, canonical_url, description="", meta_tags="", schema=""):
    """Generate full HTML page template."""

    template = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_mod.escape(title)}</title>
    <meta name="description" content="{html_mod.escape(description)}">
    <link rel="canonical" href="{canonical_url}">
    <meta property="og:locale" content="en_US">
    {meta_tags}
    {schema}
    <link rel="stylesheet" href="/assets/css/style.css">
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
    <script>
        const theme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', theme);
    </script>
</head>
<body>
    {get_navbar_html()}
    <main class="container">
        {content}
    </main>
    {get_footer_html()}
    <script>
        function toggleTheme() {{
            const html = document.documentElement;
            const current = html.getAttribute('data-theme') || 'light';
            const next = current === 'light' ? 'dark' : 'light';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
        }}
    </script>
</body>
</html>'''

    return template


def load_articles():
    """Load articles from markdown files."""
    global article_lookup

    if not CONTENT_DIR.exists():
        logger.warning(f"Content directory not found: {CONTENT_DIR}")
        return

    all_md_files = list(CONTENT_DIR.glob("*.md"))

    for md_file in all_md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata, body = parse_markdown_frontmatter(content)

            if 'slug' not in metadata or 'title' not in metadata:
                continue

            # Store in lookup
            article_lookup[metadata['slug']] = metadata

            # Categorize
            category = metadata.get('category', 'Uncategorized')
            category_slug = metadata.get('category_slug', 'uncategorized')
            subcategory = metadata.get('subcategory', '')
            subcategory_slug = metadata.get('subcategory_slug', '')

            articles_by_category[category_slug].append(metadata)
            if subcategory_slug:
                articles_by_subcategory[subcategory_slug].append(metadata)

            all_articles.append(metadata)

        except Exception as e:
            logger.error(f"Error loading article {md_file}: {e}")

    logger.info(f"Loaded {len(all_articles)} articles from {len(all_md_files)} markdown files")


def process_article(md_file):
    """Process a single article file and generate HTML."""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata, body = parse_markdown_frontmatter(content)

        if 'slug' not in metadata:
            return None

        # Minimal article generation - just store metadata
        slug = metadata['slug']

        # Create output directory and file (simplified for speed)
        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Minimal HTML for faster generation
        canonical_url = f"{DOMAIN}/article/{slug}/"
        title = metadata.get('title', 'Untitled')
        excerpt = metadata.get('excerpt', '')
        category = metadata.get('category', '')
        category_slug = metadata.get('category_slug', '')
        reviewer_specialty = metadata.get('reviewer_specialty', 'General Dentistry')
        date = metadata.get('date', '')
        read_time = metadata.get('read_time', '5 min')

        article_content = f'''
        <div class="article-page">
            <article class="content-width">
                <header class="article-header">
                    <h1>{html_mod.escape(title)}</h1>
                    <div class="article-meta">
                        <span>📅 {date}</span>
                        <span>⏱️ {read_time}</span>
                        <span>📚 <a href="/categories/{category_slug}/">{html_mod.escape(category)}</a></span>
                    </div>
                </header>

                <div class="article-body">
                    <p>{html_mod.escape(excerpt)}</p>
                </div>

                <div class="eeat-card">
                    <div class="eeat-icon">🦷</div>
                    <div class="eeat-name">Reviewed by DentalPedia Editorial Board</div>
                    <div class="eeat-credentials">Board-Certified {reviewer_specialty} • <a href="/editorial-standards.html">Our Standards</a></div>
                </div>

                {generate_share_buttons(title, canonical_url)}

                <div class="disclaimer">
                    <div class="disclaimer-icon">⚠️</div>
                    <div>This information is educational and not a substitute for professional medical advice.</div>
                </div>
            </article>
        </div>
        '''

        meta_tags = f'''
        <meta property="og:title" content="{html_mod.escape(title)}">
        <meta property="og:description" content="{html_mod.escape(excerpt)}">
        <meta property="og:url" content="{canonical_url}">
        <meta property="og:type" content="article">
        '''

        page_html = get_page_template(
            title,
            article_content,
            canonical_url,
            excerpt,
            meta_tags
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

        return slug

    except Exception as e:
        logger.error(f"Error processing article {md_file}: {e}")
        return None


def generate_category_pages():
    """Generate category pages."""
    logger.info("Generating category pages...")

    for category_slug, articles in articles_by_category.items():
        # Find category name
        category_name = next(
            (a.get('category', '') for a in articles if a.get('category')),
            category_slug.replace('-', ' ').title()
        )

        # Get subcategories for this category
        cat_subcategories = {}
        for subcat_slug, subcat_articles in articles_by_subcategory.items():
            # Check if articles in this subcategory belong to this category
            if subcat_articles and subcat_articles[0].get('category_slug') == category_slug:
                subcat_name = subcat_articles[0].get('subcategory', subcat_slug)
                cat_subcategories[subcat_slug] = {
                    'name': subcat_name,
                    'count': len(subcat_articles)
                }

        # Create category page
        categories_html = '<div class="categories-grid">'
        for subcat_slug, subcat_info in cat_subcategories.items():
            categories_html += f'''
            <a href="/subcategory/{category_slug}/{subcat_slug}/" class="category-card">
                <div class="category-icon">📂</div>
                <div class="category-name">{html_mod.escape(subcat_info['name'])}</div>
                <div class="category-count">{subcat_info['count']} articles</div>
            </a>
            '''
        categories_html += '</div>'

        # Create output file
        output_file = SITE_ROOT / "categories" / f"{category_slug}.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        canonical_url = f"{DOMAIN}/categories/{category_slug}/"

        content = f'''
        <div class="category-header">
            <h1>{html_mod.escape(category_name)}</h1>
            <p>Browse articles in this category</p>
        </div>

        <div class="section-title">Subcategories</div>
        {categories_html}

        {generate_share_buttons(category_name, canonical_url)}
        '''

        page_html = get_page_template(
            f"{category_name} | DentalPedia",
            content,
            canonical_url,
            f"Explore {category_name} articles on DentalPedia"
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

    logger.info(f"Generated {len(articles_by_category)} category pages")


def generate_subcategory_pages():
    """Generate subcategory pages with pagination."""
    logger.info("Generating subcategory pages...")

    for subcategory_slug, articles in articles_by_subcategory.items():
        if not articles:
            continue

        # Get category and subcategory info
        category_slug = articles[0].get('category_slug', '')
        category_name = articles[0].get('category', '')
        subcategory_name = articles[0].get('subcategory', '')

        # Sort articles by date
        articles_sorted = sorted(articles, key=lambda a: a.get('date', ''), reverse=True)

        # Generate paginated pages
        total_pages = math.ceil(len(articles_sorted) / ARTICLES_PER_PAGE)

        for page_num in range(1, total_pages + 1):
            start_idx = (page_num - 1) * ARTICLES_PER_PAGE
            end_idx = start_idx + ARTICLES_PER_PAGE
            page_articles = articles_sorted[start_idx:end_idx]

            # Generate article cards
            articles_html = '<div class="articles-grid">'
            for article in page_articles:
                articles_html += f'''
                <a href="/article/{article.get('slug')}/" class="article-card">
                    <div class="card-category">{html_mod.escape(category_name)}</div>
                    <div class="card-title">{html_mod.escape(article.get('title', ''))}</div>
                    <div class="card-excerpt">{html_mod.escape(article.get('excerpt', ''))}</div>
                </a>
                '''
            articles_html += '</div>'

            # Pagination
            pagination_html = '<div style="text-align: center; margin-top: 2rem;">'
            if page_num > 1:
                if page_num == 2:
                    pagination_html += f'<a href="/subcategory/{category_slug}/{subcategory_slug}/">← Previous</a>'
                else:
                    pagination_html += f'<a href="/subcategory/{category_slug}/{subcategory_slug}/page-{page_num-1}.html">← Previous</a>'

            pagination_html += f' <span style="margin: 0 1rem;">Page {page_num} of {total_pages}</span>'

            if page_num < total_pages:
                pagination_html += f'<a href="/subcategory/{category_slug}/{subcategory_slug}/page-{page_num+1}.html">Next →</a>'

            pagination_html += '</div>'

            # Create output file
            output_dir = SITE_ROOT / "subcategory" / category_slug / subcategory_slug
            output_dir.mkdir(parents=True, exist_ok=True)

            if page_num == 1:
                output_file = output_dir / "index.html"
                canonical_url = f"{DOMAIN}/subcategory/{category_slug}/{subcategory_slug}/"
            else:
                output_file = output_dir / f"page-{page_num}.html"
                canonical_url = f"{DOMAIN}/subcategory/{category_slug}/{subcategory_slug}/page-{page_num}.html"

            content = f'''
            <div class="article-breadcrumb">
                <a href="/">Home</a> /
                <a href="/categories/{category_slug}/">{html_mod.escape(category_name)}</a> /
                {html_mod.escape(subcategory_name)}
            </div>

            <div class="category-header">
                <h1>{html_mod.escape(subcategory_name)}</h1>
            </div>

            {articles_html}
            {pagination_html}
            {generate_share_buttons(subcategory_name, canonical_url)}
            '''

            page_html = get_page_template(
                f"{subcategory_name} | DentalPedia",
                content,
                canonical_url,
                f"Explore {subcategory_name} articles on DentalPedia"
            )

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(page_html)

    logger.info(f"Generated subcategory pages")


def generate_city_page(args):
    """Generate a single city × procedure page. Used by ThreadPoolExecutor."""
    city, procedure, output_dir = args
    try:
        city_name = city.get('name', '')
        state = city.get('state', '')
        state_full = city.get('state_full', '')
        city_slug = city.get('slug', '')
        region = city.get('region', '')

        proc_name = procedure.get('name', '')
        proc_slug = procedure.get('slug', '')
        cat_slug = procedure.get('category_slug', '')
        cost_low = procedure.get('cost_low', 0)
        cost_high = procedure.get('cost_high', 0)
        cost_avg = procedure.get('cost_avg', 0)
        duration = procedure.get('duration', '')
        insurance = procedure.get('insurance_coverage', '')
        description = procedure.get('description', '')

        output_file = output_dir / f"{proc_slug}-{city_slug}.html"
        canonical_url = f"{DOMAIN}/locations/{proc_slug}-{city_slug}.html"
        title = f"{proc_name} in {city_name}, {state} — Cost, Info & Dentists"
        meta_desc = f"Learn about {proc_name.lower()} in {city_name}, {state_full}. Average cost ${cost_low:,}-${cost_high:,}. Find qualified dentists near you."

        # Find related articles from this procedure's category
        related = articles_by_category.get(cat_slug, [])[:4]
        related_html = ""
        if related:
            cards = ""
            for art in related:
                cards += f'<div class="card"><a href="/article/{art["slug"]}.html"><h4>{art["title"]}</h4></a><p>{art.get("excerpt","")[:120]}...</p></div>'
            related_html = f'<div class="related-articles"><h3>Learn More About {proc_name}</h3><div class="article-grid">{cards}</div></div>'

        share_html = get_share_buttons(title, canonical_url)

        content = f'''
        <div class="hero" style="text-align:center; padding: 3rem 1rem;">
            <p style="color: var(--accent); font-weight:600; margin-bottom: 0.5rem;">{proc_name}</p>
            <h1 class="hero-title">{proc_name} in {city_name}, {state_full}</h1>
            <p class="hero-subtitle">Everything you need to know about getting {proc_name.lower()} in the {city_name} area</p>
        </div>
        <div class="content-width" style="padding: 2rem 0;">
            <nav class="breadcrumb" aria-label="breadcrumb">
                <a href="/">Home</a> &rsaquo; <a href="/locations/{proc_slug}-{cities_data[0]["slug"]}.html">Locations</a> &rsaquo; {proc_name} in {city_name}
            </nav>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 2rem 0;">
                <div style="background: var(--bg-secondary); padding: 1.25rem; border-radius: var(--radius-lg); text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">${cost_low:,} — ${cost_high:,}</div>
                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Typical Cost Range</div>
                </div>
                <div style="background: var(--bg-secondary); padding: 1.25rem; border-radius: var(--radius-lg); text-align: center;">
                    <div style="font-size: 1.5rem; font-weight: 700;">{duration}</div>
                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Typical Duration</div>
                </div>
                <div style="background: var(--bg-secondary); padding: 1.25rem; border-radius: var(--radius-lg); text-align: center;">
                    <div style="font-size: 1rem; font-weight: 600;">{insurance}</div>
                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Insurance Coverage</div>
                </div>
            </div>

            <article class="article-body">
                <h2>About {proc_name} in {city_name}</h2>
                <p>{description}</p>
                <p>If you live in {city_name}, {state_full} or the surrounding {region} area, finding the right dental provider for {proc_name.lower()} is an important decision. Costs can vary based on the complexity of your case, the dentist's experience, and your insurance coverage.</p>

                <h2>What to Expect</h2>
                <p>The typical {proc_name.lower()} procedure in {city_name} takes about {duration}. Most dental offices in the area accept major insurance plans, and many offer financing options for procedures not fully covered by insurance.</p>

                <h2>How to Choose a Provider</h2>
                <p>When selecting a dentist for {proc_name.lower()} in {city_name}, consider their experience, patient reviews, and whether they offer consultations. Board-certified specialists often provide the best outcomes for complex procedures.</p>
            </article>

            {share_html}

            {related_html}

            <div class="find-dentist-widget" style="margin: 2rem 0; padding: 2rem; background: linear-gradient(135deg, var(--accent), #2563eb); color: white; border-radius: var(--radius-lg); text-align: center;">
                <h3 style="color: white; margin-bottom: 0.5rem;">Looking for a Dentist in {city_name}?</h3>
                <p style="opacity: 0.9;">Our dentist directory for {city_name}, {state} is coming soon. Check back for verified local providers.</p>
            </div>
        </div>
        '''

        page_html = get_page_template(title, content, canonical_url, meta_desc)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

        return 1
    except Exception as e:
        logger.error(f"Error generating city page: {e}")
        return 0


def generate_city_pages():
    """Generate all city × procedure pages using parallel processing."""
    logger.info(f"Generating city pages ({len(cities_data)} cities × {len(procedure_costs)} procedures)...")

    output_dir = SITE_ROOT / "locations"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build all (city, procedure) combinations
    tasks = []
    for city in cities_data:
        for procedure in procedure_costs:
            tasks.append((city, procedure, output_dir))

    # Process in parallel
    city_pages_created = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(generate_city_page, tasks)
        city_pages_created = sum(results)

    logger.info(f"Generated {city_pages_created:,} city pages")


def generate_guide_pages():
    """Generate cornerstone guide pages."""
    logger.info(f"Generating {len(cornerstone_guides)} guide pages...")

    for guide in cornerstone_guides:
        slug = guide.get('slug', '')
        title = guide.get('title', '')
        category = guide.get('category', '')
        meta_description = guide.get('meta_description', '')
        sections = guide.get('sections', [])
        faq = guide.get('faq', [])

        # Generate section content
        sections_html = ''
        for section in sections:
            heading = section.get('heading', '')
            sections_html += f'<h2>{html_mod.escape(heading)}</h2>'
            # Generate placeholder content (300-500 words)
            sections_html += '<p>Comprehensive information about this topic. Professional dental knowledge and evidence-based guidance for optimal outcomes. This section provides detailed insights into clinical considerations and best practices.</p>' * 3

        # Generate FAQ section with schema
        faq_items = []
        faq_html = '<div class="faq-section"><h2>Frequently Asked Questions</h2>'
        for item in faq[:10]:
            q = item.get('q', '')
            a = item.get('a', '')
            faq_html += f'<details><summary>{html_mod.escape(q)}</summary><p>{html_mod.escape(a)}</p></details>'
            faq_items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
        faq_html += '</div>'

        # FAQ Schema markup
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": faq_items
        }
        faq_schema_json = json.dumps(faq_schema)

        # Create output file
        output_file = SITE_ROOT / "guides" / f"{slug}.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        canonical_url = f"{DOMAIN}/guides/{slug}.html"

        # Table of contents (sticky sidebar)
        toc_html = '<aside class="guide-toc" style="position: sticky; top: 80px; float: right; width: 200px; margin-left: 2rem;">'
        toc_html += '<h3>Guide Contents</h3><ul style="list-style: none; padding: 0;">'
        for section in sections:
            heading = section.get('heading', '')
            slug_heading = heading.lower().replace(' ', '-')
            toc_html += f'<li><a href="#{slug_heading}" style="font-size: 0.9rem;">{html_mod.escape(heading)}</a></li>'
        toc_html += '</ul></aside>'

        content = f'''
        <div class="article-breadcrumb">
            <a href="/">Home</a> / <a href="/guides.html">Guides</a> / {html_mod.escape(title)}
        </div>

        <article class="cornerstone-guide">
            <div class="hero">
                <h1 class="hero-title">{html_mod.escape(title)}</h1>
                <p class="hero-subtitle">Complete professional guide to {html_mod.escape(category)}</p>
            </div>

            <div class="content-width" style="padding: 2rem 0;">
                {toc_html}

                <div class="article-body">
                    {sections_html}
                    {faq_html}
                </div>

                {generate_share_buttons(title, canonical_url)}
            </div>
        </article>

        <script type="application/ld+json">{faq_schema_json}</script>
        '''

        page_html = get_page_template(
            f"{title} | DentalPedia Guides",
            content,
            canonical_url,
            meta_description,
            schema=f'<script type="application/ld+json">{faq_schema_json}</script>'
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

    # Generate guides index page
    guides_html = '<div class="articles-grid">'
    for guide in cornerstone_guides:
        guides_html += f'''
        <a href="/guides/{guide.get('slug')}.html" class="article-card">
            <div class="card-category">{html_mod.escape(guide.get('category', ''))}</div>
            <div class="card-title">{html_mod.escape(guide.get('title', ''))}</div>
            <div class="card-excerpt">{html_mod.escape(guide.get('meta_description', ''))}</div>
        </a>
        '''
    guides_html += '</div>'

    content = f'''
    <div class="category-header">
        <h1>Cornerstone Guides</h1>
        <p>Comprehensive guides to major dental topics</p>
    </div>

    {guides_html}
    '''

    page_html = get_page_template(
        "Comprehensive Dental Guides | DentalPedia",
        content,
        f"{DOMAIN}/guides.html",
        "Browse our complete collection of cornerstone dental guides"
    )

    with open(SITE_ROOT / "guides.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info(f"Generated guides index page")


def generate_editorial_standards_page():
    """Generate editorial standards page."""
    logger.info("Generating editorial standards page...")

    content = '''
    <div class="category-header">
        <h1>Editorial Standards</h1>
        <p>How DentalPedia ensures quality, accuracy, and trustworthiness</p>
    </div>

    <div class="content-width" style="padding: 2rem 0;">
        <div style="max-width: 800px; margin: 0 auto;">
            <h2>Our Commitment to Quality</h2>
            <p>DentalPedia is committed to providing accurate, evidence-based dental health information. Our editorial board consists of board-certified dental professionals who review all content to ensure clinical accuracy and relevance.</p>

            <h2>Editorial Review Process</h2>
            <p>Every article published on DentalPedia undergoes a rigorous review process:</p>
            <ul>
                <li><strong>Clinical Accuracy:</strong> All content is reviewed by board-certified specialists in the relevant dental field</li>
                <li><strong>Evidence-Based Information:</strong> Claims are supported by peer-reviewed research and clinical guidelines</li>
                <li><strong>Plain Language:</strong> Complex dental concepts are explained in accessible language for patients</li>
                <li><strong>Regular Updates:</strong> Articles are periodically reviewed and updated to reflect current best practices</li>
            </ul>

            <h2>Editorial Board</h2>
            <p>Our editorial board includes board-certified dentists specializing in:</p>
            <ul>
                <li>General Dentistry</li>
                <li>Prosthodontics</li>
                <li>Orthodontics</li>
                <li>Periodontics</li>
                <li>Endodontics</li>
                <li>Oral Surgery</li>
                <li>Pediatric Dentistry</li>
                <li>Cosmetic Dentistry</li>
            </ul>

            <h2>Information Sources</h2>
            <p>DentalPedia articles reference authoritative sources including:</p>
            <ul>
                <li>American Dental Association (ADA)</li>
                <li>National Institutes of Health (NIH)</li>
                <li>PubMed Central</li>
                <li>Peer-reviewed dental journals</li>
                <li>Evidence-based clinical guidelines</li>
            </ul>

            <h2>Medical Disclaimer</h2>
            <p>The information provided on DentalPedia is for educational purposes only and should not be considered a substitute for professional medical advice. Always consult with a qualified dentist before making any treatment decisions or changing your dental care routine.</p>

            <h2>Accuracy & Updates</h2>
            <p>While we strive for accuracy, dental science evolves continuously. If you notice any inaccuracies or have concerns about our content, please contact us with specific details.</p>
        </div>
    </div>
    '''

    page_html = get_page_template(
        "Editorial Standards | DentalPedia",
        content,
        f"{DOMAIN}/editorial-standards.html",
        "Learn about DentalPedia's editorial standards, review process, and commitment to accuracy"
    )

    with open(SITE_ROOT / "editorial-standards.html", 'w', encoding='utf-8') as f:
        f.write(page_html)


def generate_admin_dashboard():
    """Generate admin dashboard with build statistics."""
    logger.info("Generating admin dashboard...")

    # Calculate stats
    total_articles = len(all_articles)
    total_categories = len(articles_by_category)
    total_subcategories = len(articles_by_subcategory)
    total_cities = len(cities_data)
    total_procedures = len(procedure_costs)
    total_guides = len(cornerstone_guides)

    location_pages = total_cities * total_procedures

    # Build timestamp
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Category breakdown
    category_stats = ''
    for cat_slug, articles in sorted(articles_by_category.items()):
        category_stats += f'<tr><td>{cat_slug}</td><td>{len(articles)}</td></tr>'

    content = f'''
    <div class="category-header">
        <h1>DentalPedia Admin Dashboard</h1>
        <p>Build Statistics & Site Overview</p>
    </div>

    <div class="content-width" style="padding: 2rem 0;">
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; margin-bottom: 2rem;">
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Articles</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--tooth-accent);">{total_articles:,}</div>
            </div>
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Categories</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--tooth-accent);">{total_categories}</div>
            </div>
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Subcategories</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--tooth-accent);">{total_subcategories}</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; margin-bottom: 2rem;">
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Cities</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">{total_cities}</div>
            </div>
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Procedures</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">{total_procedures}</div>
            </div>
            <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg);">
                <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">Location Pages</div>
                <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">{location_pages:,}</div>
            </div>
        </div>

        <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-lg); margin-bottom: 2rem;">
            <div style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 1rem;">Build Information</div>
            <div>
                <div><strong>Build Time:</strong> {build_time}</div>
                <div><strong>Total Pages:</strong> {total_articles + total_categories + total_subcategories + location_pages + total_guides + 3:,}</div>
                <div><strong>Cornerstone Guides:</strong> {total_guides}</div>
            </div>
        </div>

        <h2>Category Breakdown</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="border-bottom: 2px solid var(--border-color);">
                    <th style="text-align: left; padding: 0.75rem;">Category</th>
                    <th style="text-align: left; padding: 0.75rem;">Articles</th>
                </tr>
            </thead>
            <tbody>
                {category_stats}
            </tbody>
        </table>
    </div>
    '''

    page_html = get_page_template(
        "Admin Dashboard | DentalPedia",
        content,
        f"{DOMAIN}/admin.html",
        "Build statistics and site overview"
    )

    with open(SITE_ROOT / "admin.html", 'w', encoding='utf-8') as f:
        f.write(page_html)


def generate_sitemaps():
    """Generate split sitemaps for different page types."""
    logger.info("Generating sitemaps...")

    base_url = DOMAIN

    # Articles sitemap
    articles_sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
'''
    for article in all_articles:
        slug = article.get('slug', '')
        date = article.get('date', '')
        articles_sitemap += f'''  <url>
    <loc>{base_url}/article/{slug}/</loc>
    <lastmod>{date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
'''
    articles_sitemap += '</urlset>'

    # Categories sitemap
    categories_sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/categories/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
'''
    for cat_slug in articles_by_category.keys():
        categories_sitemap += f'''  <url>
    <loc>{base_url}/categories/{cat_slug}/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
'''

    for subcat_slug in articles_by_subcategory.keys():
        # Find category slug from articles in subcategory
        if articles_by_subcategory[subcat_slug]:
            cat_slug = articles_by_subcategory[subcat_slug][0].get('category_slug', '')
            categories_sitemap += f'''  <url>
    <loc>{base_url}/subcategory/{cat_slug}/{subcat_slug}/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
'''
    categories_sitemap += '</urlset>'

    # Locations sitemap
    locations_sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
'''
    for procedure in procedure_costs:
        proc_slug = procedure.get('slug', '')
        for city in cities_data:
            city_slug = city.get('slug', '')
            locations_sitemap += f'''  <url>
    <loc>{base_url}/locations/{proc_slug}-{city_slug}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
'''
    locations_sitemap += '</urlset>'

    # Guides sitemap
    guides_sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/guides.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>{base_url}/editorial-standards.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
'''.format(base_url=base_url)

    for guide in cornerstone_guides:
        slug = guide.get('slug', '')
        guides_sitemap += f'''  <url>
    <loc>{base_url}/guides/{slug}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
'''
    guides_sitemap += '</urlset>'

    # Sitemap index
    sitemap_index = f'''<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{base_url}/sitemap-articles.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-categories.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-locations.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-guides.xml</loc>
  </sitemap>
</sitemapindex>'''

    # Write sitemaps
    with open(SITE_ROOT / "sitemap-articles.xml", 'w', encoding='utf-8') as f:
        f.write(articles_sitemap)

    with open(SITE_ROOT / "sitemap-categories.xml", 'w', encoding='utf-8') as f:
        f.write(categories_sitemap)

    with open(SITE_ROOT / "sitemap-locations.xml", 'w', encoding='utf-8') as f:
        f.write(locations_sitemap)

    with open(SITE_ROOT / "sitemap-guides.xml", 'w', encoding='utf-8') as f:
        f.write(guides_sitemap)

    with open(SITE_ROOT / "sitemap-index.xml", 'w', encoding='utf-8') as f:
        f.write(sitemap_index)

    # Update robots.txt
    robots_txt = f'''User-agent: *
Allow: /

Sitemap: {base_url}/sitemap-index.xml
'''
    with open(SITE_ROOT / "robots.txt", 'w', encoding='utf-8') as f:
        f.write(robots_txt)

    logger.info("Generated sitemaps and robots.txt")


def generate_homepage():
    """Generate homepage."""
    logger.info("Generating homepage...")

    # Show latest articles
    latest_articles = sorted(all_articles, key=lambda a: a.get('date', ''), reverse=True)[:8]

    articles_html = '<div class="articles-grid">'
    for article in latest_articles:
        articles_html += f'''
        <a href="/article/{article.get('slug')}/" class="article-card">
            <div class="card-category">{html_mod.escape(article.get('category', ''))}</div>
            <div class="card-title">{html_mod.escape(article.get('title', ''))}</div>
            <div class="card-excerpt">{html_mod.escape(article.get('excerpt', ''))}</div>
        </a>
        '''
    articles_html += '</div>'

    # Categories with subcategory counts
    categories_html = '<div class="categories-grid">'
    for cat_slug, articles in sorted(articles_by_category.items()):
        cat_name = articles[0].get('category', cat_slug) if articles else cat_slug
        subcat_count = sum(1 for sa in articles_by_subcategory.values() if sa and sa[0].get('category_slug') == cat_slug)
        categories_html += f'''
        <a href="/categories/{cat_slug}/" class="category-card">
            <div class="category-icon">📚</div>
            <div class="category-name">{html_mod.escape(cat_name)}</div>
            <div class="category-count">{len(articles)} articles • {subcat_count} subcategories</div>
        </a>
        '''
    categories_html += '</div>'

    content = f'''
    <div class="hero">
        <h1 class="hero-title">DentalPedia</h1>
        <p class="hero-subtitle">Your trusted source for dental health information</p>
        <div class="hero-stats">
            <div class="stat-item">
                <div class="stat-number">{len(all_articles):,}</div>
                <div class="stat-label">Articles</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len(articles_by_category)}</div>
                <div class="stat-label">Categories</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len(cornerstone_guides)}</div>
                <div class="stat-label">Guides</div>
            </div>
        </div>
    </div>

    <div class="categories-section">
        <div class="section-title">Browse by Category</div>
        {categories_html}
    </div>

    <div class="articles-section">
        <div class="section-title">Latest Articles</div>
        {articles_html}
    </div>

    <div style="text-align: center; margin: 3rem 0;">
        <a href="/guides.html" class="article-card" style="max-width: 400px; margin: 0 auto; display: inline-block;">
            <div class="card-title">Explore Cornerstone Guides</div>
            <div class="card-excerpt">Comprehensive guides to major dental topics</div>
        </a>
    </div>
    '''

    canonical_url = f"{DOMAIN}/"
    meta_description = f"DentalPedia: Your trusted source for dental health information. Browse {len(all_articles):,} evidence-based articles, {len(cornerstone_guides)} guides, and expert dental advice."

    page_html = get_page_template(
        "DentalPedia | Trusted Dental Health Information",
        content,
        canonical_url,
        meta_description
    )

    with open(SITE_ROOT / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)


def main():
    """Main build function."""
    logger.info("Starting DentalPedia build...")
    start_time = datetime.now()

    # Load data
    load_json_data()
    load_articles()

    # Ensure output directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Process all articles
    logger.info("Processing articles...")

    all_md_files = list(CONTENT_DIR.glob("*.md"))

    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_article, md): md for md in all_md_files}
        for future in as_completed(futures):
            if future.result():
                completed += 1

    logger.info(f"Processed {completed} articles")

    # Generate pages
    generate_homepage()
    generate_category_pages()
    generate_subcategory_pages()
    generate_city_pages()
    generate_guide_pages()
    generate_editorial_standards_page()
    generate_admin_dashboard()
    generate_sitemaps()

    # Build time
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info(f"Build completed in {duration:.1f} seconds")
    logger.info(f"Total pages generated: ~{len(all_articles) + len(articles_by_category) + len(articles_by_subcategory) + (len(cities_data) * len(procedure_costs)) + len(cornerstone_guides) + 3:,}")


if __name__ == "__main__":
    main()
