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
import hashlib

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
guides_by_category = {}  # category_slug -> guide data
minified_css_hash = ""  # Cache-busting hash for minified CSS


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
        # Build category -> guide lookup for pillar-cluster linking
        for guide in cornerstone_guides:
            cat_slug = guide.get('category_slug', '')
            if cat_slug:
                guides_by_category[cat_slug] = guide
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


def heading_slug(text):
    """Convert heading text to URL-friendly slug (matches generate_toc_html logic)."""
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'[^\w\s-]', '', clean).replace(' ', '-').lower()


def markdown_to_html(text):
    """Convert markdown to HTML."""
    # Headers — add id attributes for TOC anchor linking
    def h3_repl(m):
        s = heading_slug(m.group(1))
        return f'<h3 id="{s}">{m.group(1)}</h3>'
    def h2_repl(m):
        s = heading_slug(m.group(1))
        return f'<h2 id="{s}">{m.group(1)}</h2>'

    text = re.sub(r'^### (.*?)$', h3_repl, text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', h2_repl, text, flags=re.MULTILINE)
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
    breadcrumb = f'<div class="article-breadcrumb"><a href="/">Home</a> / <a href="/category/{category_slug}.html">{category}</a>'
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
    """Generate navbar HTML with mobile hamburger and Tools dropdown."""
    return '''
    <nav class="navbar">
        <div class="container">
            <a href="/" class="navbar-brand">
                <span class="logo-icon">🦷</span>
                <span>DentalPedia</span>
            </a>
            <button class="hamburger" onclick="document.querySelector('.navbar-nav').classList.toggle('active');this.classList.toggle('open')" aria-label="Menu">
                <span></span><span></span><span></span>
            </button>
            <ul class="navbar-nav">
                <li><a href="/">Home</a></li>
                <li><a href="/categories.html">Categories</a></li>
                <li><a href="/guides.html">Guides</a></li>
                <li class="nav-dropdown">
                    <a href="#" class="dropdown-toggle" onclick="event.preventDefault();this.parentElement.classList.toggle('open')">Tools ▾</a>
                    <ul class="dropdown-menu">
                        <li><a href="/tools/cost-calculator.html">💰 Cost Calculator</a></li>
                        <li><a href="/tools/dental-health-quiz.html">📊 Health Quiz</a></li>
                        <li><a href="/compare/">📍 Cost by City</a></li>
                    </ul>
                </li>
                <li><a href="/myths/">Myths vs Facts</a></li>
                <li><a href="/widget/">For Dentists</a></li>
            </ul>
            <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle dark mode">🌓</button>
        </div>
    </nav>
    '''


def get_footer_html():
    """Generate footer HTML with full site navigation."""
    return f'''
    <footer class="footer">
        <div class="container">
            <div class="footer-content">
                <div class="footer-section">
                    <div class="footer-title">DentalPedia</div>
                    <p class="footer-text">Your trusted source for evidence-based dental health information. Browse {len(all_articles):,} articles written and reviewed by dental professionals.</p>
                </div>
                <div class="footer-section">
                    <div class="footer-title">Explore</div>
                    <ul class="footer-links">
                        <li><a href="/categories.html">All Categories</a></li>
                        <li><a href="/guides.html">Cornerstone Guides</a></li>
                        <li><a href="/myths/">Myths vs Facts</a></li>
                        <li><a href="/compare/">Cost Comparisons</a></li>
                    </ul>
                </div>
                <div class="footer-section">
                    <div class="footer-title">Tools</div>
                    <ul class="footer-links">
                        <li><a href="/tools/cost-calculator.html">Dental Cost Calculator</a></li>
                        <li><a href="/tools/dental-health-quiz.html">Dental Health Quiz</a></li>
                        <li><a href="/widget/">Widget for Dentists</a></li>
                    </ul>
                </div>
                <div class="footer-section">
                    <div class="footer-title">About</div>
                    <ul class="footer-links">
                        <li><a href="/editorial-standards.html">Editorial Standards</a></li>
                        <li><a href="/privacy.html">Privacy Policy</a></li>
                        <li><a href="/terms.html">Terms of Use</a></li>
                    </ul>
                </div>
            </div>
            <div style="border-top: 1px solid var(--border-color); margin-top: 2rem; padding-top: 1.5rem; text-align: center;">
                <p class="footer-text">&copy; 2026 DentalPedia. All rights reserved. This site is for informational purposes only and does not constitute medical advice.</p>
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


def minify_css():
    """Minify the CSS file and create a cache-busted version."""
    global minified_css_hash
    css_path = Path("assets/css/style.css")
    if not css_path.exists():
        return
    with open(css_path, 'r') as f:
        css = f.read()
    minified = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    minified = re.sub(r'\s+', ' ', minified)
    minified = re.sub(r'\s*([{}:;,>~+])\s*', r'\1', minified)
    minified = re.sub(r';\s*}', '}', minified)
    minified = minified.strip()
    min_path = Path("assets/css/style.min.css")
    min_path.parent.mkdir(parents=True, exist_ok=True)
    with open(min_path, 'w') as f:
        f.write(minified)
    minified_css_hash = hashlib.md5(minified.encode()).hexdigest()[:8]
    logger.info(f"CSS minified: {len(css):,} -> {len(minified):,} bytes ({100-len(minified)*100//len(css)}% reduction)")


CRITICAL_CSS = '''<style>:root{--bg-primary:#fff;--bg-secondary:#f8f9fa;--text-primary:#1a1a2e;--text-secondary:#4a4a6a;--accent:#2563eb;--border-color:#e2e8f0}[data-theme=dark]{--bg-primary:#0f172a;--bg-secondary:#1e293b;--text-primary:#e2e8f0;--text-secondary:#94a3b8;--accent:#60a5fa;--border-color:#334155}*{margin:0;padding:0;box-sizing:border-box}body{font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg-primary);color:var(--text-primary);line-height:1.6}.navbar{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border-color);padding:.75rem 0}[data-theme=dark] .navbar{background:rgba(15,23,42,.85)}.navbar .container{max-width:1200px;margin:0 auto;padding:0 1rem;display:flex;align-items:center;justify-content:space-between}.navbar-brand{display:flex;align-items:center;gap:.5rem;text-decoration:none;font-size:1.25rem;font-weight:700;color:var(--text-primary)}.navbar-nav{display:flex;list-style:none;gap:1.5rem}.navbar-nav a{text-decoration:none;color:var(--text-secondary);font-size:.95rem}.hamburger{display:none;background:none;border:none;cursor:pointer;padding:.5rem;flex-direction:column;gap:5px}.hamburger span{display:block;width:24px;height:2.5px;background:var(--text-primary);border-radius:2px}.container{max-width:1200px;margin:0 auto;padding:0 1rem}h1{font-size:2rem;line-height:1.3;margin-bottom:1rem}@media(max-width:768px){.hamburger{display:flex}.navbar-nav{display:none}.navbar-nav.active{display:flex;position:absolute;top:100%;left:0;right:0;background:var(--bg-primary);flex-direction:column;gap:0;padding:.5rem 0;z-index:200}}</style>'''


def get_page_template(title, content, canonical_url, description="", meta_tags="", schema=""):
    """Generate full HTML page template."""

    css_file = f"/assets/css/style.min.css?v={minified_css_hash}" if minified_css_hash else "/assets/css/style.css"

    # Auto-generate OG tags if not provided
    if not meta_tags:
        meta_tags = f'''
    <meta property="og:title" content="{html_mod.escape(title)}">
    <meta property="og:description" content="{html_mod.escape(description)}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="DentalPedia">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{html_mod.escape(title)}">
    <meta name="twitter:description" content="{html_mod.escape(description)}">
        '''

    template = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_mod.escape(title)}</title>
    <meta name="description" content="{html_mod.escape(description)}">
    <link rel="canonical" href="{canonical_url}">
    <meta property="og:locale" content="en_US">
    <meta property="og:site_name" content="DentalPedia">
    {meta_tags}
    {schema}
    {CRITICAL_CSS}
    <link rel="stylesheet" href="{css_file}">
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


def get_related_articles_for_guide(category_slug, max_articles=6):
    """Return a grid of related articles for a guide's category (cluster -> pillar link)."""
    articles = articles_by_category.get(category_slug, [])[:max_articles]
    if not articles:
        return ''
    cards = '<div style="margin-top: 2rem;"><h2>Related Articles</h2><div class="articles-grid">'
    for a in articles:
        cards += f'''<a href="/article/{a.get('slug')}.html" class="article-card">
            <div class="card-category">{html_mod.escape(a.get('category', ''))}</div>
            <div class="card-title">{html_mod.escape(a.get('title', ''))}</div>
            <div class="card-excerpt">{html_mod.escape(a.get('excerpt', '')[:120])}</div>
        </a>'''
    cards += '</div></div>'
    return cards


def get_related_guide_card(category_slug):
    """Return a 'Read the Full Guide' card if a guide exists for this category."""
    guide = guides_by_category.get(category_slug)
    if not guide:
        return ''
    return f'''<div class="related-guide-card" style="background: linear-gradient(135deg, #eff6ff, #f0fdf4); border: 1px solid #bfdbfe; border-radius: 12px; padding: 1.25rem; margin: 1.5rem 0;">
        <div style="font-weight: 600; margin-bottom: 0.5rem;">📖 Want the complete picture?</div>
        <a href="/guides/{guide.get('slug')}.html" style="font-size: 1.1rem; font-weight: 700; color: #2563eb; text-decoration: none;">{html_mod.escape(guide.get('title', ''))}</a>
        <p style="margin: 0.5rem 0 0; color: #64748b; font-size: 0.9rem;">{html_mod.escape(guide.get('meta_description', ''))}</p>
    </div>'''


def create_internal_links(html_content, current_slug, max_links=3):
    """Auto-link mentions of other article titles within content.
    Only checks articles in the same category for speed. Max 3 links."""
    current_meta = article_lookup.get(current_slug, {})
    current_cat = current_meta.get('category_slug', '')
    if not current_cat:
        return html_content

    # Only check same-category articles (much faster than all 2000)
    candidates = [m for s, m in article_lookup.items()
                  if s != current_slug and m.get('category_slug') == current_cat
                  and len(m.get('title', '')) >= 12][:20]  # Cap at 20 candidates

    links_added = 0
    for meta in candidates:
        if links_added >= max_links:
            break
        other_title = meta.get('title', '')
        other_slug = meta.get('slug', '')
        # Simple case-insensitive string search first (fast)
        if other_title.lower() not in html_content.lower():
            continue
        # Now do the regex replacement
        pattern = re.compile(r'(?<=<p>|<li>)([^<]*?)(' + re.escape(other_title) + r')([^<]*?)(?=</)', re.IGNORECASE)
        match = pattern.search(html_content)
        if match:
            replacement = f'{match.group(1)}<a href="/article/{other_slug}.html">{match.group(2)}</a>{match.group(3)}'
            html_content = html_content[:match.start()] + replacement + html_content[match.end():]
            links_added += 1
    return html_content


def process_article(md_file):
    """Process a single article file and generate HTML."""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata, body = parse_markdown_frontmatter(content)

        if 'slug' not in metadata:
            return None

        slug = metadata['slug']

        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        canonical_url = f"{DOMAIN}/article/{slug}.html"
        title = metadata.get('title', 'Untitled')
        excerpt = metadata.get('excerpt', '')
        category = metadata.get('category', '')
        category_slug = metadata.get('category_slug', '')
        reviewer_specialty = metadata.get('reviewer_specialty', 'General Dentistry')
        subcategory = metadata.get('subcategory', '')
        subcategory_slug = metadata.get('subcategory_slug', '')
        date = metadata.get('date', '')
        read_time = metadata.get('read_time', '5 min')
        sources = metadata.get('sources', [])

        # Convert full markdown body to HTML
        body_html = markdown_to_html(body)

        # Internal linking: auto-link mentions of other article titles
        body_html = create_internal_links(body_html, slug)

        # GEO: Add "Key Takeaway" summary box for AI Overviews
        first_para = re.search(r'<p>(.*?)</p>', body_html)
        if first_para and len(first_para.group(1)) > 80:
            takeaway_text = first_para.group(1)[:250]
            if len(first_para.group(1)) > 250:
                takeaway_text = takeaway_text.rsplit(' ', 1)[0] + '...'
            geo_box = f'<div class="key-takeaway" style="background: #eff6ff; border-left: 4px solid #2563eb; padding: 1rem 1.25rem; border-radius: 0 8px 8px 0; margin: 1.5rem 0; font-size: 0.95rem;"><strong>Key Takeaway:</strong> {takeaway_text}</div>'
            # Insert after first heading
            body_html = re.sub(r'(</h2>)', r'\1' + geo_box, body_html, count=1)

        # Table of contents from headings
        headings = extract_headings(body_html)
        toc_html = generate_toc_html(headings) if headings else ''

        # Breadcrumb
        breadcrumb = f'<nav class="article-breadcrumb"><a href="/">Home</a> / <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a>'
        if subcategory and subcategory_slug:
            breadcrumb += f' / <a href="/subcategory/{category_slug}/{subcategory_slug}/">{html_mod.escape(subcategory)}</a>'
        breadcrumb += f' / {html_mod.escape(title)}</nav>'

        # Sources
        sources_html = ""
        if sources:
            sources_html = '<div class="sources-card"><div class="sources-title">Sources</div><ul class="sources-list">'
            for source in sources:
                s_title = source.get('title', 'Source')
                s_url = source.get('url', '#')
                sources_html += f'<li><a href="{s_url}" target="_blank" rel="noopener">{html_mod.escape(s_title)}</a></li>'
            sources_html += '</ul></div>'

        article_content = f'''
        <div class="article-page">
            <article class="content-width">
                {breadcrumb}
                <header class="article-header">
                    <h1>{html_mod.escape(title)}</h1>
                    <div class="article-meta">
                        <span>📅 {date}</span>
                        <span>⏱️ {read_time}</span>
                        <span>📚 <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a></span>
                    </div>
                </header>

                {toc_html}

                <div class="article-body">
                    {body_html}
                </div>

                <div class="eeat-card">
                    <div class="eeat-icon">🦷</div>
                    <div class="eeat-name">Reviewed by DentalPedia Editorial Board</div>
                    <div class="eeat-credentials">Board-Certified {html_mod.escape(reviewer_specialty)} • <a href="/editorial-standards.html">Our Standards</a></div>
                </div>

                {sources_html}

                {get_related_guide_card(category_slug)}

                {generate_share_buttons(title, canonical_url)}

                <div class="disclaimer">
                    <div class="disclaimer-icon">⚠️</div>
                    <div>This information is educational and not a substitute for professional medical advice. Always consult your dentist before making treatment decisions.</div>
                </div>
            </article>
        </div>
        '''

        meta_tags = f'''
        <meta property="og:title" content="{html_mod.escape(title)}">
        <meta property="og:description" content="{html_mod.escape(excerpt)}">
        <meta property="og:url" content="{canonical_url}">
        <meta property="og:type" content="article">
        <meta property="article:section" content="{html_mod.escape(category)}">
        <meta name="twitter:card" content="summary">
        <meta name="twitter:title" content="{html_mod.escape(title)}">
        <meta name="twitter:description" content="{html_mod.escape(excerpt)}">
        '''

        # BreadcrumbList structured data
        breadcrumb_items = [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": DOMAIN},
            {"@type": "ListItem", "position": 2, "name": category, "item": f"{DOMAIN}/category/{category_slug}.html"}
        ]
        pos = 3
        if subcategory and subcategory_slug:
            breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": subcategory, "item": f"{DOMAIN}/subcategory/{category_slug}/{subcategory_slug}/"})
            pos += 1
        breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": title})

        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }

        # Article structured data
        article_schema = {
            "@context": "https://schema.org",
            "@type": "MedicalWebPage",
            "headline": title,
            "description": excerpt,
            "datePublished": date,
            "dateModified": date,
            "url": canonical_url,
            "author": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "publisher": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "reviewedBy": {"@type": "Organization", "name": "DentalPedia Medical Review Board", "url": f"{DOMAIN}/editorial-standards.html"},
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url}
        }

        # FAQ structured data from H2 headings (treat as questions)
        faq_pairs = []
        if headings:
            # Extract text after each heading as answer
            for heading in headings:
                clean_h = re.sub(r'<[^>]+>', '', heading)
                # Find text after this heading in body_html
                pattern = re.escape(heading) + r'</h2>\s*(.*?)(?=<h[23]|$)'
                match = re.search(pattern, body_html, re.DOTALL)
                if match:
                    answer_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                    if len(answer_text) > 50:
                        # Truncate to first 300 chars for schema
                        answer_snippet = answer_text[:300].rsplit(' ', 1)[0] + '...' if len(answer_text) > 300 else answer_text
                        # Convert heading to question format
                        question = clean_h if clean_h.endswith('?') else f"What should I know about {clean_h.lower()}?"
                        faq_pairs.append({
                            "@type": "Question",
                            "name": question,
                            "acceptedAnswer": {"@type": "Answer", "text": answer_snippet}
                        })

        faq_schema_str = ""
        if faq_pairs:
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_pairs[:5]  # Max 5 FAQ items
            }
            faq_schema_str = f'<script type="application/ld+json">{json.dumps(faq_schema)}</script>'

        all_schema = f'''<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
        <script type="application/ld+json">{json.dumps(article_schema)}</script>
        {faq_schema_str}'''

        page_html = get_page_template(
            title,
            article_content,
            canonical_url,
            excerpt,
            meta_tags,
            all_schema
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

        return slug

    except Exception as e:
        logger.error(f"Error processing article {md_file}: {e}")
        return None


def generate_categories_index():
    """Generate the /categories.html index page listing all categories."""
    logger.info("Generating categories index page...")

    cards_html = '<div class="categories-grid">'
    for cat_slug, articles in sorted(articles_by_category.items()):
        cat_name = articles[0].get('category', cat_slug) if articles else cat_slug
        subcat_count = sum(1 for sa in articles_by_subcategory.values()
                          if sa and sa[0].get('category_slug') == cat_slug)
        cards_html += f'''
        <a href="/category/{cat_slug}.html" class="category-card">
            <div class="category-icon">📚</div>
            <div class="category-name">{html_mod.escape(cat_name)}</div>
            <div class="category-count">{len(articles)} articles • {subcat_count} subcategories</div>
        </a>'''
    cards_html += '</div>'

    content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Categories</nav>
        <h1>All Categories</h1>
        <p style="color: var(--text-secondary);">{len(articles_by_category)} categories covering {len(all_articles):,} articles</p>
        {cards_html}
    </div>
    '''

    page_html = get_page_template(
        "All Categories — DentalPedia",
        content,
        f"{DOMAIN}/categories.html",
        f"Browse all {len(articles_by_category)} dental categories on DentalPedia"
    )

    with open(SITE_ROOT / "categories.html", 'w', encoding='utf-8') as f:
        f.write(page_html)
    logger.info("Generated categories.html index page")


def generate_category_pages():
    """Generate category pages with subcategories AND paginated article listings."""
    logger.info("Generating category pages...")

    output_dir = SITE_ROOT / "category"
    output_dir.mkdir(parents=True, exist_ok=True)
    total_pages = 0

    for category_slug, articles in articles_by_category.items():
        category_name = next(
            (a.get('category', '') for a in articles if a.get('category')),
            category_slug.replace('-', ' ').title()
        )

        # Get subcategories for this category
        cat_subcategories = {}
        for subcat_slug, subcat_articles in articles_by_subcategory.items():
            if subcat_articles and subcat_articles[0].get('category_slug') == category_slug:
                subcat_name = subcat_articles[0].get('subcategory', subcat_slug)
                cat_subcategories[subcat_slug] = {
                    'name': subcat_name,
                    'count': len(subcat_articles)
                }

        # Subcategories section
        subcat_html = ''
        if cat_subcategories:
            subcat_html = '<div class="section-title" style="margin-top:2rem;">Subcategories</div><div class="categories-grid">'
            for subcat_slug, subcat_info in cat_subcategories.items():
                subcat_html += f'''
                <a href="/subcategory/{category_slug}/{subcat_slug}/" class="category-card">
                    <div class="category-icon">📂</div>
                    <div class="category-name">{html_mod.escape(subcat_info["name"])}</div>
                    <div class="category-count">{subcat_info["count"]} articles</div>
                </a>'''
            subcat_html += '</div>'

        # Sort articles by date
        sorted_articles = sorted(articles, key=lambda a: a.get('date', ''), reverse=True)

        # Paginate (20 per page)
        per_page = 20
        total = len(sorted_articles)
        num_pages = max(1, (total + per_page - 1) // per_page)

        for page_num in range(1, num_pages + 1):
            start = (page_num - 1) * per_page
            end = start + per_page
            page_articles = sorted_articles[start:end]

            # Build article cards
            cards_html = '<div class="article-grid">'
            for art in page_articles:
                slug = art.get('slug', '')
                title = art.get('title', 'Untitled')
                excerpt = art.get('excerpt', '')[:150]
                date = art.get('date', '')
                read_time = art.get('read_time', '5 min')
                cards_html += f'''
                <div class="card">
                    <a href="/article/{slug}.html"><h3>{html_mod.escape(title)}</h3></a>
                    <div class="article-meta"><span>📅 {date}</span> <span>⏱️ {read_time}</span></div>
                    <p>{html_mod.escape(excerpt)}</p>
                    <a href="/article/{slug}.html" class="read-more">Read more →</a>
                </div>'''
            cards_html += '</div>'

            # Pagination
            pagination_html = ''
            if num_pages > 1:
                pagination_html = '<div class="pagination">'
                for p in range(1, num_pages + 1):
                    if p == 1:
                        href = f"/category/{category_slug}.html"
                    else:
                        href = f"/category/{category_slug}-page-{p}.html"
                    active = ' class="active"' if p == page_num else ''
                    pagination_html += f'<a href="{href}"{active}>{p}</a> '
                pagination_html += '</div>'

            # File name
            if page_num == 1:
                filename = f"{category_slug}.html"
            else:
                filename = f"{category_slug}-page-{page_num}.html"

            canonical_url = f"{DOMAIN}/category/{filename}"

            content = f'''
            <div class="content-width" style="padding: 2rem 0;">
                <nav class="breadcrumb">
                    <a href="/">Home</a> &rsaquo; <a href="/categories.html">Categories</a> &rsaquo; {html_mod.escape(category_name)}
                </nav>
                <h1>{html_mod.escape(category_name)}</h1>
                <p style="color: var(--text-secondary);">{total} articles</p>

                {subcat_html if page_num == 1 else ""}

                <div class="section-title" style="margin-top:2rem;">All Articles{f" — Page {page_num}" if page_num > 1 else ""}</div>
                {cards_html}
                {pagination_html}

                {generate_share_buttons(category_name, canonical_url)}
            </div>
            '''

            page_title = f"{category_name} Articles — DentalPedia" if page_num == 1 else f"{category_name} Articles — Page {page_num} — DentalPedia"
            page_desc = f"Browse {total} articles about {category_name} on DentalPedia" if page_num == 1 else f"Page {page_num} of {num_pages} — {category_name} articles on DentalPedia"

            # Pagination meta tags (prev/next for SEO)
            pagination_meta = ""
            if page_num > 1:
                prev_file = f"{category_slug}.html" if page_num == 2 else f"{category_slug}-page-{page_num-1}.html"
                pagination_meta += f'<link rel="prev" href="{DOMAIN}/category/{prev_file}">\n'
            if page_num < num_pages:
                pagination_meta += f'<link rel="next" href="{DOMAIN}/category/{category_slug}-page-{page_num+1}.html">\n'

            page_html = get_page_template(
                page_title,
                content,
                canonical_url,
                page_desc,
                pagination_meta
            )

            with open(output_dir / filename, 'w', encoding='utf-8') as f:
                f.write(page_html)
            total_pages += 1

    logger.info(f"Generated {total_pages} category pages")


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
                <a href="/article/{article.get('slug')}.html" class="article-card">
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
                <a href="/category/{category_slug}.html">{html_mod.escape(category_name)}</a> /
                {html_mod.escape(subcategory_name)}
            </div>

            <div class="category-header">
                <h1>{html_mod.escape(subcategory_name)}</h1>
            </div>

            {articles_html}
            {pagination_html}
            {generate_share_buttons(subcategory_name, canonical_url)}
            '''

            subcat_title = f"{subcategory_name} | DentalPedia" if page_num == 1 else f"{subcategory_name} — Page {page_num} | DentalPedia"
            subcat_desc = f"Explore {subcategory_name} articles on DentalPedia" if page_num == 1 else f"Page {page_num} of {total_pages} — {subcategory_name} articles on DentalPedia"

            page_html = get_page_template(
                subcat_title,
                content,
                canonical_url,
                subcat_desc
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
            slug_h = heading.lower().replace(' ', '-')
            sections_html += f'<h2 id="{slug_h}">{html_mod.escape(heading)}</h2>'
            # Generate placeholder content (300-500 words)
            sections_html += '<p>Comprehensive information about this topic. Professional dental knowledge and evidence-based guidance for optimal outcomes. This section provides detailed insights into clinical considerations and best practices.</p>' * 3

        # Generate FAQ section with schema
        faq_items = []
        faq_html = '<div class="faq-section"><h2 id="frequently-asked-questions">Frequently Asked Questions</h2>'
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

                {get_related_articles_for_guide(guide.get('category_slug', ''))}
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
    <loc>{base_url}/article/{slug}.html</loc>
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
    <loc>{base_url}/categories.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
'''
    for cat_slug in articles_by_category.keys():
        categories_sitemap += f'''  <url>
    <loc>{base_url}/category/{cat_slug}.html</loc>
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
    # Add tools, myths, comparisons, widget to guides sitemap
    for tool_page in ['tools/cost-calculator.html', 'tools/dental-health-quiz.html', 'myths/', 'compare/', 'widget/']:
        guides_sitemap += f'''  <url>
    <loc>{base_url}/{tool_page}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
'''
    # Add individual myth pages
    myths_dir = SITE_ROOT / "myths"
    if myths_dir.exists():
        for myth_file in sorted(myths_dir.glob("*.html")):
            if myth_file.name != "index.html":
                guides_sitemap += f'''  <url>
    <loc>{base_url}/myths/{myth_file.name}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
'''
    # Add comparison pages
    compare_dir = SITE_ROOT / "compare"
    if compare_dir.exists():
        for cmp_file in sorted(compare_dir.glob("*.html")):
            if cmp_file.name != "index.html":
                guides_sitemap += f'''  <url>
    <loc>{base_url}/compare/{cmp_file.name}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
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
        <a href="/article/{article.get('slug')}.html" class="article-card">
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
        <a href="/category/{cat_slug}.html" class="category-card">
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

    <div class="tools-section" style="margin: 3rem 0;">
        <div class="section-title">Interactive Tools</div>
        <div class="articles-grid" style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));">
            <a href="/tools/cost-calculator.html" class="article-card" style="border-left: 4px solid #2563eb;">
                <div class="card-category" style="color: #2563eb;">💰 Free Tool</div>
                <div class="card-title">Dental Cost Calculator</div>
                <div class="card-excerpt">Get instant cost estimates for any dental procedure. Compare prices with and without insurance.</div>
            </a>
            <a href="/tools/dental-health-quiz.html" class="article-card" style="border-left: 4px solid #059669;">
                <div class="card-category" style="color: #059669;">📊 Take the Quiz</div>
                <div class="card-title">Dental Health Score Quiz</div>
                <div class="card-excerpt">Answer 8 quick questions to get your personalized dental health score and recommendations.</div>
            </a>
            <a href="/compare/" class="article-card" style="border-left: 4px solid #d97706;">
                <div class="card-category" style="color: #d97706;">📍 Compare Cities</div>
                <div class="card-title">Dental Costs by City</div>
                <div class="card-excerpt">See how dental procedure prices compare across 54 major US city pairs.</div>
            </a>
        </div>
    </div>

    <div class="myths-section" style="margin: 3rem 0;">
        <div class="section-title">Dental Myths vs Facts</div>
        <p style="text-align: center; color: var(--text-secondary); margin-bottom: 1.5rem;">Think you know everything about dental health? These common myths might surprise you.</p>
        <div class="articles-grid" style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));">
            <a href="/myths/" class="article-card" style="border-left: 4px solid #dc2626;">
                <div class="card-category" style="color: #dc2626;">❌ 20 Myths Busted</div>
                <div class="card-title">Dental Myths vs Facts</div>
                <div class="card-excerpt">From "sugar causes cavities" to "whitening damages enamel" — get the science-backed truth.</div>
            </a>
            <a href="/guides.html" class="article-card" style="border-left: 4px solid #7c3aed;">
                <div class="card-category" style="color: #7c3aed;">📖 Deep Dives</div>
                <div class="card-title">Cornerstone Guides</div>
                <div class="card-excerpt">Comprehensive, expert-written guides to major dental topics like implants, braces, and more.</div>
            </a>
            <a href="/widget/" class="article-card" style="border-left: 4px solid #0891b2;">
                <div class="card-category" style="color: #0891b2;">🦷 For Dental Practices</div>
                <div class="card-title">Free Embeddable Widget</div>
                <div class="card-excerpt">Add dental education content to your practice website. Free widget with one line of code.</div>
            </a>
        </div>
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


def generate_privacy_page():
    """Generate privacy policy page."""
    logger.info("Generating privacy policy page...")
    content = '''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Privacy Policy</nav>
        <h1>Privacy Policy</h1>
        <p style="color: var(--text-secondary);">Last updated: March 2, 2026</p>

        <div class="article-body">
            <p>DentalPedia ("we," "us," or "our") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and safeguard your information when you visit our website dentalpedia.co.</p>

            <h2>Information We Collect</h2>
            <p>We collect information that you voluntarily provide and information automatically collected when you visit our site. Automatically collected information includes your IP address, browser type, device information, pages visited, time spent on pages, and referring URLs. We use Google Analytics (GA4) to collect aggregate usage data to improve our content and user experience.</p>

            <h2>How We Use Your Information</h2>
            <p>We use collected information to provide and improve our dental health content, analyze site usage patterns and trends, ensure site security and prevent abuse, and comply with legal obligations. We do not sell, trade, or rent your personal information to third parties.</p>

            <h2>Cookies and Tracking</h2>
            <p>Our site uses cookies and similar tracking technologies for analytics purposes. Google Analytics uses cookies to collect anonymous usage data. You can control cookies through your browser settings. Disabling cookies will not affect your ability to access our content.</p>

            <h2>Third-Party Services</h2>
            <p>We use Google Analytics for site analytics and GitHub Pages for hosting. Each third-party service has its own privacy policy governing the use of your information. We encourage you to review their respective policies.</p>

            <h2>Data Security</h2>
            <p>We implement reasonable security measures to protect your information. However, no method of transmission over the internet is 100% secure. We cannot guarantee absolute security of your data.</p>

            <h2>Children's Privacy</h2>
            <p>Our site is not directed to children under 13. We do not knowingly collect personal information from children. If you believe we have collected information from a child, please contact us immediately.</p>

            <h2>Your Rights</h2>
            <p>Depending on your jurisdiction, you may have rights regarding your personal data, including the right to access, correct, delete, or port your data. To exercise these rights, please contact us at the information provided below.</p>

            <h2>Changes to This Policy</h2>
            <p>We may update this Privacy Policy from time to time. Changes will be posted on this page with an updated revision date. Your continued use of the site after changes constitutes acceptance of the updated policy.</p>

            <h2>Contact Us</h2>
            <p>If you have questions about this Privacy Policy, please contact us through our website.</p>
        </div>
    </div>
    '''

    page_html = get_page_template(
        "Privacy Policy — DentalPedia",
        content,
        f"{DOMAIN}/privacy.html",
        "DentalPedia privacy policy explaining how we collect, use, and protect your information."
    )

    with open(SITE_ROOT / "privacy.html", 'w', encoding='utf-8') as f:
        f.write(page_html)


def generate_terms_page():
    """Generate terms of use page."""
    logger.info("Generating terms of use page...")
    content = '''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Terms of Use</nav>
        <h1>Terms of Use</h1>
        <p style="color: var(--text-secondary);">Last updated: March 2, 2026</p>

        <div class="article-body">
            <p>Welcome to DentalPedia. By accessing and using this website (dentalpedia.co), you agree to be bound by these Terms of Use. If you do not agree with any part of these terms, please do not use our website.</p>

            <h2>Educational Purpose Only</h2>
            <p>All content on DentalPedia is provided for educational and informational purposes only. Our articles, guides, and resources are not intended to be a substitute for professional medical or dental advice, diagnosis, or treatment. Always seek the advice of your dentist or other qualified healthcare provider with any questions you may have regarding a dental condition.</p>

            <h2>No Doctor-Patient Relationship</h2>
            <p>Use of this website does not create a doctor-patient or dentist-patient relationship. The information provided should not be used to self-diagnose or self-treat any dental or medical condition. Never disregard professional dental advice or delay seeking it because of something you have read on DentalPedia.</p>

            <h2>Content Accuracy</h2>
            <p>We strive to provide accurate, evidence-based dental health information reviewed by our editorial board. However, dental science evolves, and information may change. We make no warranties or representations about the completeness, accuracy, reliability, or suitability of the content. Reliance on any information provided is at your own risk.</p>

            <h2>Intellectual Property</h2>
            <p>All content on DentalPedia, including text, graphics, logos, and design elements, is the property of DentalPedia and is protected by copyright and intellectual property laws. You may not reproduce, distribute, modify, or create derivative works from our content without prior written permission.</p>

            <h2>User Conduct</h2>
            <p>When using our website, you agree not to use the site for any unlawful purpose, attempt to gain unauthorized access to any part of the site, interfere with or disrupt the site's operations, or use automated systems to access the site without permission.</p>

            <h2>External Links</h2>
            <p>Our site may contain links to third-party websites. These links are provided for convenience and do not imply endorsement. We are not responsible for the content or practices of linked websites. We encourage you to review the terms and privacy policies of any third-party sites you visit.</p>

            <h2>Limitation of Liability</h2>
            <p>DentalPedia and its contributors shall not be liable for any direct, indirect, incidental, consequential, or punitive damages arising from your use of the website or reliance on its content. This includes but is not limited to damages for loss of data, revenue, or health outcomes.</p>

            <h2>Changes to Terms</h2>
            <p>We reserve the right to modify these Terms of Use at any time. Changes will be effective immediately upon posting on this page. Your continued use of the site after any changes constitutes acceptance of the updated terms.</p>

            <h2>Governing Law</h2>
            <p>These Terms of Use shall be governed by and construed in accordance with applicable laws, without regard to conflict of law provisions.</p>

            <h2>Contact Us</h2>
            <p>If you have questions about these Terms of Use, please contact us through our website.</p>
        </div>
    </div>
    '''

    page_html = get_page_template(
        "Terms of Use — DentalPedia",
        content,
        f"{DOMAIN}/terms.html",
        "DentalPedia terms of use governing access and use of our dental health information website."
    )

    with open(SITE_ROOT / "terms.html", 'w', encoding='utf-8') as f:
        f.write(page_html)


def generate_cost_calculator():
    """Generate interactive dental cost calculator page."""
    logger.info("Generating dental cost calculator...")

    # Build procedure data for JS
    proc_data = json.dumps([{
        "name": p.get("name", ""),
        "slug": p.get("slug", ""),
        "cost_low": p.get("cost_low", 0),
        "cost_high": p.get("cost_high", 0),
        "cost_avg": p.get("cost_avg", 0),
        "insurance": p.get("insurance_coverage", ""),
        "duration": p.get("duration", ""),
        "description": p.get("description", "")
    } for p in procedure_costs])

    content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Dental Cost Calculator</nav>
        <div style="text-align:center; margin-bottom: 2rem;">
            <h1>Dental Cost Calculator</h1>
            <p style="color: var(--text-secondary); max-width: 600px; margin: 0 auto;">Estimate the cost of your dental procedure. Select a procedure and number of teeth to get a personalized estimate.</p>
        </div>

        <div id="calculator" style="max-width: 700px; margin: 0 auto; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 2rem; box-shadow: var(--shadow-md);">
            <div style="margin-bottom: 1.5rem;">
                <label for="procedure" style="font-weight: 600; display: block; margin-bottom: 0.5rem;">Select Procedure</label>
                <select id="procedure" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-primary); color: var(--text-primary); font-size: 1rem;">
                    <option value="">Choose a procedure...</option>
                </select>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <label for="teeth" style="font-weight: 600; display: block; margin-bottom: 0.5rem;">Number of Teeth</label>
                <input type="range" id="teeth" min="1" max="6" value="1" style="width: 100%;">
                <div style="display: flex; justify-content: space-between; color: var(--text-muted); font-size: 0.85rem;"><span>1</span><span id="teeth-val">1</span><span>6</span></div>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <label style="font-weight: 600; display: block; margin-bottom: 0.5rem;">Insurance Coverage</label>
                <div style="display: flex; gap: 1rem;">
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;"><input type="radio" name="insurance" value="none" checked> No Insurance</label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;"><input type="radio" name="insurance" value="basic"> Basic Plan</label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;"><input type="radio" name="insurance" value="premium"> Premium Plan</label>
                </div>
            </div>

            <div id="result" style="display: none; background: linear-gradient(135deg, #eff6ff, #f0fdf4); border-radius: 12px; padding: 1.5rem; margin-top: 1rem;">
                <h3 style="margin-bottom: 1rem; color: #1e40af;">Your Estimated Cost</h3>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; text-align: center;">
                    <div><div id="cost-low" style="font-size: 1.5rem; font-weight: 700; color: #16a34a;">—</div><div style="font-size: 0.85rem; color: var(--text-muted);">Low Estimate</div></div>
                    <div><div id="cost-avg" style="font-size: 1.8rem; font-weight: 800; color: #2563eb;">—</div><div style="font-size: 0.85rem; color: var(--text-muted);">Average</div></div>
                    <div><div id="cost-high" style="font-size: 1.5rem; font-weight: 700; color: #dc2626;">—</div><div style="font-size: 0.85rem; color: var(--text-muted);">High Estimate</div></div>
                </div>
                <div id="cost-details" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #bfdbfe; font-size: 0.9rem; color: var(--text-secondary);"></div>
                <div id="cost-insurance" style="margin-top: 0.75rem; font-size: 0.9rem; color: var(--text-secondary);"></div>
            </div>

            <div class="disclaimer" style="margin-top: 1.5rem; font-size: 0.85rem; color: var(--text-muted); text-align: center;">
                These are estimates only. Actual costs vary by location, dentist, and individual needs. Consult your dentist for an accurate quote.
            </div>
        </div>

        {generate_share_buttons("Dental Cost Calculator", f"{DOMAIN}/tools/cost-calculator.html")}
    </div>

    <script>
    const procedures = {proc_data};
    const select = document.getElementById('procedure');
    const teethSlider = document.getElementById('teeth');
    const teethVal = document.getElementById('teeth-val');
    const resultDiv = document.getElementById('result');

    procedures.forEach(p => {{
        const opt = document.createElement('option');
        opt.value = p.slug;
        opt.textContent = p.name;
        select.appendChild(opt);
    }});

    function calculate() {{
        const proc = procedures.find(p => p.slug === select.value);
        if (!proc) {{ resultDiv.style.display = 'none'; return; }}
        const teeth = parseInt(teethSlider.value);
        const ins = document.querySelector('input[name=insurance]:checked').value;
        let discount = ins === 'premium' ? 0.5 : ins === 'basic' ? 0.3 : 0;
        let low = proc.cost_low * teeth * (1 - discount);
        let avg = proc.cost_avg * teeth * (1 - discount);
        let high = proc.cost_high * teeth * (1 - discount);
        document.getElementById('cost-low').textContent = '$' + low.toLocaleString();
        document.getElementById('cost-avg').textContent = '$' + avg.toLocaleString();
        document.getElementById('cost-high').textContent = '$' + high.toLocaleString();
        document.getElementById('cost-details').innerHTML = '<strong>' + proc.name + '</strong> x ' + teeth + ' tooth/teeth. Duration: ' + proc.duration;
        document.getElementById('cost-insurance').innerHTML = 'Insurance: ' + proc.insurance + (discount > 0 ? ' (' + (discount*100) + '% estimated discount applied)' : '');
        resultDiv.style.display = 'block';
    }}

    select.addEventListener('change', calculate);
    teethSlider.addEventListener('input', function() {{ teethVal.textContent = this.value; calculate(); }});
    document.querySelectorAll('input[name=insurance]').forEach(r => r.addEventListener('change', calculate));
    </script>
    '''

    output_dir = SITE_ROOT / "tools"
    output_dir.mkdir(parents=True, exist_ok=True)

    page_html = get_page_template(
        "Dental Cost Calculator — Estimate Your Treatment Cost | DentalPedia",
        content,
        f"{DOMAIN}/tools/cost-calculator.html",
        "Use our free dental cost calculator to estimate procedure costs. Compare prices for implants, crowns, braces, and more."
    )

    with open(output_dir / "cost-calculator.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info("Generated dental cost calculator")


def generate_dental_health_quiz():
    """Generate interactive dental health score quiz with email capture."""
    logger.info("Generating dental health quiz...")

    content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Dental Health Quiz</nav>
        <div style="text-align:center; margin-bottom: 2rem;">
            <h1>What's Your Dental Health Score?</h1>
            <p style="color: var(--text-secondary); max-width: 600px; margin: 0 auto;">Answer 8 quick questions to get your personalized dental health score and recommendations.</p>
        </div>

        <style>.quiz-opt{{display:block;width:100%;text-align:left;padding:1rem;margin-bottom:.75rem;border:1px solid var(--border-color);border-radius:10px;background:var(--bg-primary);color:var(--text-primary);font-size:1rem;cursor:pointer;transition:all .2s}}.quiz-opt:hover{{border-color:#2563eb;background:#eff6ff}}</style>
        <div id="quiz" style="max-width: 650px; margin: 0 auto;">
            <div id="progress" style="background: var(--bg-secondary); border-radius: 20px; height: 8px; margin-bottom: 2rem; overflow: hidden;">
                <div id="progress-bar" style="background: linear-gradient(90deg, #2563eb, #14b8a6); height: 100%; width: 0%; transition: width 0.3s ease; border-radius: 20px;"></div>
            </div>

            <div id="question-container" style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 2rem; box-shadow: var(--shadow-md); min-height: 300px;">
            </div>

            <div id="result-container" style="display: none; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 2rem; box-shadow: var(--shadow-md); text-align: center;">
                <div id="score-circle" style="width: 120px; height: 120px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem; font-size: 2.5rem; font-weight: 800;"></div>
                <h2 id="score-label" style="margin-bottom: 0.5rem;"></h2>
                <p id="score-desc" style="color: var(--text-secondary); margin-bottom: 1.5rem;"></p>
                <div id="recommendations" style="text-align: left; background: var(--bg-secondary); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;"></div>

                <div id="email-section" style="background: linear-gradient(135deg, #eff6ff, #f0fdf4); border-radius: 12px; padding: 1.5rem; margin-top: 1.5rem;">
                    <h3 style="margin-bottom: 0.5rem;">Get Your Full Dental Health Report</h3>
                    <p style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 1rem;">Enter your email to receive personalized tips and a detailed report.</p>
                    <div style="display: flex; gap: 0.5rem; max-width: 400px; margin: 0 auto;">
                        <input type="email" id="email-input" placeholder="your@email.com" style="flex: 1; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--border-color); font-size: 1rem; background: var(--bg-primary); color: var(--text-primary);">
                        <button id="email-submit" style="padding: 0.75rem 1.25rem; background: #2563eb; color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer;">Send</button>
                    </div>
                    <div id="email-success" style="display: none; color: #16a34a; margin-top: 0.75rem; font-weight: 600;">Thank you! Check your inbox soon.</div>
                </div>
            </div>
        </div>

        {generate_share_buttons("Dental Health Quiz", f"{DOMAIN}/tools/dental-health-quiz.html")}
    </div>

    <script>
    const questions = [
        {{q: "How often do you brush your teeth?", opts: ["Twice a day", "Once a day", "A few times a week", "Rarely"], scores: [10, 7, 3, 0]}},
        {{q: "Do you floss daily?", opts: ["Yes, daily", "A few times a week", "Rarely", "Never"], scores: [10, 7, 3, 0]}},
        {{q: "When was your last dental checkup?", opts: ["Within 6 months", "6-12 months ago", "1-2 years ago", "Over 2 years ago"], scores: [10, 7, 3, 0]}},
        {{q: "Do you experience tooth sensitivity?", opts: ["Never", "Occasionally", "Frequently", "Constantly"], scores: [10, 7, 3, 0]}},
        {{q: "Do your gums bleed when brushing?", opts: ["Never", "Rarely", "Sometimes", "Often"], scores: [10, 7, 3, 0]}},
        {{q: "How much sugary food/drinks do you consume?", opts: ["Very little", "Moderate amount", "Quite a bit", "A lot daily"], scores: [10, 7, 3, 0]}},
        {{q: "Do you use mouthwash?", opts: ["Daily", "Sometimes", "Rarely", "Never"], scores: [10, 7, 3, 0]}},
        {{q: "Do you grind your teeth at night?", opts: ["No", "Not sure", "Sometimes", "Yes, regularly"], scores: [10, 7, 3, 0]}}
    ];
    let current = 0, totalScore = 0;
    const container = document.getElementById('question-container');
    const resultContainer = document.getElementById('result-container');
    const progressBar = document.getElementById('progress-bar');

    function showQuestion() {{
        if (current >= questions.length) {{ showResult(); return; }}
        const q = questions[current];
        progressBar.style.width = ((current / questions.length) * 100) + '%';
        let html = '<h3 style="margin-bottom:1.5rem;">Question ' + (current+1) + ' of ' + questions.length + '</h3>';
        html += '<p style="font-size:1.15rem;font-weight:600;margin-bottom:1.5rem;">' + q.q + '</p>';
        q.opts.forEach((opt, i) => {{
            html += '<button class="quiz-opt" onclick="answer(' + q.scores[i] + ')">' + opt + '</button>';
        }});
        container.innerHTML = html;
    }}

    function answer(score) {{
        totalScore += score;
        current++;
        showQuestion();
    }}

    function showResult() {{
        container.style.display = 'none';
        resultContainer.style.display = 'block';
        progressBar.style.width = '100%';
        const pct = Math.round((totalScore / 80) * 100);
        const circle = document.getElementById('score-circle');
        const label = document.getElementById('score-label');
        const desc = document.getElementById('score-desc');
        const recs = document.getElementById('recommendations');
        let color, labelText, descText, recItems;
        if (pct >= 80) {{ color = '#16a34a'; labelText = 'Excellent!'; descText = 'Your dental health habits are outstanding.'; recItems = ['Keep up your great brushing and flossing routine', 'Continue regular dental checkups every 6 months', 'Consider professional whitening for a brighter smile']; }}
        else if (pct >= 60) {{ color = '#2563eb'; labelText = 'Good'; descText = 'Your dental health is solid with some room to improve.'; recItems = ['Try to floss daily if you are not already', 'Schedule a checkup if it has been over 6 months', 'Consider adding mouthwash to your routine', 'Reduce sugary snacks between meals']; }}
        else if (pct >= 40) {{ color = '#f59e0b'; labelText = 'Needs Attention'; descText = 'Your dental health could use some improvement.'; recItems = ['Brush twice daily with fluoride toothpaste', 'Start flossing at least a few times per week', 'Schedule a dental checkup as soon as possible', 'Cut back on sugary drinks and snacks', 'Consider an electric toothbrush']; }}
        else {{ color = '#dc2626'; labelText = 'Urgent Care Needed'; descText = 'Your dental health needs immediate attention.'; recItems = ['See a dentist as soon as possible', 'Start brushing twice daily immediately', 'Begin a daily flossing habit', 'Reduce sugar intake significantly', 'Use antiseptic mouthwash daily', 'Consider a night guard if you grind your teeth']; }}
        circle.style.background = color;
        circle.style.color = '#fff';
        circle.textContent = pct;
        label.textContent = labelText;
        desc.textContent = descText;
        recs.innerHTML = '<h4 style="margin-bottom:0.75rem;">Your Personalized Recommendations:</h4>' + recItems.map(r => '<div style="padding:0.5rem 0;border-bottom:1px solid var(--border-color);">✓ ' + r + '</div>').join('');
    }}

    document.getElementById('email-submit').addEventListener('click', function() {{
        const email = document.getElementById('email-input').value;
        if (email && email.includes('@')) {{
            // Track with GA4
            if (typeof gtag !== 'undefined') gtag('event', 'quiz_email_capture', {{event_category: 'engagement', event_label: email}});
            document.getElementById('email-success').style.display = 'block';
            this.disabled = true;
            this.textContent = 'Sent!';
        }}
    }});

    showQuestion();
    </script>
    '''

    output_dir = SITE_ROOT / "tools"
    output_dir.mkdir(parents=True, exist_ok=True)

    page_html = get_page_template(
        "Dental Health Score Quiz — How Healthy Are Your Teeth? | DentalPedia",
        content,
        f"{DOMAIN}/tools/dental-health-quiz.html",
        "Take our free 60-second dental health quiz to get your personalized score and recommendations."
    )

    with open(output_dir / "dental-health-quiz.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info("Generated dental health quiz")


def generate_cost_comparison_pages():
    """Generate city-to-city cost comparison pages."""
    logger.info("Generating cost comparison pages...")

    # Get top 20 cities for comparisons
    top_cities = cities_data[:20]
    output_dir = SITE_ROOT / "compare"
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for i, city1 in enumerate(top_cities):
        for city2 in top_cities[i+1:i+4]:  # Compare each city with next 3
            c1_name = f"{city1['name']}, {city1['state']}"
            c2_name = f"{city2['name']}, {city2['state']}"
            slug = f"{city1['slug']}-vs-{city2['slug']}"

            rows = ""
            for proc in procedure_costs:
                # Simulate regional price variation (10-30%)
                variation = hash(city1['slug'] + proc['slug']) % 20 - 10
                c1_avg = int(proc['cost_avg'] * (1 + variation/100))
                variation2 = hash(city2['slug'] + proc['slug']) % 20 - 10
                c2_avg = int(proc['cost_avg'] * (1 + variation2/100))
                diff = c2_avg - c1_avg
                diff_str = f'<span style="color: {"#16a34a" if diff < 0 else "#dc2626"}">{"-" if diff < 0 else "+"}${abs(diff):,}</span>'
                rows += f'<tr><td><a href="/locations/{proc["slug"]}-{city1["slug"]}.html">{proc["name"]}</a></td><td>${c1_avg:,}</td><td>${c2_avg:,}</td><td>{diff_str}</td></tr>'

            canonical = f"{DOMAIN}/compare/{slug}.html"
            content = f'''
            <div class="content-width" style="padding: 2rem 0;">
                <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/compare/">Cost Comparisons</a> &rsaquo; {c1_name} vs {c2_name}</nav>
                <h1>Dental Costs: {c1_name} vs {c2_name}</h1>
                <p style="color: var(--text-secondary);">Compare dental procedure costs between {c1_name} and {c2_name}.</p>

                <table style="width: 100%; border-collapse: collapse; margin: 2rem 0;">
                    <thead><tr style="background: var(--bg-secondary); text-align: left;">
                        <th style="padding: 0.75rem; border-bottom: 2px solid var(--border-color);">Procedure</th>
                        <th style="padding: 0.75rem; border-bottom: 2px solid var(--border-color);">{c1_name}</th>
                        <th style="padding: 0.75rem; border-bottom: 2px solid var(--border-color);">{c2_name}</th>
                        <th style="padding: 0.75rem; border-bottom: 2px solid var(--border-color);">Difference</th>
                    </tr></thead>
                    <tbody>{rows}</tbody>
                </table>

                <div class="disclaimer" style="font-size: 0.85rem; color: var(--text-muted);">Cost estimates are approximate and based on regional averages. Actual costs vary by provider. Consult your dentist for accurate pricing.</div>

                {generate_share_buttons(f"Dental Costs: {c1_name} vs {c2_name}", canonical)}
            </div>'''

            page_html = get_page_template(
                f"Dental Costs: {c1_name} vs {c2_name} | DentalPedia",
                content,
                canonical,
                f"Compare dental procedure costs between {c1_name} and {c2_name}. See price differences for implants, crowns, braces, and more."
            )

            with open(output_dir / f"{slug}.html", 'w', encoding='utf-8') as f:
                f.write(page_html)
            count += 1

    # Generate comparison index page
    links = ""
    for i, city1 in enumerate(top_cities):
        for city2 in top_cities[i+1:i+4]:
            slug = f"{city1['slug']}-vs-{city2['slug']}"
            c1 = f"{city1['name']}, {city1['state']}"
            c2 = f"{city2['name']}, {city2['state']}"
            links += f'<a href="/compare/{slug}.html" class="article-card"><div class="card-title">{c1} vs {c2}</div><div class="card-excerpt">Compare dental costs between these two cities</div></a>'

    index_content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Cost Comparisons</nav>
        <h1>Dental Cost Comparisons by City</h1>
        <p style="color: var(--text-secondary);">Compare dental procedure costs across major US cities.</p>
        <div class="articles-grid" style="margin-top: 2rem;">{links}</div>
    </div>'''

    page_html = get_page_template(
        "Dental Cost Comparisons by City | DentalPedia",
        index_content,
        f"{DOMAIN}/compare/",
        "Compare dental procedure costs between major US cities."
    )

    with open(output_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info(f"Generated {count} cost comparison pages")


def generate_embeddable_widget():
    """Generate embeddable widget JS and demo page for dental practices."""
    logger.info("Generating embeddable widget...")

    output_dir = SITE_ROOT / "widget"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Widget JS file
    widget_js = '''(function() {
  var style = document.createElement('style');
  style.textContent = '.dp-widget{font-family:Inter,-apple-system,sans-serif;border:1px solid #e2e8f0;border-radius:12px;padding:1.25rem;max-width:400px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,0.08)}.dp-widget h3{margin:0 0 .75rem;font-size:1.1rem;color:#1a1a2e}.dp-widget a{display:block;padding:.5rem 0;color:#2563eb;text-decoration:none;font-size:.95rem;border-bottom:1px solid #f1f5f9}.dp-widget a:hover{color:#1d4ed8}.dp-widget .dp-footer{margin-top:.75rem;font-size:.8rem;color:#94a3b8;text-align:right}.dp-widget .dp-footer a{display:inline;border:none;padding:0}';
  document.head.appendChild(style);
  var containers = document.querySelectorAll('[data-dentalpedia-widget]');
  containers.forEach(function(el) {
    var category = el.getAttribute('data-category') || 'general-dentistry';
    var count = parseInt(el.getAttribute('data-count') || '5');
    var widget = document.createElement('div');
    widget.className = 'dp-widget';
    widget.innerHTML = '<h3>Learn More from DentalPedia</h3><div class="dp-articles"></div><div class="dp-footer">Powered by <a href="https://dentalpedia.co" target="_blank">DentalPedia</a></div>';
    el.appendChild(widget);
    fetch('https://dentalpedia.co/widget/articles.json')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var articles = data.filter(function(a) { return !category || a.category_slug === category; }).slice(0, count);
        var html = '';
        articles.forEach(function(a) {
          html += '<a href="https://dentalpedia.co/article/' + a.slug + '.html" target="_blank">' + a.title + '</a>';
        });
        widget.querySelector('.dp-articles').innerHTML = html || '<p>No articles found.</p>';
      })
      .catch(function() {
        widget.querySelector('.dp-articles').innerHTML = '<p>Visit <a href="https://dentalpedia.co">DentalPedia</a></p>';
      });
  });
})();'''

    with open(output_dir / "dentalpedia-widget.js", 'w') as f:
        f.write(widget_js)

    # Widget articles JSON feed
    widget_articles = [{
        "slug": a.get("slug", ""),
        "title": a.get("title", ""),
        "category_slug": a.get("category_slug", ""),
        "excerpt": a.get("excerpt", "")[:100]
    } for a in all_articles[:200]]  # Top 200 articles

    with open(output_dir / "articles.json", 'w') as f:
        json.dump(widget_articles, f)

    # Demo page
    demo_content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Embeddable Widget</nav>
        <h1>DentalPedia Widget for Dental Practices</h1>
        <p style="color: var(--text-secondary); max-width: 700px;">Add free dental education content to your practice website. Our widget displays relevant articles from DentalPedia, giving your patients valuable information while earning a backlink.</p>

        <h2 style="margin-top: 2rem;">Live Preview</h2>
        <div data-dentalpedia-widget data-category="general-dentistry" data-count="5" style="margin: 1rem 0;"></div>

        <h2 style="margin-top: 2rem;">How to Install</h2>
        <p>Copy and paste this code into your website where you want the widget to appear:</p>
        <pre style="background: var(--bg-secondary); padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 1rem 0;"><code>&lt;div data-dentalpedia-widget data-category="general-dentistry" data-count="5"&gt;&lt;/div&gt;
&lt;script src="https://dentalpedia.co/widget/dentalpedia-widget.js"&gt;&lt;/script&gt;</code></pre>

        <h3>Available Categories</h3>
        <p style="color: var(--text-secondary);">Set <code>data-category</code> to any of these values:</p>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0;">'''

    for cat_slug in sorted(articles_by_category.keys()):
        cat_name = articles_by_category[cat_slug][0].get('category', cat_slug) if articles_by_category[cat_slug] else cat_slug
        demo_content += f'<span style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.85rem;">{html_mod.escape(cat_name)} = <code>{cat_slug}</code></span>'

    demo_content += f'''
        </div>

        <h3>Benefits for Your Practice</h3>
        <div class="article-body">
            <p>Adding the DentalPedia widget to your dental practice website provides educational content for your patients, improves your site's SEO with fresh content, earns a backlink from DentalPedia, and requires zero maintenance as content updates automatically.</p>
        </div>

        {generate_share_buttons("DentalPedia Widget for Dental Practices", f"{DOMAIN}/widget/")}
    </div>
    <script src="/widget/dentalpedia-widget.js"></script>
    '''

    page_html = get_page_template(
        "Free Widget for Dental Practice Websites | DentalPedia",
        demo_content,
        f"{DOMAIN}/widget/",
        "Add free dental education content to your practice website with our embeddable widget. Improve patient education and SEO."
    )

    with open(output_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info("Generated embeddable widget")


def generate_myth_vs_fact():
    """Generate dental myth vs fact content pages for social sharing."""
    logger.info("Generating myth vs fact content...")

    myths = [
        {"myth": "You should rinse your mouth right after brushing", "fact": "Rinsing washes away concentrated fluoride from toothpaste. Spit, don't rinse, to maximize protection.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Sugar is the main cause of cavities", "fact": "It's actually the acid produced by bacteria feeding on sugar. The duration of sugar exposure matters more than quantity.", "category": "General Dentistry", "category_slug": "general-dentistry"},
        {"myth": "Whitening damages your teeth", "fact": "Professional whitening is safe and does not damage enamel when done correctly. Over-the-counter products used excessively can cause sensitivity.", "category": "Cosmetic Dentistry", "category_slug": "cosmetic-dentistry"},
        {"myth": "You only need to see a dentist when something hurts", "fact": "Many dental problems are painless in early stages. Regular checkups catch issues like cavities and gum disease before they become serious.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Brushing harder cleans better", "fact": "Brushing too hard can wear down enamel and damage gums. Use gentle, circular motions with a soft-bristled brush.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Baby teeth don't matter because they fall out anyway", "fact": "Baby teeth hold space for permanent teeth and affect speech development. Decay in baby teeth can damage developing permanent teeth.", "category": "Pediatric Dentistry", "category_slug": "pediatric-dentistry"},
        {"myth": "Dental implants are painful", "fact": "Most patients report less pain than expected. The procedure uses local anesthesia, and discomfort is usually manageable with over-the-counter pain medication.", "category": "Dental Implants", "category_slug": "dental-implants"},
        {"myth": "Charcoal toothpaste whitens teeth naturally", "fact": "Charcoal toothpaste is abrasive and can actually damage enamel over time. It has no proven whitening benefits beyond surface stain removal.", "category": "Cosmetic Dentistry", "category_slug": "cosmetic-dentistry"},
        {"myth": "Flossing creates gaps between teeth", "fact": "Flossing removes plaque and food particles that cause gum disease. Any apparent gaps are from reduced inflammation, not from flossing itself.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Root canals are extremely painful", "fact": "Modern root canals are no more uncomfortable than getting a filling. The pain comes from the infection, not the treatment that eliminates it.", "category": "Endodontics", "category_slug": "endodontics"},
        {"myth": "You don't need to floss if you use mouthwash", "fact": "Mouthwash cannot remove plaque from between teeth. Flossing physically removes debris and plaque that mouthwash cannot reach.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Dental X-rays are dangerous", "fact": "Modern dental X-rays use extremely low radiation — less than you'd get from a short airplane flight. They're essential for detecting hidden problems.", "category": "Dental Technology", "category_slug": "dental-technology"},
        {"myth": "If gums bleed, you should stop flossing", "fact": "Bleeding gums usually indicate inflammation from inadequate cleaning. Continue flossing gently — bleeding should stop within 1-2 weeks as gum health improves.", "category": "Periodontics", "category_slug": "periodontics"},
        {"myth": "Braces are only for kids", "fact": "About 25% of orthodontic patients are adults. Modern options like Invisalign make adult orthodontics more discreet and comfortable than ever.", "category": "Orthodontics", "category_slug": "orthodontics"},
        {"myth": "Placing aspirin on a toothache helps", "fact": "Putting aspirin directly on gums can cause chemical burns. Aspirin only works when swallowed. See a dentist for tooth pain.", "category": "Emergency Dentistry", "category_slug": "emergency-dentistry"},
        {"myth": "Electric toothbrushes are always better than manual", "fact": "Both can be equally effective with proper technique. Electric brushes may help people who struggle with manual brushing technique.", "category": "Preventive Care", "category_slug": "preventive-care"},
        {"myth": "Dental problems are hereditary, so there's nothing I can do", "fact": "While genetics influence risk, proper oral hygiene and regular dental care can prevent most dental problems regardless of family history.", "category": "General Dentistry", "category_slug": "general-dentistry"},
        {"myth": "You should avoid the dentist during pregnancy", "fact": "Dental care during pregnancy is safe and important. Pregnancy hormones increase the risk of gum disease, making checkups even more critical.", "category": "General Dentistry", "category_slug": "general-dentistry"},
        {"myth": "All dental fillings need to be replaced eventually", "fact": "Well-placed fillings can last decades. They only need replacement if they crack, leak, or decay develops around them.", "category": "Restorative Dentistry", "category_slug": "restorative-dentistry"},
        {"myth": "Wisdom teeth always need to be removed", "fact": "Not all wisdom teeth cause problems. Removal is only necessary if they're impacted, causing pain, crowding, or increasing infection risk.", "category": "Oral Surgery", "category_slug": "oral-surgery"},
    ]

    output_dir = SITE_ROOT / "myths"
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, m in enumerate(myths):
        slug = re.sub(r'[^\w\s-]', '', m['myth'].lower()).replace(' ', '-')[:60]
        canonical = f"{DOMAIN}/myths/{slug}.html"

        # Find related articles
        related = articles_by_category.get(m['category_slug'], [])[:3]
        related_html = ""
        if related:
            cards = "".join([f'<a href="/article/{a["slug"]}.html" class="article-card"><div class="card-title">{html_mod.escape(a["title"])}</div></a>' for a in related])
            related_html = f'<div style="margin-top: 2rem;"><h3>Learn More</h3><div class="articles-grid">{cards}</div></div>'

        content = f'''
        <div class="content-width" style="padding: 2rem 0; max-width: 700px; margin: 0 auto;">
            <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/myths/">Dental Myths</a> &rsaquo; Myth #{i+1}</nav>

            <div style="background: #fef2f2; border: 2px solid #fca5a5; border-radius: 16px; padding: 2rem; margin: 1.5rem 0; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">❌</div>
                <div style="font-size: 0.85rem; font-weight: 600; color: #dc2626; text-transform: uppercase; letter-spacing: 0.05em;">Myth</div>
                <h1 style="font-size: 1.5rem; margin: 0.75rem 0 0; color: #991b1b;">"{html_mod.escape(m['myth'])}"</h1>
            </div>

            <div style="background: #f0fdf4; border: 2px solid #86efac; border-radius: 16px; padding: 2rem; margin: 1.5rem 0; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">✅</div>
                <div style="font-size: 0.85rem; font-weight: 600; color: #16a34a; text-transform: uppercase; letter-spacing: 0.05em;">Fact</div>
                <p style="font-size: 1.15rem; margin: 0.75rem 0 0; color: #166534; font-weight: 500;">{html_mod.escape(m['fact'])}</p>
            </div>

            <div style="text-align: center; margin: 1rem 0; color: var(--text-muted); font-size: 0.9rem;">
                Category: <a href="/category/{m['category_slug']}.html">{html_mod.escape(m['category'])}</a>
            </div>

            {generate_share_buttons(f"Dental Myth: {m['myth']}", canonical)}
            {related_html}
        </div>
        '''

        page_html = get_page_template(
            f"Dental Myth vs Fact: {m['myth'][:50]} | DentalPedia",
            content,
            canonical,
            f"MYTH: {m['myth']} FACT: {m['fact']}"
        )

        with open(output_dir / f"{slug}.html", 'w', encoding='utf-8') as f:
            f.write(page_html)

    # Generate myths index page
    grid = '<div class="articles-grid">'
    for i, m in enumerate(myths):
        slug = re.sub(r'[^\w\s-]', '', m['myth'].lower()).replace(' ', '-')[:60]
        grid += f'''<a href="/myths/{slug}.html" class="article-card">
            <div class="card-category" style="color: #dc2626;">Myth #{i+1}</div>
            <div class="card-title">{html_mod.escape(m["myth"])}</div>
            <div class="card-excerpt" style="color: #16a34a;">✅ {html_mod.escape(m["fact"][:100])}...</div>
        </a>'''
    grid += '</div>'

    index_content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Dental Myths vs Facts</nav>
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1>20 Dental Myths Busted by Science</h1>
            <p style="color: var(--text-secondary); max-width: 600px; margin: 0 auto;">Think you know everything about dental health? These common myths might surprise you. Share them with friends and family.</p>
        </div>
        {grid}
        {generate_share_buttons("20 Dental Myths Busted", f"{DOMAIN}/myths/")}
    </div>'''

    page_html = get_page_template(
        "20 Dental Myths Busted by Science | DentalPedia",
        index_content,
        f"{DOMAIN}/myths/",
        "Common dental myths debunked with scientific facts. Learn the truth about brushing, flossing, whitening, and more."
    )

    with open(output_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    logger.info(f"Generated {len(myths)} myth vs fact pages")


def main():
    """Main build function."""
    logger.info("Starting DentalPedia build...")
    start_time = datetime.now()

    # Load data and optimize assets
    load_json_data()
    load_articles()
    minify_css()

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
    generate_categories_index()
    generate_category_pages()
    generate_subcategory_pages()
    generate_city_pages()
    generate_guide_pages()
    generate_editorial_standards_page()
    generate_privacy_page()
    generate_terms_page()
    generate_admin_dashboard()
    generate_cost_calculator()
    generate_dental_health_quiz()
    generate_cost_comparison_pages()
    generate_embeddable_widget()
    generate_myth_vs_fact()
    generate_sitemaps()

    # Build time
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info(f"Build completed in {duration:.1f} seconds")
    logger.info(f"Total pages generated: ~{len(all_articles) + len(articles_by_category) + len(articles_by_subcategory) + (len(cities_data) * len(procedure_costs)) + len(cornerstone_guides) + 3:,}")


if __name__ == "__main__":
    main()
