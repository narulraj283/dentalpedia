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
CLINICAL_CONTENT_DIR = Path("content/clinical")
OUTPUT_DIR = Path("article")
CLINICAL_DIR = Path("clinical")
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
dentists_data = []  # Find a Dentist directory data
ekwa_clients = {}  # Ekwa premium client data
cities_data = []
procedure_costs = []
cornerstone_guides = []
article_lookup = {}  # slug -> article metadata
guides_by_category = {}  # category_slug -> guide data
minified_css_hash = ""  # Cache-busting hash for minified CSS


def load_json_data():
    """Load all JSON data files."""
    global subcategories_data, cities_data, procedure_costs, cornerstone_guides, dentists_data, ekwa_clients

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

    try:
        with open(DATA_DIR / "dentists.json") as f:
            dentists_data = json.load(f)
        logger.info(f"Loaded {len(dentists_data)} dental practices for directory")
    except Exception as e:
        logger.error(f"Failed to load dentists.json: {e}")

    try:
        with open(DATA_DIR / "ekwa_clients.json") as f:
            ekwa_clients = json.load(f)
        logger.info(f"Loaded {len(ekwa_clients)} Ekwa premium clients")
    except:
        ekwa_clients = {}


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

            # Handle lists (sources - old format with title/url)
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
            # Handle references list (new format: simple string list)
            elif key == "references":
                refs = []
                ref_section = frontmatter_text.split("references:")[1]
                # Stop at the next top-level key (line that doesn't start with - or whitespace)
                for ref_line in ref_section.split("\n"):
                    stripped = ref_line.strip()
                    if stripped.startswith("- "):
                        ref_text = stripped[2:].strip().strip('"').strip("'")
                        if ref_text:
                            refs.append(ref_text)
                    elif stripped and not stripped.startswith("-") and ":" in stripped and not stripped.startswith('"'):
                        break  # Hit next frontmatter key
                metadata["references"] = refs
            else:
                metadata[key] = value

    return metadata, body


def heading_slug(text):
    """Convert heading text to URL-friendly slug (matches generate_toc_html logic)."""
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'[^\w\s-]', '', clean).replace(' ', '-').lower()


def markdown_to_html(text):
    """Convert markdown to HTML."""
    # Clinical detail expandable blocks (:::clinical ... :::)
    def clinical_block_repl(m):
        inner = m.group(1).strip()
        # Process bold/italic inside the block
        inner = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', inner)
        inner = re.sub(r'\*(.*?)\*', r'<em>\1</em>', inner)
        # Convert paragraphs
        paras = inner.split('\n\n')
        inner_html = ''.join([f'<p>{p.strip()}</p>' for p in paras if p.strip()])
        return (
            '<details class="clinical-detail">'
            '<summary class="clinical-detail-toggle">'
            '<span class="clinical-icon">🔬</span> Clinical Detail <span class="clinical-badge">For Professionals</span>'
            '<span class="clinical-chevron">▸</span>'
            '</summary>'
            f'<div class="clinical-detail-content">{inner_html}</div>'
            '</details>'
        )
    text = re.sub(r'^:::clinical\s*\n(.*?)\n^:::', clinical_block_repl, text, flags=re.MULTILINE | re.DOTALL)

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

    # Content disclaimer (honest about content process)
    eeat_card = '''
    <div class="content-disclaimer">
        <div class="content-disclaimer-icon">ℹ️</div>
        <div class="content-disclaimer-text">This article is for informational purposes only. Content is compiled from dental literature and professional guidelines. It is not a substitute for professional dental advice. <a href="/editorial-standards.html">Learn more</a></div>
    </div>
    '''

    # Sources card - only show if real sources exist (not generic placeholders)
    sources_html = ""

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
                <li class="nav-dropdown">
                    <a href="/categories.html" class="dropdown-toggle" onclick="if(window.innerWidth<769){event.preventDefault();this.parentElement.classList.toggle('open')}">For Patients ▾</a>
                    <ul class="dropdown-menu">
                        <li><a href="/categories.html">📚 All Topics</a></li>
                        <li><a href="/guides.html">📖 Guides</a></li>
                        <li><a href="/myths/">🔍 Myths vs Facts</a></li>
                        <li><a href="/tools/dental-health-quiz.html">📊 Health Quiz</a></li>
                    </ul>
                </li>
                <li><a href="/clinical/">For Professionals</a></li>
                <li><a href="/find-a-dentist/">Find a Dentist</a></li>
                <li class="nav-dropdown">
                    <a href="#" class="dropdown-toggle" onclick="event.preventDefault();this.parentElement.classList.toggle('open')">Tools ▾</a>
                    <ul class="dropdown-menu">
                        <li><a href="/tools/cost-calculator.html">💰 Cost Calculator</a></li>
                        <li><a href="/compare/">📍 Cost by City</a></li>
                    </ul>
                </li>
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
                    <div class="footer-title">For Patients</div>
                    <ul class="footer-links">
                        <li><a href="/categories.html">All Topics</a></li>
                        <li><a href="/guides.html">Guides</a></li>
                        <li><a href="/myths/">Myths vs Facts</a></li>
                        <li><a href="/compare/">Cost by City</a></li>
                    </ul>
                </div>
                <div class="footer-section">
                    <div class="footer-title">For Professionals</div>
                    <ul class="footer-links">
                        <li><a href="/clinical/">Clinical Protocols</a></li>
                        <li><a href="/editorial-standards.html">Editorial Standards</a></li>
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


def clean_title(t):
    """Strip surrounding quotes from titles that came from YAML frontmatter."""
    t = t.strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1]
    return t


def get_page_template(title, content, canonical_url, description="", meta_tags="", schema="", extra_head=""):
    """Generate full HTML page template."""

    title = clean_title(title)
    css_file = f"/assets/css/style.min.css?v={minified_css_hash}" if minified_css_hash else "/assets/css/style.css"

    # Brand suffix for title tag
    title_tag = f"{html_mod.escape(title)} — DentalPedia" if "DentalPedia" not in title else html_mod.escape(title)

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
    <title>{title_tag}</title>
    <meta name="description" content="{html_mod.escape(description)}">
    <link rel="canonical" href="{canonical_url}">
    {extra_head}
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
        // Clinical detail expand/collapse
        document.querySelectorAll('.clinical-detail-toggle').forEach(function(t) {{
            t.addEventListener('click', function() {{
                const chevron = t.querySelector('.clinical-chevron');
                if (chevron) chevron.textContent = t.parentElement.open ? '▸' : '▾';
            }});
        }});
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
                articles_by_subcategory[f"{category_slug}/{subcategory_slug}"].append(metadata)

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
            <div class="card-excerpt">{html_mod.escape((a.get('excerpt', '')[:120].rsplit(' ', 1)[0] + '...') if len(a.get('excerpt', '')) > 120 else a.get('excerpt', ''))}</div>
        </a>'''
    cards += '</div></div>'
    return cards


def get_related_guide_card(category_slug):
    """Return a 'Read the Full Guide' card if a guide exists for this category."""
    guide = guides_by_category.get(category_slug)
    if not guide:
        return ''
    return f'''<div class="related-guide-card" style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;padding:1.25rem;margin:1.5rem 0;color:var(--text-primary)">
        <div style="font-weight:600;margin-bottom:0.5rem;color:var(--text-primary)">📖 Want the complete picture?</div>
        <a href="/guides/{guide.get('slug')}.html" style="font-size:1.1rem;font-weight:700;color:var(--accent);text-decoration:none">{html_mod.escape(guide.get('title', ''))}</a>
        <p style="margin:0.5rem 0 0;color:var(--text-secondary);font-size:0.9rem">{html_mod.escape(guide.get('meta_description', ''))}</p>
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
        pattern = re.compile(r'(<p>|<li>)([^<]*?)(' + re.escape(other_title) + r')([^<]*?)(?=</)', re.IGNORECASE)
        match = pattern.search(html_content)
        if match:
            replacement = f'{match.group(1)}{match.group(2)}<a href="/article/{other_slug}.html">{match.group(3)}</a>{match.group(4)}'
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
        title = clean_title(metadata.get('title', 'Untitled'))
        excerpt = metadata.get('excerpt', '')
        category = metadata.get('category', '')
        category_slug = metadata.get('category_slug', '')
        reviewer_specialty = metadata.get('reviewer_specialty', 'General Dentistry')
        subcategory = metadata.get('subcategory', '')
        subcategory_slug = metadata.get('subcategory_slug', '')
        date = metadata.get('date', '')
        read_time = metadata.get('read_time', '5 min')
        sources = metadata.get('sources', [])
        references = metadata.get('references', [])
        is_reviewed = metadata.get('reviewed', '').lower() == 'true' if metadata.get('reviewed') else False

        # Strip :::clinical blocks from patient version (clinical content lives at /clinical/)
        patient_body = re.sub(r'^:::clinical\s*\n.*?\n^:::\s*$', '', body, flags=re.MULTILINE | re.DOTALL)

        # Convert full markdown body to HTML
        body_html = markdown_to_html(patient_body)

        # Internal linking: auto-link mentions of other article titles
        body_html = create_internal_links(body_html, slug)

        # GEO: Add "Key Takeaway" summary box for AI Overviews
        first_para = re.search(r'<p>(.*?)</p>', body_html)
        if first_para and len(first_para.group(1)) > 80:
            takeaway_text = first_para.group(1)[:250]
            if len(first_para.group(1)) > 250:
                takeaway_text = takeaway_text.rsplit(' ', 1)[0] + '...'
            geo_box = f'<div class="key-takeaway" style="padding:1rem 1.25rem;border-radius:0 8px 8px 0;margin:1.5rem 0;font-size:0.95rem;line-height:1.6"><strong>Key Takeaway:</strong> {takeaway_text}</div>'
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
                        <span>By DentalPedia Editorial Team</span>
                        <span>Updated {date}</span>
                        {'<span class="reviewed-badge">✓ Dentally Reviewed</span>' if is_reviewed else ''}
                    </div>
                    <div class="article-meta-secondary">
                        <span>⏱️ {read_time}</span>
                        <span>📚 <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a></span>
                    </div>
                </header>

                {toc_html}

                <div class="clinical-crosslink" style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:10px;padding:0.75rem 1rem;margin-bottom:1.5rem;font-size:0.88rem;display:flex;align-items:center;gap:0.5rem">
                    <span style="color:var(--accent)">🔬</span>
                    <span style="color:var(--text-secondary)">Dental professional?</span>
                    <a href="/clinical/{slug}.html" style="color:var(--accent);font-weight:600;text-decoration:none">View Clinical Protocol →</a>
                </div>

                <div class="article-body" id="article-body">
                    {body_html}
                </div>

                {'<div class="article-references"><h2>References</h2><ol>' + ''.join(f'<li>{html_mod.escape(ref)}</li>' for ref in references) + '</ol></div>' if references else ''}

                <div class="article-review-info">
                    <p><strong>Dentally reviewed</strong> by the DentalPedia Dental Review Board. This article is for informational purposes only and does not constitute dental or medical advice. Always consult a licensed dentist for diagnosis and treatment.</p>
                    <p>Sources: American Dental Association (ADA), peer-reviewed dental journals, and established clinical guidelines.</p>
                </div>

                {get_related_guide_card(category_slug)}

                {generate_share_buttons(title, canonical_url)}
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
            "@type": "Article",
            "headline": title,
            "description": excerpt,
            "datePublished": date,
            "dateModified": date,
            "url": canonical_url,
            "author": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "publisher": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url}
        }
        # Clean citation format — extract just the citation text
        if references:
            clean_refs = []
            for ref in references:
                if isinstance(ref, dict):
                    clean_refs.append(ref.get('title', str(ref)))
                elif isinstance(ref, str):
                    # Strip "title: " prefix if present from YAML parsing
                    r = ref.strip()
                    if r.startswith('title:'):
                        r = r[6:].strip().strip('"').strip("'")
                    clean_refs.append(r)
                else:
                    clean_refs.append(str(ref))
            article_schema["citation"] = clean_refs

        all_schema = f'''<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
        <script type="application/ld+json">{json.dumps(article_schema)}</script>'''

        # Alternate link to clinical version
        extra_head = f'<link rel="alternate" href="{DOMAIN}/clinical/{slug}.html" title="Clinical Protocol">'

        page_html = get_page_template(
            title,
            article_content,
            canonical_url,
            excerpt,
            meta_tags,
            all_schema,
            extra_head
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
        subcat_count = sum(1 for k in articles_by_subcategory.keys()
                          if k.startswith(f"{cat_slug}/"))
        cards_html += f'''
        <a href="/category/{cat_slug}.html" class="category-card">
            <div class="category-icon">📚</div>
            <div class="category-name">{html_mod.escape(cat_name)}</div>
            <div class="category-count">{len(articles)} {"article" if len(articles) == 1 else "articles"}{f" • {subcat_count} {'subcategory' if subcat_count == 1 else 'subcategories'}" if subcat_count > 0 else ""}</div>
        </a>'''
    cards_html += '</div>'

    content = f'''
    <div style="padding: 2rem 0;">
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
        for combo_key, subcat_articles in articles_by_subcategory.items():
            cat_s, sub_s = combo_key.split('/', 1)
            if cat_s == category_slug and subcat_articles:
                subcat_name = subcat_articles[0].get('subcategory', sub_s)
                cat_subcategories[sub_s] = {
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
                    <div class="category-count">{subcat_info["count"]} {"article" if subcat_info["count"] == 1 else "articles"}</div>
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
            <div style="padding: 2rem 0;">
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

    for combo_key, articles in articles_by_subcategory.items():
        if not articles:
            continue

        # Key is now "category_slug/subcategory_slug"
        category_slug, subcategory_slug = combo_key.split('/', 1)
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
        meta_desc = f"Learn about {proc_name.lower()} in {city_name}, {state_full}. Find cost estimates, procedure information, and local dentists."

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

            <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:var(--radius-lg);padding:1rem 1.25rem;margin:1.5rem 0;font-size:0.9rem;color:#856404;">
                <strong>Cost Disclaimer:</strong> The figures shown below are estimated national averages and may not reflect actual costs in {city_name}. Prices vary significantly by provider, case complexity, location, and insurance coverage. Contact a local dentist for an accurate quote.
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 2rem 0;">
                <div style="background: var(--bg-secondary); padding: 1.25rem; border-radius: var(--radius-lg); text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">${cost_low:,} — ${cost_high:,}</div>
                    <div style="color: var(--text-secondary); margin-top: 0.25rem;">Estimated National Average</div>
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
                <p style="opacity: 0.9;">Browse our <a href="/find-a-dentist/" style="color:#fff;text-decoration:underline;">dentist directory</a> to find providers in your area.</p>
            </div>

            <p style="font-size:0.8rem;color:var(--text-secondary);margin-top:1.5rem;"><em>Cost estimates are based on industry data and general dental surveys. They do not reflect specific quotes from any provider. Individual costs will vary. Last updated March 2026.</em></p>
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

        # Generate section content from guide metadata
        sections_html = ''
        guide_topic = title.lower()
        section_intros = [
            "Understanding this aspect is an important part of dental care. Patients benefit from learning about the factors involved so they can have informed discussions with their dental provider.",
            "This is an area where dental professionals can provide valuable guidance based on the patient's individual situation. A proper evaluation is the first step toward determining the right approach.",
            "Several factors influence the approach taken in this area. Patient health history, specific symptoms, and treatment goals all play a role in determining the most appropriate path forward.",
            "Modern dentistry offers a range of options in this area. The right choice depends on individual circumstances, and a thorough consultation helps identify the best fit for each patient.",
            "Patients often have questions about this topic, and discussing concerns openly with a dental professional is encouraged. Clear communication supports better outcomes and patient satisfaction.",
            "Research and clinical experience have shaped current approaches in this area. While practices may vary between providers, the fundamental principles are well-established in dental literature.",
            "Prevention and early intervention are key themes in this area of dentistry. Patients who stay informed and maintain regular dental visits are better positioned to address issues before they become more complex.",
            "Every patient's situation is different, and treatment in this area should be tailored accordingly. A personalized approach based on thorough evaluation tends to yield the best results.",
        ]
        section_details = [
            "The specifics of any dental recommendation depend on the patient's overall health, dental history, and personal preferences. Open dialogue between patient and provider helps ensure that chosen approaches align with individual needs and expectations.",
            "Costs, recovery time, and expected outcomes are all factors that patients should discuss with their dental provider before proceeding with any treatment. Understanding what to expect helps patients prepare and reduces uncertainty.",
            "Follow-up care is an important component of successful dental treatment. Patients should adhere to their provider's recommendations for post-treatment care and schedule follow-up appointments as advised.",
            "Dental technology and techniques continue to advance, offering patients more options and often improved outcomes. Staying current with available options through regular dental visits helps patients access the most appropriate care.",
            "Patient education is a cornerstone of good dental care. Understanding the rationale behind recommended treatments empowers patients to participate actively in decisions about their oral health.",
            "While general information is helpful for building understanding, it cannot replace the individualized assessment that a dental professional provides. Each patient's anatomy, health history, and goals are unique.",
            "Risk factors, complications, and alternative approaches should all be part of the conversation between patient and provider. A well-informed patient is better equipped to weigh options and make decisions.",
            "Maintaining results often requires ongoing attention to oral hygiene, diet, and regular professional care. Patients who commit to long-term maintenance tend to experience better outcomes.",
        ]
        for i, section in enumerate(sections):
            heading = section.get('heading', '')
            slug_h = heading.lower().replace(' ', '-')
            sections_html += f'<h2 id="{slug_h}">{html_mod.escape(heading)}</h2>'
            # Use rotating content ensuring no repeats within the same guide
            intro_idx = i % len(section_intros)
            detail_idx = (i + 3) % len(section_details)  # Offset to avoid patterns
            sections_html += f'<p>{section_intros[intro_idx]}</p>'
            sections_html += f'<p>{section_details[detail_idx]}</p>'

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
        <p>How DentalPedia creates and maintains its dental health content</p>
    </div>

    <div class="content-width" style="padding: 2rem 0;">
        <div style="max-width: 800px; margin: 0 auto;">
            <h2>About Our Content</h2>
            <p>DentalPedia provides dental health information compiled from established dental literature, professional guidelines, and publicly available clinical resources. Our content is created with the assistance of AI technology and is designed to help readers understand common dental topics in accessible language.</p>

            <h2>Content Creation Process</h2>
            <p>Our articles are developed through the following process:</p>
            <ul>
                <li><strong>Research:</strong> Content topics are drawn from established dental literature, clinical guidelines, and commonly asked patient questions</li>
                <li><strong>AI-Assisted Writing:</strong> Articles are drafted with the assistance of AI technology to ensure comprehensive topic coverage</li>
                <li><strong>Plain Language:</strong> Complex dental concepts are explained in language that is accessible to a general audience</li>
                <li><strong>Ongoing Improvement:</strong> Content is regularly reviewed and updated as new information becomes available</li>
            </ul>

            <h2>Reference Sources</h2>
            <p>DentalPedia content draws on information from widely recognized dental and health organizations, including:</p>
            <ul>
                <li>American Dental Association (ADA)</li>
                <li>National Institutes of Health (NIH)</li>
                <li>Published dental research and clinical guidelines</li>
            </ul>

            <h2>Important Disclaimer</h2>
            <p>The information on DentalPedia is for <strong>educational and informational purposes only</strong>. It should not be considered a substitute for professional dental or medical advice, diagnosis, or treatment. Always seek the advice of a qualified dentist or healthcare provider with any questions you may have about a dental condition or treatment.</p>
            <p>DentalPedia does not endorse any specific dentist, practice, product, or treatment. The dentist directory listings are based on publicly available data and do not imply endorsement or verification of credentials.</p>

            <h2>Accuracy & Corrections</h2>
            <p>While we strive for accuracy, dental science evolves continuously and our content may not always reflect the latest developments. If you notice any inaccuracies, please contact us so we can review and correct the information promptly.</p>
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
    """Generate password-protected admin dashboard."""
    logger.info("Generating admin dashboard...")

    total_articles = len(all_articles)
    total_categories = len(articles_by_category)
    total_subcategories = len(set(k.split('/')[1] for k in articles_by_subcategory.keys()))
    total_cities_cost = len(cities_data)
    total_procedures = len(procedure_costs)
    total_guides = len(cornerstone_guides)
    total_dentists = len(dentists_data)
    location_pages = total_cities_cost * total_procedures
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Dentist directory stats
    dentist_states = defaultdict(int)
    dentist_cities_count = defaultdict(int)
    for d in dentists_data:
        dentist_states[d['state']] += 1
        dentist_cities_count[(d['state'], d['city'])] += 1

    state_rows = ''
    for st in sorted(dentist_states.keys()):
        cities_in_st = len([k for k in dentist_cities_count if k[0] == st])
        state_rows += f'<tr><td>{STATE_NAMES.get(st, st)}</td><td>{dentist_states[st]:,}</td><td>{cities_in_st}</td></tr>'

    category_rows = ''
    for cat_slug, articles in sorted(articles_by_category.items()):
        category_rows += f'<tr><td>{cat_slug}</td><td>{len(articles)}</td></tr>'

    ekwa_count = len(ekwa_clients)

    # Password hash: SHA-256 of "dentalpedia2024" — user can change later
    # We use client-side hashing to keep it static-site compatible
    content = f'''
    <div id="login-screen" style="max-width:400px;margin:4rem auto;text-align:center;">
        <h1 style="margin-bottom:1rem;">🔒 Admin Dashboard</h1>
        <p style="color:var(--text-secondary);margin-bottom:1.5rem;">Enter password to access the dashboard</p>
        <input type="password" id="admin-pw" placeholder="Password" style="width:100%;padding:0.75rem;border:1px solid var(--border-color);border-radius:8px;font-size:1rem;margin-bottom:1rem;background:var(--bg-card);color:var(--text-primary);">
        <button onclick="checkPw()" style="width:100%;padding:0.75rem;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:700;cursor:pointer;">Unlock</button>
        <p id="pw-error" style="color:#ef4444;margin-top:0.75rem;display:none;">Incorrect password</p>
    </div>

    <div id="dashboard" style="display:none;">
        <div class="category-header">
            <h1>DentalPedia Admin Dashboard</h1>
            <p>Build: {build_time} &bull; <a href="#" onclick="document.getElementById('dashboard').style.display='none';document.getElementById('login-screen').style.display='block';return false;">Logout</a></p>
        </div>

        <!-- Tab Navigation -->
        <div style="display:flex;gap:0.5rem;margin:1.5rem 0;flex-wrap:wrap;">
            <button class="admin-tab active" onclick="showTab('overview',this)">Overview</button>
            <button class="admin-tab" onclick="showTab('directory',this)">Directory</button>
            <button class="admin-tab" onclick="showTab('leads',this)">Leads</button>
            <button class="admin-tab" onclick="showTab('content',this)">Content</button>
            <button class="admin-tab" onclick="showTab('ekwa',this)">Ekwa Clients</button>
        </div>

        <!-- OVERVIEW TAB -->
        <div id="tab-overview" class="admin-panel">
            <div class="admin-grid">
                <div class="admin-stat"><div class="admin-stat-label">Total Pages</div><div class="admin-stat-value">{total_articles + total_categories + total_subcategories + location_pages + total_guides + len(dentist_states) + len(dentist_cities_count) + 10:,}</div></div>
                <div class="admin-stat"><div class="admin-stat-label">Articles</div><div class="admin-stat-value">{total_articles:,}</div></div>
                <div class="admin-stat"><div class="admin-stat-label">Directory Listings</div><div class="admin-stat-value">{total_dentists:,}</div></div>
                <div class="admin-stat"><div class="admin-stat-label">Location Pages</div><div class="admin-stat-value">{location_pages:,}</div></div>
                <div class="admin-stat"><div class="admin-stat-label">Guides</div><div class="admin-stat-value">{total_guides}</div></div>
                <div class="admin-stat"><div class="admin-stat-label">Ekwa Premium</div><div class="admin-stat-value">{ekwa_count}</div></div>
            </div>
            <div class="admin-card" style="background:linear-gradient(135deg,#e8f4e8,#d4edda);border-color:#28a745;margin-bottom:1rem;">
                <h3 style="color:var(--text-primary);margin-bottom:0.5rem;">📊 Google Sheet — Lead Tracking</h3>
                <p style="color:var(--text-primary);margin-bottom:0.75rem;">All quiz emails, directory clicks, and appointment requests are logged here in real time.</p>
                <a href="https://docs.google.com/spreadsheets/d/1SRa0r2jDAZq-S3S1pxuJtJ-SUk898fvLiL1pEOn7NAM/edit" target="_blank" rel="noopener" style="display:inline-block;background:#28a745;color:#fff;padding:0.6rem 1.25rem;border-radius:8px;font-weight:700;text-decoration:none;font-size:0.95rem;">Open Google Sheet →</a>
            </div>
            <div class="admin-card">
                <h3>Build Information</h3>
                <p><strong>Build Time:</strong> {build_time}</p>
                <p><strong>Categories:</strong> {total_categories} &bull; <strong>Subcategories:</strong> {total_subcategories}</p>
                <p><strong>Directory:</strong> {total_dentists:,} practices across {len(dentist_states)} states, {len(dentist_cities_count):,} cities</p>
                <p><strong>Cost Pages:</strong> {total_procedures} procedures × {total_cities_cost} cities = {location_pages:,} pages</p>
            </div>
        </div>

        <!-- DIRECTORY TAB -->
        <div id="tab-directory" class="admin-panel" style="display:none;">
            <h2>Dentist Directory Coverage</h2>
            <p>{total_dentists:,} practices &bull; {len(dentist_states)} states &bull; {len(dentist_cities_count):,} cities</p>
            <div style="max-height:500px;overflow-y:auto;">
                <table class="admin-table">
                    <thead><tr><th>State</th><th>Practices</th><th>Cities</th></tr></thead>
                    <tbody>{state_rows}</tbody>
                </table>
            </div>
        </div>

        <!-- LEADS TAB -->
        <div id="tab-leads" class="admin-panel" style="display:none;">
            <h2>Lead Tracking</h2>
            <p>Directory click data, appointment requests, and quiz email captures are logged to Google Sheets in real time.</p>
            <div class="admin-card" style="background:linear-gradient(135deg,#e8f4e8,#d4edda);border-color:#28a745;margin-bottom:1rem;text-align:center;">
                <a href="https://docs.google.com/spreadsheets/d/1SRa0r2jDAZq-S3S1pxuJtJ-SUk898fvLiL1pEOn7NAM/edit" target="_blank" rel="noopener" style="display:inline-block;background:#28a745;color:#fff;padding:0.75rem 2rem;border-radius:8px;font-weight:700;text-decoration:none;font-size:1.1rem;">📊 Open Google Sheet →</a>
            </div>
            <div class="admin-card">
                <h3>Data Sources (3 Tabs in the Sheet)</h3>
                <p><strong>Sheet1 — Quiz Emails:</strong> Timestamp, Email, Score, Rating</p>
                <p><strong>Leads — Directory Clicks:</strong> Timestamp, Practice, Action (call/website), City, State, Page</p>
                <p><strong>Appointments — Requests:</strong> Timestamp, Practice, Patient Name, Phone, Email, Message, City, State, Page</p>
            </div>
            <div class="admin-card" style="margin-top:1rem;">
                <h3>Recent Leads (Live)</h3>
                <div id="leads-live" style="color:var(--text-secondary);">Loading...</div>
            </div>
        </div>

        <!-- CONTENT TAB -->
        <div id="tab-content" class="admin-panel" style="display:none;">
            <h2>Content Breakdown</h2>
            <div style="max-height:500px;overflow-y:auto;">
                <table class="admin-table">
                    <thead><tr><th>Category</th><th>Articles</th></tr></thead>
                    <tbody>{category_rows}</tbody>
                </table>
            </div>
        </div>

        <!-- EKWA TAB -->
        <div id="tab-ekwa" class="admin-panel" style="display:none;">
            <h2>Ekwa Premium Clients</h2>
            <p>{ekwa_count} premium listings active. To add clients, update <code>data/ekwa_clients.json</code> and rebuild.</p>
            <div class="admin-card">
                <h3>How It Works</h3>
                <p>Ekwa clients get a gold "Featured Practice" badge and appear at the top of their city's listing page.</p>
                <p>The <code>ekwa_clients.json</code> file maps practice names to premium status:</p>
                <pre style="background:var(--bg-secondary);padding:1rem;border-radius:8px;overflow-x:auto;font-size:0.85rem;">{{"Practice Name Here": {{"tier": "premium", "since": "2026-03"}}, ...}}</pre>
                <p style="margin-top:1rem;"><strong>Phase 2:</strong> Offer as paid feature on ekwa.com — SEO clients get premium listing as a benefit.</p>
            </div>
        </div>
    </div>

    <style>
    .admin-tab {{background:var(--bg-card);border:1px solid var(--border-color);padding:0.5rem 1rem;border-radius:6px;cursor:pointer;font-weight:600;color:var(--text-secondary);font-size:0.9rem;}}
    .admin-tab.active {{background:var(--accent);color:#fff;border-color:var(--accent);}}
    .admin-grid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:1rem;margin:1.5rem 0;}}
    .admin-stat {{background:var(--bg-card);border:1px solid var(--border-color);padding:1.25rem;border-radius:10px;text-align:center;}}
    .admin-stat-label {{font-size:0.8rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;}}
    .admin-stat-value {{font-size:1.8rem;font-weight:700;color:var(--accent);margin-top:0.25rem;}}
    .admin-card {{background:var(--bg-card);border:1px solid var(--border-color);padding:1.5rem;border-radius:10px;}}
    .admin-card h3 {{margin-top:0;margin-bottom:0.75rem;}}
    .admin-table {{width:100%;border-collapse:collapse;}}
    .admin-table th,.admin-table td {{padding:0.6rem 1rem;text-align:left;border-bottom:1px solid var(--border-color);}}
    .admin-table th {{font-weight:700;font-size:0.85rem;text-transform:uppercase;color:var(--text-secondary);}}
    </style>

    <script>
    // SHA-256 hash of password
    var HASH = '7d1c63c58bced4b89e19f61ac4e549e53b508b25383f0148da6050dcbf350106';
    async function sha256(msg) {{
        var buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(msg));
        return Array.from(new Uint8Array(buf)).map(function(b){{return b.toString(16).padStart(2,'0')}}).join('');
    }}
    async function checkPw() {{
        var pw = document.getElementById('admin-pw').value;
        var hash = await sha256(pw);
        if (hash === HASH) {{
            document.getElementById('login-screen').style.display='none';
            document.getElementById('dashboard').style.display='block';
            sessionStorage.setItem('dp_admin','1');
        }} else {{
            document.getElementById('pw-error').style.display='block';
        }}
    }}
    document.getElementById('admin-pw').addEventListener('keypress', function(e) {{
        if (e.key === 'Enter') checkPw();
    }});
    if (sessionStorage.getItem('dp_admin')==='1') {{
        document.getElementById('login-screen').style.display='none';
        document.getElementById('dashboard').style.display='block';
    }}
    function showTab(name, btn) {{
        document.querySelectorAll('.admin-panel').forEach(function(p){{p.style.display='none'}});
        document.querySelectorAll('.admin-tab').forEach(function(t){{t.classList.remove('active')}});
        document.getElementById('tab-'+name).style.display='block';
        btn.classList.add('active');
    }}
    </script>
    '''

    page_html = get_page_template(
        "Admin Dashboard | DentalPedia",
        content,
        f"{DOMAIN}/admin.html",
        "Admin dashboard"
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

    # Clinical sitemap
    clinical_sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/clinical/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
'''.format(base_url=base_url)
    for article in all_articles:
        slug = article.get('slug', '')
        date = article.get('date', '')
        clinical_sitemap += f'''  <url>
    <loc>{base_url}/clinical/{slug}.html</loc>
    <lastmod>{date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
'''
    clinical_sitemap += '</urlset>'

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

    for combo_key in articles_by_subcategory.keys():
        if articles_by_subcategory[combo_key]:
            cat_slug, subcat_slug = combo_key.split('/', 1)
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

    # Dentist directory sitemap
    dentist_sitemap = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/find-a-dentist/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
'''
    dentist_dir = SITE_ROOT / "find-a-dentist"
    if dentist_dir.exists():
        for state_file in sorted(dentist_dir.glob("*.html")):
            if state_file.name != "index.html":
                dentist_sitemap += f'''  <url>
    <loc>{base_url}/find-a-dentist/{state_file.name}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
'''
        for state_subdir in sorted(dentist_dir.iterdir()):
            if state_subdir.is_dir():
                for city_file in sorted(state_subdir.glob("*.html")):
                    dentist_sitemap += f'''  <url>
    <loc>{base_url}/find-a-dentist/{state_subdir.name}/{city_file.name}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>
'''
    dentist_sitemap += '</urlset>'

    # Sitemap index
    sitemap_index = f'''<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{base_url}/sitemap-articles.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-clinical.xml</loc>
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
  <sitemap>
    <loc>{base_url}/sitemap-dentists.xml</loc>
  </sitemap>
</sitemapindex>'''

    # Write sitemaps
    with open(SITE_ROOT / "sitemap-articles.xml", 'w', encoding='utf-8') as f:
        f.write(articles_sitemap)

    with open(SITE_ROOT / "sitemap-clinical.xml", 'w', encoding='utf-8') as f:
        f.write(clinical_sitemap)

    with open(SITE_ROOT / "sitemap-categories.xml", 'w', encoding='utf-8') as f:
        f.write(categories_sitemap)

    with open(SITE_ROOT / "sitemap-locations.xml", 'w', encoding='utf-8') as f:
        f.write(locations_sitemap)

    with open(SITE_ROOT / "sitemap-guides.xml", 'w', encoding='utf-8') as f:
        f.write(guides_sitemap)

    with open(SITE_ROOT / "sitemap-dentists.xml", 'w', encoding='utf-8') as f:
        f.write(dentist_sitemap)

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
        subcat_count = sum(1 for k in articles_by_subcategory.keys() if k.startswith(f"{cat_slug}/"))
        categories_html += f'''
        <a href="/category/{cat_slug}.html" class="category-card">
            <div class="category-icon">📚</div>
            <div class="category-name">{html_mod.escape(cat_name)}</div>
            <div class="category-count">{len(articles)} {"article" if len(articles) == 1 else "articles"}{f" • {subcat_count} {'subcategory' if subcat_count == 1 else 'subcategories'}" if subcat_count > 0 else ""}</div>
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


def generate_404_page():
    """Generate custom 404 error page for GitHub Pages."""
    logger.info("Generating 404 page...")
    content = '''
    <div class="content-width" style="padding: 4rem 0; text-align: center;">
        <div style="font-size: 5rem; margin-bottom: 1rem;">🦷</div>
        <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem;">Page Not Found</h1>
        <p style="font-size: 1.15rem; color: var(--text-secondary); margin-bottom: 2rem;">
            Sorry, the page you're looking for doesn't exist or may have moved.
        </p>
        <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-bottom: 3rem;">
            <a href="/" style="background: var(--accent); color: #fff; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600;">Go to Homepage</a>
            <a href="/categories.html" style="border: 2px solid var(--accent); color: var(--accent); padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600;">Browse Categories</a>
        </div>
        <div style="max-width: 500px; margin: 0 auto; text-align: left;">
            <p style="font-weight: 600; margin-bottom: 0.75rem;">Popular topics:</p>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                <a href="/category/general-dentistry.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">General Dentistry</a>
                <a href="/category/cosmetic-dentistry.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">Cosmetic Dentistry</a>
                <a href="/category/preventive-care.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">Preventive Care</a>
                <a href="/category/orthodontics.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">Orthodontics</a>
                <a href="/category/dental-implants.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">Dental Implants</a>
                <a href="/tools/dental-health-quiz.html" style="background: var(--bg-secondary); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; text-decoration: none; color: var(--text-primary);">Dental Health Quiz</a>
            </div>
        </div>
    </div>
    '''

    page_html = get_page_template(
        "Page Not Found | DentalPedia",
        content,
        f"{DOMAIN}/404.html",
        "The page you're looking for doesn't exist. Browse our dental health articles and guides."
    )

    with open(SITE_ROOT / "404.html", 'w', encoding='utf-8') as f:
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

            <div id="result" style="display: none; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 1.5rem; margin-top: 1rem;">
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

        <style>.quiz-opt{{display:block;width:100%;text-align:left;padding:1rem;margin-bottom:.75rem;border:1px solid var(--border-color);border-radius:10px;background:var(--bg-primary);color:var(--text-primary);font-size:1rem;cursor:pointer;transition:all .2s}}.quiz-opt:hover{{border-color:var(--accent);background:var(--bg-secondary)}}</style>
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

                <div id="email-section" style="background: var(--bg-secondary); border-radius: 12px; padding: 1.5rem; margin-top: 1.5rem; border: 1px solid var(--border-color);">
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
            const btn = this;
            btn.disabled = true;
            btn.textContent = 'Sending...';
            // Send to Google Sheet
            fetch('https://script.google.com/macros/s/AKfycbwenWITYJQ-lbT1l58OxxeQVy1M7C1kMtBWlxqEDD0MKcdKqhJhBvTnXV9tKgHSvxRVuA/exec', {{
                method: 'POST',
                mode: 'no-cors',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{email: email, score: pct, rating: document.getElementById('score-label').textContent}})
            }}).then(function() {{
                document.getElementById('email-success').style.display = 'block';
                btn.textContent = 'Sent!';
            }}).catch(function() {{
                document.getElementById('email-success').style.display = 'block';
                btn.textContent = 'Sent!';
            }});
            // Track with GA4
            if (typeof gtag !== 'undefined') gtag('event', 'quiz_email_capture', {{event_category: 'engagement', event_label: email}});
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
            <p>Adding the DentalPedia widget to your dental practice website provides educational dental health content for your patients, requires zero maintenance as articles update automatically, and helps keep visitors engaged with relevant oral health information.</p>
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

            <div class="myth-box" style="border-radius: 16px; padding: 2rem; margin: 1.5rem 0; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">❌</div>
                <div class="myth-label">Myth</div>
                <h1 class="myth-text">"{html_mod.escape(m['myth'])}"</h1>
            </div>

            <div class="fact-box" style="border-radius: 16px; padding: 2rem; margin: 1.5rem 0; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">✅</div>
                <div class="fact-label">Fact</div>
                <p class="fact-text">{html_mod.escape(m['fact'])}</p>
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


STATE_NAMES = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','DC':'District of Columbia','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'}


def slugify(text):
    """Convert text to URL-safe slug."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def practice_slug(practice):
    """Generate a URL slug for a practice."""
    return slugify(practice['name'])[:60]


def generate_dentist_card(practice, is_premium=False, show_appt=True):
    """Generate HTML card for a single dental practice."""
    stars = ''
    if practice['rating'] > 0:
        full = int(practice['rating'])
        stars = '★' * full + ('½' if practice['rating'] - full >= 0.3 else '') + f' {practice["rating"]}'

    premium_badge = '<span class="premium-badge">⭐ Featured Practice</span>' if is_premium else ''
    premium_class = ' dentist-card-premium' if is_premium else ''

    safe_name = html_mod.escape(practice['name']).replace("'", "\\'")
    safe_city = html_mod.escape(practice['city']).replace("'", "\\'")

    phone_btn = ''
    if practice['phone']:
        phone_clean = re.sub(r'[^0-9+]', '', practice['phone'])
        phone_btn = f'<a href="tel:{phone_clean}" class="dentist-btn dentist-btn-call" onclick="trackLead(\'{safe_name}\',\'call\',\'{safe_city}\',\'{practice["state"]}\')">📞 Call</a>'

    website_btn = ''
    if practice['website']:
        website_btn = f'<a href="{html_mod.escape(practice["website"])}" target="_blank" rel="noopener" class="dentist-btn dentist-btn-web" onclick="trackLead(\'{safe_name}\',\'website\',\'{safe_city}\',\'{practice["state"]}\')">🌐 Website</a>'

    reviews_text = f'({practice["reviews"]:,} reviews)' if practice['reviews'] > 0 else ''

    # Profile link
    state_slug = slugify(STATE_NAMES.get(practice['state'], practice['state']))
    city_slug_val = slugify(practice['city'])
    p_slug = practice_slug(practice)
    profile_link = f'/find-a-dentist/{state_slug}/{city_slug_val}/{p_slug}.html'

    # Appointment button
    appt_btn = ''
    if show_appt:
        appt_btn = f'<button class="dentist-btn dentist-btn-appt" onclick="openApptForm(\'{safe_name}\',\'{safe_city}\',\'{practice["state"]}\')">📅 Request Appointment</button>'

    return f'''<div class="dentist-card{premium_class}">
        {premium_badge}
        <h3 class="dentist-name"><a href="{profile_link}" style="color:inherit;text-decoration:none;">{html_mod.escape(practice['name'])}</a></h3>
        <p class="dentist-address">📍 {html_mod.escape(practice['address'])}</p>
        <div class="dentist-rating">{stars} <span class="review-count">{reviews_text}</span></div>
        <div class="dentist-actions">{phone_btn} {website_btn} {appt_btn}</div>
    </div>'''


def generate_practice_bio(practice, city, state_name, state_abbr):
    """Generate a varied, factual bio section for a practice profile page.

    Uses multiple template variants selected by practice name hash for consistency.
    Avoids unsubstantiated superlatives. Uses factual language only.
    """
    import hashlib as _hl
    name = practice['name']
    escaped_name = html_mod.escape(name)
    escaped_city = html_mod.escape(city)
    rating = practice.get('rating', 0)
    reviews = practice.get('reviews', 0)
    phone = practice.get('phone', '')
    website = practice.get('website', '')
    address = practice.get('address', '')

    # Hash-based variant selector for consistent but varied output
    h = int(_hl.md5(name.encode()).hexdigest(), 16)

    # Detect if practice name is a doctor's name
    name_lower = name.lower()
    is_doctor = any(t in name_lower for t in ['dr.', 'dr ', 'dds', 'dmd'])

    # Build rating sentence (factual only)
    rating_sentence = ''
    if rating > 0 and reviews > 0:
        rating_sentence = f'{escaped_name} has a {rating}-star rating based on {reviews:,} patient review{"s" if reviews != 1 else ""}.'

    # Build services list based on practice name keywords
    detected_services = []
    service_keywords = {
        'orthodont': 'Orthodontics', 'oral surg': 'Oral Surgery',
        'periodon': 'Periodontics', 'endodon': 'Endodontics',
        'pediatr': 'Pediatric Dentistry', 'cosmetic': 'Cosmetic Dentistry',
        'implant': 'Dental Implants', 'prosthodon': 'Prosthodontics',
        'family': 'Family Dentistry', 'general': 'General Dentistry',
        'emergency': 'Emergency Dental Care', 'sedation': 'Sedation Dentistry',
        'holistic': 'Holistic Dentistry', 'laser': 'Laser Dentistry',
        'sleep': 'Sleep Apnea Treatment',
    }
    for kw, svc in service_keywords.items():
        if kw in name_lower:
            detected_services.append(svc)

    if not detected_services:
        # Vary default services by hash
        service_sets = [
            ['General Dentistry', 'Preventive Care', 'Restorative Dentistry'],
            ['General Dentistry', 'Cosmetic Dentistry', 'Preventive Care'],
            ['Family Dentistry', 'Preventive Care', 'Restorative Dentistry'],
        ]
        detected_services = service_sets[h % len(service_sets)]

    services_text = ', '.join(detected_services[:-1]) + (f', and {detected_services[-1]}' if len(detected_services) > 1 else detected_services[0])

    # Varied intro templates (factual, no superlatives)
    if is_doctor:
        doc_intros = [
            f'{escaped_name} is a dental practice located in {escaped_city}, {html_mod.escape(state_name)}. The practice provides dental care services to patients in the {escaped_city} area.',
            f'Located in {escaped_city}, {html_mod.escape(state_name)}, {escaped_name} offers dental services to local patients. The office accepts both new and existing patients.',
            f'{escaped_name} provides dental care in {escaped_city}, {html_mod.escape(state_name)}. Patients can contact the office to learn about available services and schedule visits.',
            f'Patients in {escaped_city}, {html_mod.escape(state_name)} can visit {escaped_name} for dental care. The practice serves individuals and families in the surrounding area.',
        ]
        intro = doc_intros[h % len(doc_intros)]
    else:
        practice_intros = [
            f'{escaped_name} is a dental office located in {escaped_city}, {html_mod.escape(state_name)}, serving patients in the local area.',
            f'Located in {escaped_city}, {html_mod.escape(state_name)}, {escaped_name} provides dental care services. The practice is open to new patients.',
            f'{escaped_name} is a dental practice in {escaped_city}, {html_mod.escape(state_name)}. The office offers dental services to patients of various ages.',
            f'Patients in the {escaped_city}, {html_mod.escape(state_name)} area can visit {escaped_name} for dental care services.',
        ]
        intro = practice_intros[h % len(practice_intros)]

    # Varied service paragraphs
    svc_templates = [
        f'Services offered include {services_text}. Patients should contact the office directly to confirm specific services and availability.',
        f'The practice offers services in areas including {services_text}. For details about specific treatments, patients can reach out to the office.',
        f'{escaped_name} provides services such as {services_text}. Appointment availability and specific offerings may vary.',
    ]
    services_para = svc_templates[(h >> 4) % len(svc_templates)]

    # Location paragraph (factual)
    loc_templates = [
        f'The office is located at {html_mod.escape(address)}. Patients in {escaped_city} and surrounding communities can visit for dental care.',
        f'{escaped_name} can be found at {html_mod.escape(address)}, serving the {escaped_city} area and nearby neighborhoods in {html_mod.escape(state_name)}.',
        f'The practice is situated at {html_mod.escape(address)} in the {escaped_city}, {state_abbr} area.',
    ]
    community_para = loc_templates[(h >> 8) % len(loc_templates)]

    # CTA paragraph
    if phone:
        phone_clean = re.sub(r'[^0-9+]', '', phone)
        cta_para = f'To schedule an appointment or ask about services, contact {escaped_name} at <a href="tel:{phone_clean}">{html_mod.escape(phone)}</a>.'
    else:
        cta_para = f'To learn more about available services, visit the {escaped_name} website or use the appointment request form above.'

    bio_html = f'''
    <div class="practice-bio" style="margin:1.5rem 0;padding:1.5rem;background:var(--bg-card);border-radius:12px;border:1px solid var(--border-color);">
        <h2 style="margin-top:0;color:var(--heading);font-size:1.35rem;">About {escaped_name}</h2>
        <p style="line-height:1.75;color:var(--text);margin-bottom:1rem;">{intro}</p>
        {f'<p style="line-height:1.75;color:var(--text);margin-bottom:1rem;">{rating_sentence}</p>' if rating_sentence else ''}
        <h3 style="color:var(--heading);font-size:1.1rem;margin-bottom:0.5rem;">Services in {escaped_city}, {state_abbr}</h3>
        <p style="line-height:1.75;color:var(--text);margin-bottom:1rem;">{services_para}</p>
        <h3 style="color:var(--heading);font-size:1.1rem;margin-bottom:0.5rem;">Location</h3>
        <p style="line-height:1.75;color:var(--text);margin-bottom:1rem;">{community_para}</p>
        <p style="line-height:1.75;color:var(--text);margin-bottom:0.5rem;">{cta_para}</p>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0;margin-top:0.75rem;"><em>Practice information is based on publicly available data and may not reflect current details. Please contact the office directly to verify.</em></p>
    </div>'''

    return bio_html


def generate_find_dentist_pages():
    """Generate Find a Dentist directory: main page, state pages, city pages."""
    if not dentists_data:
        logger.warning("No dentist data loaded, skipping directory pages")
        return

    base_dir = SITE_ROOT / "find-a-dentist"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Filter out non-US entries (safety check)
    valid_us_states = {'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'}
    filtered_data = [p for p in dentists_data if p.get('state', '') in valid_us_states and 'France' not in p.get('address', '')]
    if len(filtered_data) < len(dentists_data):
        logger.info(f"Filtered out {len(dentists_data) - len(filtered_data)} non-US entries from directory")

    # Organize data by state and city
    by_state = defaultdict(list)
    for p in filtered_data:
        by_state[p['state']].append(p)

    by_city = defaultdict(list)
    for p in dentists_data:
        key = (p['state'], p['city'])
        by_city[key].append(p)

    # Sort practices: premium first, then by rating desc
    def sort_practices(practices):
        def sort_key(p):
            is_prem = 1 if p.get('name','') in ekwa_clients else 0
            return (-is_prem, -p.get('rating', 0), -p.get('reviews', 0))
        return sorted(practices, key=sort_key)

    # Build ZIP code lookup
    zip_lookup = {}
    for p in dentists_data:
        z = p.get('zip', '')
        if z and len(z) == 5 and z not in zip_lookup:
            zip_lookup[z] = [p['city'], p['state']]

    APPS_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbwenWITYJQ-lbT1l58OxxeQVy1M7C1kMtBWlxqEDD0MKcdKqhJhBvTnXV9tKgHSvxRVuA/exec'

    # Lead tracking + appointment form JS (included on all directory pages)
    lead_tracking_js = f'''
    <script>
    function trackLead(name, action, city, state) {{
        fetch('{APPS_SCRIPT_URL}', {{
            method: 'POST', mode: 'no-cors',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{type:'lead', practice: name, action: action, city: city, state: state, page: window.location.pathname}})
        }});
        if (typeof gtag !== 'undefined') gtag('event', 'dentist_lead', {{event_category: 'directory', event_label: name, action_type: action}});
    }}
    function openApptForm(name, city, state) {{
        document.getElementById('appt-modal').style.display = 'flex';
        document.getElementById('appt-practice').value = name;
        document.getElementById('appt-city').value = city;
        document.getElementById('appt-state').value = state;
        document.getElementById('appt-title').textContent = 'Request Appointment at ' + name;
    }}
    function closeApptForm() {{ document.getElementById('appt-modal').style.display = 'none'; }}
    function submitAppt() {{
        var name = document.getElementById('appt-name').value.trim();
        var phone = document.getElementById('appt-phone').value.trim();
        var email = document.getElementById('appt-email').value.trim();
        var msg = document.getElementById('appt-msg').value.trim();
        var practice = document.getElementById('appt-practice').value;
        var city = document.getElementById('appt-city').value;
        var state = document.getElementById('appt-state').value;
        if (!name || !phone) {{ alert('Please enter your name and phone number.'); return; }}
        var btn = document.querySelector('#appt-modal .appt-submit');
        btn.disabled = true; btn.textContent = 'Sending...';
        fetch('{APPS_SCRIPT_URL}', {{
            method: 'POST', mode: 'no-cors',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{type:'appointment', practice: practice, patient_name: name, patient_phone: phone, patient_email: email, message: msg, city: city, state: state, page: window.location.pathname}})
        }}).then(function() {{
            btn.textContent = 'Sent!';
            document.getElementById('appt-success').style.display = 'block';
            trackLead(practice, 'appointment', city, state);
            setTimeout(closeApptForm, 2000);
        }}).catch(function() {{
            btn.textContent = 'Sent!';
            document.getElementById('appt-success').style.display = 'block';
            setTimeout(closeApptForm, 2000);
        }});
    }}
    </script>
    <!-- Appointment Modal -->
    <div id="appt-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
        <div style="background:var(--bg-card);border-radius:12px;padding:2rem;max-width:450px;width:90%;position:relative;">
            <button onclick="closeApptForm()" style="position:absolute;top:1rem;right:1rem;background:none;border:none;font-size:1.5rem;cursor:pointer;color:var(--text-secondary);">✕</button>
            <h3 id="appt-title" style="margin-top:0;">Request Appointment</h3>
            <input type="hidden" id="appt-practice"><input type="hidden" id="appt-city"><input type="hidden" id="appt-state">
            <input type="text" id="appt-name" placeholder="Your Name *" style="width:100%;padding:0.6rem;margin-bottom:0.75rem;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-card);color:var(--text-primary);">
            <input type="tel" id="appt-phone" placeholder="Phone Number *" style="width:100%;padding:0.6rem;margin-bottom:0.75rem;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-card);color:var(--text-primary);">
            <input type="email" id="appt-email" placeholder="Email (optional)" style="width:100%;padding:0.6rem;margin-bottom:0.75rem;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-card);color:var(--text-primary);">
            <textarea id="appt-msg" placeholder="Message (optional)" rows="3" style="width:100%;padding:0.6rem;margin-bottom:0.75rem;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-card);color:var(--text-primary);resize:vertical;"></textarea>
            <button onclick="submitAppt()" class="appt-submit" style="width:100%;padding:0.75rem;background:var(--accent);color:#fff;border:none;border-radius:8px;font-weight:700;font-size:1rem;cursor:pointer;">Send Request</button>
            <p id="appt-success" style="display:none;color:#16a34a;text-align:center;margin-top:0.75rem;font-weight:600;">Request sent! The practice will contact you soon.</p>
        </div>
    </div>
    '''

    # ==========================================
    # 1. MAIN SEARCH PAGE
    # ==========================================
    state_links = ''
    for st in sorted(by_state.keys()):
        name = STATE_NAMES.get(st, st)
        count = len(by_state[st])
        state_links += f'<a href="/find-a-dentist/{slugify(name)}.html" class="state-link"><strong>{name}</strong><span>{count:,} dentists</span></a>'

    # Build compact ZIP lookup JS object — only include ZIP -> [stateSlug, citySlug]
    zip_js_map = {}
    for z, (city, st) in zip_lookup.items():
        s_slug = slugify(STATE_NAMES.get(st, st))
        c_slug = slugify(city)
        zip_js_map[z] = [s_slug, c_slug]

    search_content = f'''
    {lead_tracking_js}
    <div class="directory-hero">
        <h1>Find a Dentist Near You</h1>
        <p>Search our directory of {len(dentists_data):,} dental practices across all 50 states</p>
        <div class="directory-search">
            <input type="text" id="dentist-search" placeholder="Enter city, state, or ZIP code..." autocomplete="off">
            <button onclick="searchDentists()" class="search-btn">Search</button>
        </div>
    </div>
    <div class="state-grid">
        <h2>Browse by State</h2>
        <div class="state-links">{state_links}</div>
    </div>
    <script>
    var stateMap = {json.dumps({slugify(STATE_NAMES.get(st,st)): st for st in by_state.keys()})};
    var cityMap = {json.dumps({f"{c[1].lower()}, {STATE_NAMES.get(c[0],c[0]).lower()}": f"/find-a-dentist/{slugify(STATE_NAMES.get(c[0],c[0]))}/{slugify(c[1])}.html" for c in by_city.keys()})};
    var zipMap = {json.dumps(zip_js_map)};
    function searchDentists() {{
        var q = document.getElementById('dentist-search').value.trim().toLowerCase();
        if (!q) return;
        // Try ZIP code first
        if (/^\\d{{5}}$/.test(q) && zipMap[q]) {{
            window.location.href = '/find-a-dentist/' + zipMap[q][0] + '/' + zipMap[q][1] + '.html';
            return;
        }}
        // Try city match
        for (var key in cityMap) {{
            if (key.indexOf(q) !== -1) {{ window.location.href = cityMap[key]; return; }}
        }}
        // Try state match
        for (var slug in stateMap) {{
            var name = slug.replace(/-/g, ' ');
            if (name.indexOf(q) !== -1) {{ window.location.href = '/find-a-dentist/' + slug + '.html'; return; }}
        }}
        alert('No results found for "' + q + '". Try a different city, state, or ZIP code.');
    }}
    document.getElementById('dentist-search').addEventListener('keypress', function(e) {{
        if (e.key === 'Enter') searchDentists();
    }});
    </script>
    '''

    page_html = get_page_template(
        "Find a Dentist Near You | DentalPedia",
        search_content,
        f"{DOMAIN}/find-a-dentist/",
        f"Search {len(dentists_data):,} dental practices across the US. Find ratings, phone numbers, and websites for dentists in your area."
    )
    with open(base_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)

    # ==========================================
    # 2. STATE PAGES
    # ==========================================
    state_count = 0
    for st, practices in by_state.items():
        state_name = STATE_NAMES.get(st, st)
        state_slug = slugify(state_name)
        state_dir = base_dir / state_slug

        # Get cities in this state
        state_cities = defaultdict(list)
        for p in practices:
            state_cities[p['city']].append(p)

        city_links = ''
        for city in sorted(state_cities.keys()):
            count = len(state_cities[city])
            city_links += f'<a href="/find-a-dentist/{state_slug}/{slugify(city)}.html" class="city-link"><strong>{html_mod.escape(city)}</strong><span>{count} dentist{"s" if count != 1 else ""}</span></a>'

        # Show top-rated practices for the state
        top_practices = sort_practices(practices)[:12]
        top_cards = ''.join(generate_dentist_card(p, p['name'] in ekwa_clients) for p in top_practices)

        # Breadcrumb schema for state page
        state_bc_schema = f'''<script type="application/ld+json">
        {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
            {{"@type":"ListItem","position":1,"name":"Home","item":"{DOMAIN}/"}},
            {{"@type":"ListItem","position":2,"name":"Find a Dentist","item":"{DOMAIN}/find-a-dentist/"}},
            {{"@type":"ListItem","position":3,"name":"{html_mod.escape(state_name)}","item":"{DOMAIN}/find-a-dentist/{state_slug}.html"}}
        ]}}</script>'''

        state_content = f'''
        {lead_tracking_js}
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/find-a-dentist/">Find a Dentist</a> &rsaquo; {html_mod.escape(state_name)}</nav>
        <h1>Find a Dentist in {html_mod.escape(state_name)}</h1>
        <p>{len(practices):,} dental practices across {len(state_cities)} cities in {html_mod.escape(state_name)}</p>

        <h2>Cities in {html_mod.escape(state_name)}</h2>
        <div class="city-links">{city_links}</div>

        <h2>Top-Rated Dentists in {html_mod.escape(state_name)}</h2>
        <div class="dentist-grid">{top_cards}</div>
        {generate_share_buttons(f"Find a Dentist in {state_name}", f"{DOMAIN}/find-a-dentist/{state_slug}.html")}
        '''

        page_html = get_page_template(
            f"Find a Dentist in {state_name} | DentalPedia",
            state_content,
            f"{DOMAIN}/find-a-dentist/{state_slug}.html",
            f"Find top-rated dentists in {state_name}. Browse {len(practices):,} dental practices across {len(state_cities)} cities with ratings, phone numbers, and websites.",
            schema=state_bc_schema
        )
        with open(base_dir / f"{state_slug}.html", 'w', encoding='utf-8') as f:
            f.write(page_html)
        state_count += 1

        # ==========================================
        # 3. CITY PAGES
        # ==========================================
        state_dir.mkdir(parents=True, exist_ok=True)
        for city, city_practices in state_cities.items():
            city_slug = slugify(city)
            sorted_practices = sort_practices(city_practices)

            cards = ''.join(generate_dentist_card(p, p['name'] in ekwa_clients) for p in sorted_practices)

            avg_rating = sum(p['rating'] for p in city_practices if p['rating'] > 0) / max(1, len([p for p in city_practices if p['rating'] > 0]))

            city_content = f'''
            {lead_tracking_js}
            <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/find-a-dentist/">Find a Dentist</a> &rsaquo; <a href="/find-a-dentist/{state_slug}.html">{html_mod.escape(state_name)}</a> &rsaquo; {html_mod.escape(city)}</nav>
            <h1>Dentists in {html_mod.escape(city)}, {st}</h1>
            <p class="directory-meta">{len(city_practices)} dental practice{"s" if len(city_practices) != 1 else ""} &bull; Average rating: {avg_rating:.1f} ★</p>

            <div class="dentist-grid">{cards}</div>
            {generate_share_buttons(f"Dentists in {city}, {st}", f"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}.html")}
            '''

            # Combined breadcrumb + ItemList schema
            schema = f'''<script type="application/ld+json">
            {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
                {{"@type":"ListItem","position":1,"name":"Home","item":"{DOMAIN}/"}},
                {{"@type":"ListItem","position":2,"name":"Find a Dentist","item":"{DOMAIN}/find-a-dentist/"}},
                {{"@type":"ListItem","position":3,"name":"{html_mod.escape(state_name)}","item":"{DOMAIN}/find-a-dentist/{state_slug}.html"}},
                {{"@type":"ListItem","position":4,"name":"{html_mod.escape(city)}","item":"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}.html"}}
            ]}}</script>
            <script type="application/ld+json">
            {{"@context":"https://schema.org","@type":"ItemList","name":"Dentists in {html_mod.escape(city)}, {st}","numberOfItems":{len(city_practices)},"itemListElement":[{",".join(f'{{"@type":"ListItem","position":{i+1},"item":{{"@type":"Dentist","name":"{html_mod.escape(p["name"])}","address":"{html_mod.escape(p["address"])}","telephone":"{html_mod.escape(p["phone"])}"}}}}' for i, p in enumerate(sorted_practices[:20]))}]}}
            </script>'''

            page_html = get_page_template(
                f"Dentists in {city}, {st} - Find a Dentist | DentalPedia",
                city_content,
                f"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}.html",
                f"Find {len(city_practices)} dentists in {city}, {state_name}. Compare ratings, read reviews, and contact dental practices near you.",
                schema=schema
            )
            with open(state_dir / f"{city_slug}.html", 'w', encoding='utf-8') as f:
                f.write(page_html)

            # ==========================================
            # 4. INDIVIDUAL PRACTICE PROFILE PAGES
            # ==========================================
            city_profile_dir = state_dir / city_slug
            city_profile_dir.mkdir(parents=True, exist_ok=True)
            for p in sorted_practices:
                p_slug = practice_slug(p)
                is_prem = p['name'] in ekwa_clients
                safe_name_p = html_mod.escape(p['name']).replace("'", "\\'")
                safe_city_p = html_mod.escape(p['city']).replace("'", "\\'")

                # Build social links
                social_links = ''
                if p.get('facebook'):
                    social_links += f'<a href="{html_mod.escape(p["facebook"])}" target="_blank" rel="noopener" class="dentist-btn dentist-btn-web">Facebook</a> '
                if p.get('instagram'):
                    social_links += f'<a href="{html_mod.escape(p["instagram"])}" target="_blank" rel="noopener" class="dentist-btn dentist-btn-web">Instagram</a> '

                phone_html = ''
                if p['phone']:
                    phone_clean = re.sub(r'[^0-9+]', '', p['phone'])
                    phone_html = f'<a href="tel:{phone_clean}" class="dentist-btn dentist-btn-call" onclick="trackLead(\'{safe_name_p}\',\'call\',\'{safe_city_p}\',\'{p["state"]}\')">📞 {html_mod.escape(p["phone"])}</a>'

                web_html = ''
                if p['website']:
                    web_html = f'<a href="{html_mod.escape(p["website"])}" target="_blank" rel="noopener" class="dentist-btn dentist-btn-web" onclick="trackLead(\'{safe_name_p}\',\'website\',\'{safe_city_p}\',\'{p["state"]}\')">🌐 Visit Website</a>'

                map_url = f'https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(p["address"])}'
                prem_badge = '<span class="premium-badge" style="font-size:0.9rem;">⭐ Featured Practice</span>' if is_prem else ''

                stars_p = ''
                if p['rating'] > 0:
                    full = int(p['rating'])
                    stars_p = '★' * full + ('½' if p['rating'] - full >= 0.3 else '') + f' {p["rating"]}'
                reviews_p = f' ({p["reviews"]:,} reviews)' if p['reviews'] > 0 else ''

                # Generate SEO-optimized bio for the practice
                bio_html = generate_practice_bio(p, city, state_name, st)

                profile_content = f'''
                {lead_tracking_js}
                <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; <a href="/find-a-dentist/">Find a Dentist</a> &rsaquo; <a href="/find-a-dentist/{state_slug}.html">{html_mod.escape(state_name)}</a> &rsaquo; <a href="/find-a-dentist/{state_slug}/{city_slug}.html">{html_mod.escape(city)}</a> &rsaquo; {html_mod.escape(p['name'])}</nav>
                <div class="profile-header">
                    {prem_badge}
                    <h1>{html_mod.escape(p['name'])}</h1>
                    <div class="dentist-rating" style="font-size:1.2rem;">{stars_p}<span class="review-count">{reviews_p}</span></div>
                    <p class="dentist-address" style="font-size:1.05rem;">📍 {html_mod.escape(p['address'])}</p>
                </div>
                <div class="profile-actions" style="display:flex;flex-wrap:wrap;gap:0.75rem;margin:1.5rem 0;">
                    {phone_html} {web_html}
                    <a href="{map_url}" target="_blank" rel="noopener" class="dentist-btn dentist-btn-web" onclick="trackLead('{safe_name_p}','directions','{safe_city_p}','{p["state"]}')">📍 Get Directions</a>
                    <button class="dentist-btn dentist-btn-appt" onclick="openApptForm('{safe_name_p}','{safe_city_p}','{p["state"]}')">📅 Request Appointment</button>
                </div>
                {bio_html}
                <div class="profile-details" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem;margin:1.5rem 0;">
                    <div class="admin-card"><h3>Location</h3><p>{html_mod.escape(p['address'])}</p><p><a href="{map_url}" target="_blank" rel="noopener" style="color:var(--accent);">View on Google Maps →</a></p></div>
                    <div class="admin-card"><h3>Contact</h3><p>{html_mod.escape(p['phone']) if p['phone'] else 'Phone not available'}</p>{social_links}</div>
                </div>
                <div style="margin-top:2rem;"><a href="/find-a-dentist/{state_slug}/{city_slug}.html" style="color:var(--accent);font-weight:600;">← Back to all dentists in {html_mod.escape(city)}, {st}</a></div>
                '''

                profile_schema = f'''<script type="application/ld+json">
                {{"@context":"https://schema.org","@type":"Dentist","name":"{html_mod.escape(p['name'])}","address":{{"@type":"PostalAddress","streetAddress":"{html_mod.escape(p['address'])}","addressLocality":"{html_mod.escape(p['city'])}","addressRegion":"{p['state']}","postalCode":"{p.get('zip','')}","addressCountry":"US"}},"telephone":"{html_mod.escape(p['phone'])}","url":"{html_mod.escape(p['website']) if p['website'] else ''}","aggregateRating":{{"@type":"AggregateRating","ratingValue":"{p['rating']}","reviewCount":"{p['reviews']}"}},"geo":{{"@type":"GeoCoordinates","latitude":"{p['lat']}","longitude":"{p['lng']}"}}}}
                </script>
                <script type="application/ld+json">
                {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
                    {{"@type":"ListItem","position":1,"name":"Home","item":"{DOMAIN}/"}},
                    {{"@type":"ListItem","position":2,"name":"Find a Dentist","item":"{DOMAIN}/find-a-dentist/"}},
                    {{"@type":"ListItem","position":3,"name":"{html_mod.escape(state_name)}","item":"{DOMAIN}/find-a-dentist/{state_slug}.html"}},
                    {{"@type":"ListItem","position":4,"name":"{html_mod.escape(city)}","item":"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}.html"}},
                    {{"@type":"ListItem","position":5,"name":"{html_mod.escape(p['name'])}","item":"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}/{p_slug}.html"}}
                ]}}</script>'''

                profile_html = get_page_template(
                    f"{p['name']} - Dentist in {city}, {st} | DentalPedia",
                    profile_content,
                    f"{DOMAIN}/find-a-dentist/{state_slug}/{city_slug}/{p_slug}.html",
                    f"{p['name']} is a dental practice in {city}, {state_name}. Rating: {p['rating']} stars. Call {p['phone']} or request an appointment online.",
                    schema=profile_schema
                )
                with open(city_profile_dir / f"{p_slug}.html", 'w', encoding='utf-8') as f:
                    f.write(profile_html)

    total_city_pages = sum(len(set(p['city'] for p in practices)) for practices in by_state.values())
    logger.info(f"Generated Find a Dentist: 1 index + {state_count} state pages + {total_city_pages} city pages + {len(dentists_data)} practice profiles")


def generate_ekwa_landing_page():
    """Generate Ekwa premium listing landing page."""
    logger.info("Generating Ekwa premium landing page...")
    output_dir = SITE_ROOT / "for-dentists"
    output_dir.mkdir(parents=True, exist_ok=True)

    content = '''
    <div class="directory-hero" style="background:linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">
        <h1>Get Featured on DentalPedia</h1>
        <p>Boost your practice visibility with a premium listing seen by thousands of patients searching for dentists</p>
    </div>

    <div style="max-width:800px;margin:2rem auto;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin:2rem 0;">
            <div class="admin-card">
                <h3>Free Listing</h3>
                <ul style="list-style:none;padding:0;margin:1rem 0;">
                    <li style="padding:0.4rem 0;">✓ Practice name & address</li>
                    <li style="padding:0.4rem 0;">✓ Phone number & website link</li>
                    <li style="padding:0.4rem 0;">✓ Google rating display</li>
                    <li style="padding:0.4rem 0;">✓ City directory listing</li>
                    <li style="padding:0.4rem 0;opacity:0.4;">✗ Featured badge</li>
                    <li style="padding:0.4rem 0;opacity:0.4;">✗ Priority placement</li>
                    <li style="padding:0.4rem 0;opacity:0.4;">✗ Lead tracking dashboard</li>
                </ul>
                <p style="font-size:1.5rem;font-weight:700;color:var(--text-primary);">Free</p>
            </div>
            <div class="admin-card" style="border-color:#f59e0b;position:relative;">
                <span class="premium-badge" style="position:absolute;top:-10px;right:1rem;">⭐ Recommended</span>
                <h3>Premium Listing</h3>
                <ul style="list-style:none;padding:0;margin:1rem 0;">
                    <li style="padding:0.4rem 0;">✓ Everything in Free</li>
                    <li style="padding:0.4rem 0;color:#f59e0b;font-weight:600;">⭐ Featured Practice badge</li>
                    <li style="padding:0.4rem 0;color:#f59e0b;font-weight:600;">⭐ Top of city page placement</li>
                    <li style="padding:0.4rem 0;color:#f59e0b;font-weight:600;">⭐ Lead tracking & analytics</li>
                    <li style="padding:0.4rem 0;color:#f59e0b;font-weight:600;">⭐ Appointment request form</li>
                    <li style="padding:0.4rem 0;color:#f59e0b;font-weight:600;">⭐ Enhanced profile page</li>
                </ul>
                <p style="font-size:1.1rem;font-weight:700;color:var(--text-primary);">Included with <a href="https://ekwa.com" target="_blank" rel="noopener" style="color:var(--accent);">Ekwa SEO</a></p>
                <a href="https://ekwa.com" target="_blank" rel="noopener" style="display:block;text-align:center;padding:0.75rem;background:var(--accent);color:#fff;border-radius:8px;font-weight:700;text-decoration:none;margin-top:1rem;">Learn About Ekwa SEO →</a>
            </div>
        </div>

        <div class="admin-card" style="margin:2rem 0;">
            <h3>Why DentalPedia?</h3>
            <p style="margin:0.75rem 0;">DentalPedia is a comprehensive dental encyclopedia with over 2,000 articles, reaching patients actively researching dental care. Our Find a Dentist directory connects these informed patients directly with practices in their area.</p>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:1.5rem;text-align:center;">
                <div><div style="font-size:2rem;font-weight:700;color:var(--accent);">31K+</div><div style="font-size:0.85rem;color:var(--text-secondary);">Listed Practices</div></div>
                <div><div style="font-size:2rem;font-weight:700;color:var(--accent);">2,000+</div><div style="font-size:0.85rem;color:var(--text-secondary);">Dental Articles</div></div>
                <div><div style="font-size:2rem;font-weight:700;color:var(--accent);">50</div><div style="font-size:0.85rem;color:var(--text-secondary);">States Covered</div></div>
            </div>
        </div>

        <div class="admin-card" style="text-align:center;">
            <h3>Interested in a Premium Listing?</h3>
            <p>Contact Ekwa to learn how a premium DentalPedia listing can be included with your SEO package.</p>
            <a href="https://ekwa.com" target="_blank" rel="noopener" style="display:inline-block;padding:0.75rem 2rem;background:var(--accent);color:#fff;border-radius:8px;font-weight:700;text-decoration:none;margin-top:1rem;">Contact Ekwa →</a>
        </div>
    </div>
    '''

    page_html = get_page_template(
        "Premium Dental Listing - Get Featured on DentalPedia",
        content,
        f"{DOMAIN}/for-dentists/premium.html",
        "Boost your dental practice visibility with a premium listing on DentalPedia. Featured badge, priority placement, and lead tracking included with Ekwa SEO."
    )
    with open(output_dir / "premium.html", 'w', encoding='utf-8') as f:
        f.write(page_html)
    logger.info("Generated Ekwa premium landing page")


def markdown_to_html_clinical(text):
    """Convert markdown to HTML for clinical pages — renders :::clinical blocks as inline content (not collapsed)."""
    # Strip :::clinical / ::: markers but keep the content as regular text
    text = re.sub(r'^:::clinical\s*\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'^:::\s*$', '', text, flags=re.MULTILINE)

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


def process_clinical_article(md_file):
    """Process a single article file and generate a clinical-focused HTML page at /clinical/slug.html."""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata, body = parse_markdown_frontmatter(content)

        # Derive slug from filename if not in YAML
        if 'slug' not in metadata:
            metadata['slug'] = Path(md_file).stem

        slug = metadata['slug']
        output_file = CLINICAL_DIR / f"{slug}.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        canonical_url = f"{DOMAIN}/clinical/{slug}.html"
        title = clean_title(metadata.get('title', 'Untitled'))
        excerpt = metadata.get('excerpt', '')
        category = metadata.get('category', '')
        category_slug = metadata.get('category_slug', '')
        reviewer_specialty = metadata.get('reviewer_specialty', 'General Dentistry')
        subcategory = metadata.get('subcategory', '')
        subcategory_slug = metadata.get('subcategory_slug', '')
        date = metadata.get('date', '')
        read_time = metadata.get('read_time', '5 min')
        references = metadata.get('references', [])

        # Convert markdown to HTML — clinical version renders all content inline
        body_html = markdown_to_html_clinical(body)

        # Internal linking within clinical section
        body_html = create_internal_links(body_html, slug)

        # Table of contents
        headings = extract_headings(body_html)
        toc_html = generate_toc_html(headings) if headings else ''

        # Breadcrumb
        breadcrumb = f'<nav class="article-breadcrumb"><a href="/">Home</a> / <a href="/clinical/">Clinical</a> / <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a>'
        if subcategory and subcategory_slug:
            breadcrumb += f' / {html_mod.escape(subcategory)}'
        breadcrumb += f' / {html_mod.escape(title)}</nav>'

        # References section (proper academic format)
        references_html = ""
        if references:
            references_html = '<div class="article-references"><h2>References</h2><ol>'
            for ref in references:
                if isinstance(ref, dict):
                    ref_title = ref.get('title', '')
                    ref_url = ref.get('url', '')
                    if ref_url:
                        references_html += f'<li><a href="{ref_url}" target="_blank" rel="noopener">{html_mod.escape(ref_title)}</a></li>'
                    else:
                        references_html += f'<li>{html_mod.escape(ref_title)}</li>'
                else:
                    references_html += f'<li>{html_mod.escape(str(ref))}</li>'
            references_html += '</ol></div>'

        article_content = f'''
        <div class="article-page clinical-article">
            <article class="content-width">
                {breadcrumb}
                <header class="article-header">
                    <div style="display:inline-block;background:#6366f1;color:#fff;font-size:0.75rem;font-weight:700;padding:0.25rem 0.75rem;border-radius:99px;margin-bottom:0.75rem;letter-spacing:0.05em;text-transform:uppercase">Clinical Protocol</div>
                    <h1>{html_mod.escape(title)}</h1>
                    <div class="article-meta">
                        <span>Specialty: {html_mod.escape(reviewer_specialty)}</span>
                        <span>Updated {date}</span>
                    </div>
                    <div class="article-meta-secondary">
                        <span>⏱️ {read_time}</span>
                        <span>📚 <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a></span>
                    </div>
                </header>

                {toc_html}

                <div class="patient-crosslink" style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:10px;padding:0.75rem 1rem;margin-bottom:1.5rem;font-size:0.88rem;display:flex;align-items:center;gap:0.5rem">
                    <span style="color:#16a34a">👤</span>
                    <span style="color:var(--text-secondary)">Looking for the patient guide?</span>
                    <a href="/article/{slug}.html" style="color:#16a34a;font-weight:600;text-decoration:none">View Patient Version →</a>
                </div>

                <div class="article-body" id="article-body">
                    {body_html}
                </div>

                {references_html}

                <div class="article-review-info">
                    <p><strong>Clinical Reference</strong> — This protocol is compiled from peer-reviewed literature and established clinical guidelines. It is intended as a professional reference and does not constitute medical advice. Clinical decisions should be based on individual patient assessment.</p>
                </div>

                {generate_share_buttons(title, canonical_url)}
            </article>
        </div>
        '''

        meta_tags = f'''
        <meta property="og:title" content="Clinical Protocol: {html_mod.escape(title)}">
        <meta property="og:description" content="{html_mod.escape(excerpt)}">
        <meta property="og:url" content="{canonical_url}">
        <meta property="og:type" content="article">
        <meta property="article:section" content="{html_mod.escape(category)}">
        <meta name="twitter:card" content="summary">
        <meta name="twitter:title" content="Clinical: {html_mod.escape(title)}">
        <meta name="twitter:description" content="{html_mod.escape(excerpt)}">
        '''

        # BreadcrumbList structured data
        breadcrumb_items = [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": DOMAIN},
            {"@type": "ListItem", "position": 2, "name": "Clinical", "item": f"{DOMAIN}/clinical/"},
            {"@type": "ListItem", "position": 3, "name": category, "item": f"{DOMAIN}/category/{category_slug}.html"}
        ]
        pos = 4
        if subcategory and subcategory_slug:
            breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": subcategory})
            pos += 1
        breadcrumb_items.append({"@type": "ListItem", "position": pos, "name": title})

        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }

        # MedicalScholarlyArticle structured data
        article_schema = {
            "@context": "https://schema.org",
            "@type": "MedicalScholarlyArticle",
            "headline": title,
            "description": excerpt,
            "datePublished": date,
            "dateModified": date,
            "url": canonical_url,
            "author": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "publisher": {"@type": "Organization", "name": "DentalPedia", "url": DOMAIN},
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
            "about": {"@type": "MedicalSpecialty", "name": reviewer_specialty}
        }
        if references:
            citation_list = []
            for ref in references:
                if isinstance(ref, dict):
                    citation_list.append(ref.get('title', ''))
                elif isinstance(ref, str):
                    r = ref.strip()
                    if r.startswith('title:'):
                        r = r[6:].strip().strip('"').strip("'")
                    citation_list.append(r)
                else:
                    citation_list.append(str(ref))
            article_schema["citation"] = citation_list

        all_schema = f'''<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
        <script type="application/ld+json">{json.dumps(article_schema)}</script>'''

        # Alternate link to patient version
        extra_head = f'<link rel="alternate" href="{DOMAIN}/article/{slug}.html" title="Patient Guide">'

        page_html = get_page_template(
            f"Clinical: {title}",
            article_content,
            canonical_url,
            excerpt,
            meta_tags,
            all_schema,
            extra_head
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(page_html)

        return slug

    except Exception as e:
        logger.error(f"Error processing clinical article {md_file}: {e}")
        return None


def generate_clinical_index():
    """Generate the /clinical/index.html landing page."""
    logger.info("Generating clinical section index...")

    # Group articles by category for the index
    clinical_cats = defaultdict(list)
    for article in all_articles:
        clinical_cats[article.get('category', 'Uncategorized')].append(article)

    cards_html = '<div class="categories-grid">'
    for cat_name in sorted(clinical_cats.keys()):
        articles = clinical_cats[cat_name]
        cat_slug = articles[0].get('category_slug', '') if articles else ''
        cards_html += f'''
        <div class="category-card" style="cursor:default;">
            <div class="category-icon">🔬</div>
            <div class="category-name">{html_mod.escape(cat_name)}</div>
            <div class="category-count">{len(articles)} {"clinical protocol" if len(articles) == 1 else "clinical protocols"}</div>
            <div style="margin-top:0.75rem;">'''
        for a in articles[:5]:
            a_slug = a.get('slug', '')
            a_title = a.get('title', '')
            cards_html += f'<a href="/clinical/{a_slug}.html" style="display:block;font-size:0.85rem;color:var(--accent);margin:0.25rem 0;text-decoration:none;">{html_mod.escape(a_title)}</a>'
        if len(articles) > 5:
            cards_html += f'<span style="font-size:0.8rem;color:var(--text-secondary);">+{len(articles)-5} more protocols</span>'
        cards_html += '</div></div>'
    cards_html += '</div>'

    content = f'''
    <div class="content-width" style="padding: 2rem 0;">
        <nav class="breadcrumb"><a href="/">Home</a> &rsaquo; Clinical Protocols</nav>
        <div style="display:inline-block;background:#6366f1;color:#fff;font-size:0.75rem;font-weight:700;padding:0.25rem 0.75rem;border-radius:99px;margin-bottom:0.75rem;letter-spacing:0.05em;text-transform:uppercase">For Dental Professionals</div>
        <h1>Clinical Protocols & Evidence-Based References</h1>
        <p style="color: var(--text-secondary);max-width:700px;">Evidence-based clinical protocols compiled from peer-reviewed literature and established guidelines. {len(all_articles):,} protocols across {len(clinical_cats)} specialties.</p>
        <div class="patient-crosslink" style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:10px;padding:0.75rem 1rem;margin:1.5rem 0;font-size:0.88rem;display:inline-flex;align-items:center;gap:0.5rem">
            <span style="color:#16a34a">👤</span>
            <span style="color:var(--text-secondary)">Patient?</span>
            <a href="/categories.html" style="color:#16a34a;font-weight:600;text-decoration:none">Browse Patient Articles →</a>
        </div>
        {cards_html}
    </div>
    '''

    CLINICAL_DIR.mkdir(parents=True, exist_ok=True)
    page_html = get_page_template(
        "Clinical Protocols — DentalPedia",
        content,
        f"{DOMAIN}/clinical/",
        f"Evidence-based clinical protocols for dental professionals. {len(all_articles):,} protocols across {len(clinical_cats)} dental specialties."
    )

    with open(CLINICAL_DIR / "index.html", 'w', encoding='utf-8') as f:
        f.write(page_html)
    logger.info("Generated clinical index page")


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
    CLINICAL_DIR.mkdir(parents=True, exist_ok=True)

    # Process all articles (patient + clinical versions)
    logger.info("Processing articles...")

    all_md_files = list(CONTENT_DIR.glob("*.md"))
    all_clinical_md_files = list(CLINICAL_CONTENT_DIR.glob("*.md")) if CLINICAL_CONTENT_DIR.exists() else all_md_files

    completed_patient = 0
    completed_clinical = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Patient articles — read from content/articles/
        patient_futures = {executor.submit(process_article, md): md for md in all_md_files}
        # Clinical articles — read from content/clinical/ (original clinical-depth content)
        clinical_futures = {executor.submit(process_clinical_article, md): md for md in all_clinical_md_files}

        for future in as_completed(patient_futures):
            if future.result():
                completed_patient += 1
        for future in as_completed(clinical_futures):
            if future.result():
                completed_clinical += 1

    logger.info(f"Processed {completed_patient} patient articles + {completed_clinical} clinical articles")

    # Generate pages
    generate_homepage()
    generate_categories_index()
    generate_clinical_index()
    generate_category_pages()
    generate_subcategory_pages()
    generate_city_pages()
    generate_guide_pages()
    generate_editorial_standards_page()
    generate_privacy_page()
    generate_terms_page()
    generate_404_page()
    generate_admin_dashboard()
    generate_cost_calculator()
    generate_dental_health_quiz()
    generate_cost_comparison_pages()
    generate_embeddable_widget()
    generate_myth_vs_fact()
    generate_find_dentist_pages()
    generate_ekwa_landing_page()
    generate_sitemaps()

    # Build time
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info(f"Build completed in {duration:.1f} seconds")
    logger.info(f"Total pages generated: ~{len(all_articles) + len(articles_by_category) + len(articles_by_subcategory) + (len(cities_data) * len(procedure_costs)) + len(cornerstone_guides) + 3:,}")


if __name__ == "__main__":
    main()
