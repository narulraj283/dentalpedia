#!/usr/bin/env python3
"""
DentalPedia Build Script (v2)
=============================
Converts Markdown articles in content/articles/ into HTML pages in article/
Generates dynamic category pages, homepage, categories page, dentists page.
Generates search-index.json and sitemap.xml

Features:
- Processes 200+ articles efficiently with parallel processing
- Dynamic category pages with pagination (20 per page)
- Dynamic homepage showing latest 8 articles and real category stats
- Enhanced markdown parser (tables, blockquotes, images, horizontal rules, nested lists)
- Internal article linking
- Sitemap with proper date handling
- Dynamic dentists page from data/clients.json

Usage:
  python3 build.py

Each markdown file should have YAML frontmatter:
---
title: Article Title
slug: article-slug
category: Category Name
category_slug: category-slug
excerpt: Short description of the article.
reviewer_name: Dr. Jane Smith, DDS
reviewer_credentials: Board-Certified Prosthodontist
reviewer_practice: Smith Family Dentistry
reviewer_location: San Francisco, CA
reviewer_url: https://example.com
sources:
  - title: ADA — Dental Implants
    url: https://www.ada.org/resources/dental-implants
  - title: NIH — Implant Success Rates
    url: https://pubmed.ncbi.nlm.nih.gov/12345678/
date: 2026-03-01
read_time: 8 min
---

Article body in Markdown...
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

# Paths
BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content" / "articles"
OUTPUT_DIR = BASE_DIR / "article"
DATA_DIR = BASE_DIR / "data"
SEARCH_INDEX_PATH = BASE_DIR / "search-index.json"
SITEMAP_PATH = BASE_DIR / "sitemap.xml"
DOMAIN = "https://dentalpedia.co"
ARTICLES_PER_PAGE = 20
LATEST_ARTICLES_COUNT = 8

# GA4 Tracking
GA_MEASUREMENT_ID = "G-XXXXXXXXXX"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def parse_frontmatter(text):
    """Parse YAML-like frontmatter from markdown text."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("---", 3)
    if end == -1:
        return {}, text

    fm_text = text[3:end].strip()
    body = text[end + 3:].strip()

    meta = {}
    current_key = None
    current_list = None

    for line in fm_text.split("\n"):
        line_stripped = line.strip()

        # List item
        if line_stripped.startswith("- ") and current_list is not None:
            item_text = line_stripped[2:].strip()
            if ":" in item_text:
                key, val = item_text.split(":", 1)
                current_list.append({key.strip(): val.strip()})
            else:
                current_list.append(item_text)
            continue

        # Continuation of a dict item in list
        if line_stripped and ":" in line_stripped and current_list and isinstance(current_list, list) and current_list and isinstance(current_list[-1], dict):
            key, val = line_stripped.split(":", 1)
            current_list[-1][key.strip()] = val.strip()
            continue

        # Key: value pair
        if ":" in line_stripped and not line_stripped.startswith("-"):
            key, val = line_stripped.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val == "":
                current_key = key
                current_list = []
                meta[key] = current_list
            else:
                current_key = key
                current_list = None
                meta[key] = val

    return meta, body


def markdown_to_html(md_text, all_articles=None):
    """Enhanced markdown to HTML converter with tables, blockquotes, images, etc."""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False
    list_type = None
    in_table = False
    table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Empty line
        if not stripped:
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append("")
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            html_lines.append("<hr>")
            i += 1
            continue

        # Blockquote
        if stripped.startswith("> "):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            blockquote_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                blockquote_lines.append(lines[i].strip()[2:])
                i += 1
            html_lines.append(f"<blockquote>{process_inline(chr(10).join(blockquote_lines), all_articles)}</blockquote>")
            continue

        # Table detection (simple pipe-based tables)
        if "|" in stripped and "|" in lines[i]:
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            
            table_lines = []
            while i < len(lines) and "|" in lines[i].strip():
                table_lines.append(lines[i].strip())
                i += 1
            
            table_html = build_table_html(table_lines)
            html_lines.append(table_html)
            continue

        # Headers
        if stripped.startswith("######"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            html_lines.append(f'<h6>{process_inline(stripped[6:].strip(), all_articles)}</h6>')
            i += 1
            continue
        if stripped.startswith("#####"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            html_lines.append(f'<h5>{process_inline(stripped[5:].strip(), all_articles)}</h5>')
            i += 1
            continue
        if stripped.startswith("####"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            html_lines.append(f'<h4>{process_inline(stripped[4:].strip(), all_articles)}</h4>')
            i += 1
            continue
        if stripped.startswith("###"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            content = stripped[3:].strip()
            slug = slugify(content)
            html_lines.append(f'<h3 id="{slug}">{process_inline(content, all_articles)}</h3>')
            i += 1
            continue
        if stripped.startswith("##"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            content = stripped[2:].strip()
            slug = slugify(content)
            html_lines.append(f'<h2 id="{slug}">{process_inline(content, all_articles)}</h2>')
            i += 1
            continue
        if stripped.startswith("#"):
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            content = stripped[1:].strip()
            html_lines.append(f'<h1>{process_inline(content, all_articles)}</h1>')
            i += 1
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list or list_type != "ul":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ul>")
                in_list = True
                list_type = "ul"
            html_lines.append(f"<li>{process_inline(stripped[2:].strip(), all_articles)}</li>")
            i += 1
            continue

        # Ordered list
        ol_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        if ol_match:
            if not in_list or list_type != "ol":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ol>")
                in_list = True
                list_type = "ol"
            html_lines.append(f"<li>{process_inline(ol_match.group(1), all_articles)}</li>")
            i += 1
            continue

        # Close list if we hit a non-list item
        if in_list:
            html_lines.append(f"</{list_type}>")
            in_list = False

        # Paragraph
        html_lines.append(f"<p>{process_inline(stripped, all_articles)}</p>")
        i += 1

    if in_list:
        html_lines.append(f"</{list_type}>")

    return "\n".join(html_lines)


def build_table_html(table_lines):
    """Convert pipe-separated table to HTML table."""
    if not table_lines:
        return ""
    
    rows = []
    for i, line in enumerate(table_lines):
        cells = [cell.strip() for cell in line.split("|")]
        cells = [c for c in cells if c]
        rows.append(cells)
    
    if not rows:
        return ""
    
    html = "<table>\n"
    
    # Header row
    if len(rows) > 0:
        html += "  <thead>\n    <tr>\n"
        for cell in rows[0]:
            html += f"      <th>{html_mod.escape(cell)}</th>\n"
        html += "    </tr>\n  </thead>\n"
    
    # Body rows
    if len(rows) > 1:
        html += "  <tbody>\n"
        for row in rows[1:]:
            html += "    <tr>\n"
            for cell in row:
                html += f"      <td>{html_mod.escape(cell)}</td>\n"
            html += "    </tr>\n"
        html += "  </tbody>\n"
    
    html += "</table>"
    return html


def process_inline(text, all_articles=None):
    """Process inline markdown (bold, italic, links, code, images)."""
    if not text:
        return text
    
    # Images ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" loading="lazy">', text)
    
    # Links [text](url) - but avoid URLs
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # Internal article linking (if all_articles provided)
    if all_articles:
        text = create_internal_links(text, all_articles)
    
    # Bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Italic *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    
    # Code `text`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    
    return text


def create_internal_links(text, all_articles):
    """Auto-link mentions of other articles (optimized for large article sets)."""
    if not all_articles:
        return text

    # Only check short, distinctive titles (skip very short or generic ones)
    # Limit to max 200 titles for performance
    candidates = []
    for article in all_articles:
        title = article.get("title", "")
        slug = article.get("slug", "")
        if title and slug and len(title) > 15 and len(title) < 80:
            candidates.append((title, slug))

    # Sort by title length descending (match longer titles first)
    candidates.sort(key=lambda x: -len(x[0]))

    # Only check first 100 candidates and stop after 5 links
    links_added = 0
    for original_title, slug in candidates[:100]:
        if links_added >= 5:
            break
        if original_title.lower() in text.lower():
            pattern = r'(?<!</a>)(?<![>"\w])' + re.escape(original_title) + r'(?![<"\w])'
            if re.search(pattern, text, re.IGNORECASE):
                replacement = f'<a href="/article/{slug}.html">{original_title}</a>'
                text = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)
                links_added += 1

    return text


def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    text = text.strip('-')
    return text


def extract_toc(md_text):
    """Extract table of contents from h2 and h3 headers."""
    toc = []
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            title = stripped[3:].strip()
            toc.append({"title": title, "slug": slugify(title), "level": 2})
        elif stripped.startswith("### ") and not stripped.startswith("####"):
            title = stripped[4:].strip()
            toc.append({"title": title, "slug": slugify(title), "level": 3})
    return toc


def find_related_articles(current_article, all_articles, limit=4):
    """Find 3-4 related articles from the same or adjacent categories."""
    current_category = current_article.get("category", "")
    current_slug = current_article.get("slug", "")

    # Get articles from the same category, excluding current
    same_category = [a for a in all_articles
                     if a.get("category") == current_category
                     and a.get("slug") != current_slug]

    # If we need more, grab from other categories
    related = same_category[:limit]

    if len(related) < limit:
        other_category = [a for a in all_articles
                         if a.get("category") != current_category
                         and a.get("slug") != current_slug]
        related.extend(other_category[:limit - len(related)])

    return related[:limit]


def build_article_html(meta, body_html, toc, related_articles=None):
    """Build a complete article HTML page."""
    title = meta.get("title", "Untitled")
    slug = meta.get("slug", "untitled")
    category = meta.get("category", "General")
    category_slug = meta.get("category_slug", "general-dentistry")
    excerpt = meta.get("excerpt", "")
    date = meta.get("date", datetime.now().strftime("%Y-%m-%d"))
    read_time = meta.get("read_time", "5 min")

    # Reviewer
    reviewer_name = meta.get("reviewer_name", "")
    reviewer_credentials = meta.get("reviewer_credentials", "")
    reviewer_practice = meta.get("reviewer_practice", "")
    reviewer_location = meta.get("reviewer_location", "")
    reviewer_url = meta.get("reviewer_url", "")
    reviewer_slug = slugify(reviewer_name.split(",")[0]) if reviewer_name else ""

    # Sources
    sources = meta.get("sources", [])

    # Format date
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = dt.strftime("%B %d, %Y")
    except:
        formatted_date = date

    # Build TOC HTML
    toc_html = ""
    if toc:
        toc_items = "\n".join(
            f'          <li><a href="#{t["slug"]}">{html_mod.escape(t["title"])}</a></li>'
            for t in toc
        )
        toc_html = f"""
      <div class="toc">
        <div class="toc-title">Contents</div>
        <ol class="toc-list">
{toc_items}
        </ol>
      </div>"""

    # Build reviewer card with link to dentist profile
    reviewer_html = ""
    if reviewer_name:
        reviewer_link = ""
        if reviewer_url:
            display_url = reviewer_url.replace("https://", "").replace("http://", "").rstrip("/")
            reviewer_link = f'<div class="eeat-link"><a href="{html_mod.escape(reviewer_url)}" target="_blank">&rarr; {html_mod.escape(display_url)}</a></div>'

        reviewer_profile_link = f'<a href="/dentist/{reviewer_slug}.html" class="dentist-profile-btn">View Profile</a>'

        reviewer_html = f"""
      <div class="eeat-card">
        <div class="eeat-icon">🦷</div>
        <div class="eeat-content">
          <div class="eeat-label">Expert Reviewer</div>
          <div class="eeat-name">{html_mod.escape(reviewer_name)}</div>
          <div class="eeat-credentials">{html_mod.escape(reviewer_credentials)} &middot; {html_mod.escape(reviewer_practice)} &middot; {html_mod.escape(reviewer_location)}</div>
          {reviewer_link}
          {reviewer_profile_link}
        </div>
      </div>"""

    # Build sources card
    sources_html = ""
    if sources:
        source_items = []
        for s in sources:
            if isinstance(s, dict):
                s_title = s.get("title", "Source")
                s_url = s.get("url", "#")
                source_items.append(
                    f'<li><a href="{html_mod.escape(s_url)}" target="_blank" rel="noopener">{html_mod.escape(s_title)}</a></li>'
                )
        if source_items:
            sources_html = f"""
      <div class="sources-card">
        <div class="sources-title">📚 Sources</div>
        <ul class="sources-list">
          {"".join(source_items)}
        </ul>
      </div>"""

    # Build related articles section
    related_html = ""
    if related_articles:
        related_items = ""
        for rel_article in related_articles[:4]:
            rel_title = rel_article.get("title", "")
            rel_slug = rel_article.get("slug", "")
            rel_excerpt = rel_article.get("excerpt", "")
            related_items += f"""
        <div class="related-article">
          <a href="/article/{rel_slug}.html" class="related-title">{html_mod.escape(rel_title)}</a>
          <p class="related-excerpt">{html_mod.escape(rel_excerpt)}</p>
        </div>"""

        related_html = f"""
      <div class="related-articles">
        <h3>Related Articles</h3>
{related_items}
      </div>"""

    # Build find a dentist widget
    dentist_widget = """
      <div class="find-dentist-widget">
        <div class="widget-title">🦷 Find a Dentist Near You</div>
        <p>Connect with one of our expert dental professionals.</p>
        <a href="/dentists.html" class="btn-find-dentist">View Expert Dentists →</a>
      </div>"""

    # Schema.org JSON-LD - Breadcrumb
    breadcrumb_items = [
        {"position": 1, "name": "Home", "item": DOMAIN},
        {"position": 2, "name": category, "item": f"{DOMAIN}/category/{category_slug}.html"},
        {"position": 3, "name": title, "item": f"{DOMAIN}/article/{slug}.html"}
    ]

    breadcrumb_schema = f"""
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": {json.dumps(breadcrumb_items)}
  }}
  </script>"""

    # Schema.org JSON-LD
    schema_reviewer = ""
    if reviewer_name:
        schema_reviewer = f""",
    "reviewedBy": {{
      "@type": "Person",
      "name": "{reviewer_name}",
      "jobTitle": "{reviewer_credentials}",
      "url": "{reviewer_url}"
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html_mod.escape(title)} — DentalPedia</title>
  <meta name="description" content="{html_mod.escape(excerpt)}">
  <meta property="og:title" content="{html_mod.escape(title)} — DentalPedia">
  <meta property="og:description" content="{html_mod.escape(excerpt)}">
  <meta property="og:type" content="article">
  <link rel="canonical" href="{DOMAIN}/article/{slug}.html">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "MedicalWebPage",
    "name": "{title}",
    "description": "{excerpt}",
    "url": "{DOMAIN}/article/{slug}.html",
    "datePublished": "{date}",
    "dateModified": "{date}",
    "publisher": {{
      "@type": "Organization",
      "name": "DentalPedia",
      "url": "{DOMAIN}"
    }}{schema_reviewer},
    "medicalAudience": {{
      "@type": "PatientAudience",
      "audienceType": "Patient"
    }}
  }}
  </script>
  {breadcrumb_schema}
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="article-page">
    <div class="container content-width">
      <div class="article-breadcrumb">
        <a href="/">Home</a> &rsaquo;
        <a href="/category/{category_slug}.html">{html_mod.escape(category)}</a> &rsaquo;
        {html_mod.escape(title)}
      </div>

      <header class="article-header">
        <h1>{html_mod.escape(title)}</h1>
        <div class="article-meta">
          <span>📅 Updated {formatted_date}</span>
          <span>📂 {html_mod.escape(category)}</span>
          <span>⏱️ {html_mod.escape(read_time)} read</span>
          <a href="/suggest.html?article={slug}" class="suggest-edit-btn">✏️ Suggest Edit</a>
        </div>
      </header>
{toc_html}

      <article class="article-body">
{body_html}
      </article>

{dentist_widget}

{related_html}

{reviewer_html}
{sources_html}

      <div class="disclaimer">
        <span class="disclaimer-icon">⚕️</span>
        <span>This article is AI-generated and reviewed by a licensed dental professional for accuracy. It is intended for informational purposes only and is not a substitute for professional dental advice, diagnosis, or treatment. Always consult your dentist.</span>
      </div>
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_category_page_html(category, category_slug, articles_in_category, page_num):
    """Build a category page with pagination."""
    total_pages = math.ceil(len(articles_in_category) / ARTICLES_PER_PAGE)
    start_idx = (page_num - 1) * ARTICLES_PER_PAGE
    end_idx = start_idx + ARTICLES_PER_PAGE
    page_articles = articles_in_category[start_idx:end_idx]

    article_cards = ""
    for article in page_articles:
        article_cards += f"""
      <div class="article-card">
        <div class="article-card-title"><a href="/article/{article['slug']}.html">{html_mod.escape(article['title'])}</a></div>
        <div class="article-card-meta">
          <span>📅 {article.get('date', 'N/A')}</span>
          <span>⏱️ {article.get('read_time', '5 min')}</span>
        </div>
        <p class="article-card-excerpt">{html_mod.escape(article.get('excerpt', ''))}</p>
        <a href="/article/{article['slug']}.html" class="article-card-link">Read more &rarr;</a>
      </div>"""

    # Pagination HTML
    pagination_html = ""
    if total_pages > 1:
        pagination_html = '<div class="pagination">'
        
        if page_num > 1:
            if page_num == 2:
                pagination_html += f'<a href="/category/{category_slug}.html" class="pagination-link">← Previous</a>'
            else:
                pagination_html += f'<a href="/category/{category_slug}-page-{page_num - 1}.html" class="pagination-link">← Previous</a>'
        
        for i in range(1, total_pages + 1):
            if i == page_num:
                pagination_html += f'<span class="pagination-current">{i}</span>'
            else:
                if i == 1:
                    pagination_html += f'<a href="/category/{category_slug}.html" class="pagination-link">{i}</a>'
                else:
                    pagination_html += f'<a href="/category/{category_slug}-page-{i}.html" class="pagination-link">{i}</a>'
        
        if page_num < total_pages:
            pagination_html += f'<a href="/category/{category_slug}-page-{page_num + 1}.html" class="pagination-link">Next →</a>'
        
        pagination_html += '</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html_mod.escape(category)} Articles — DentalPedia</title>
  <meta name="description" content="Articles about {html_mod.escape(category)} on DentalPedia">
  <meta property="og:title" content="{html_mod.escape(category)} Articles — DentalPedia">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{DOMAIN}/category/{category_slug}.html">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="category-page">
    <div class="container content-width">
      <header class="category-header">
        <div class="breadcrumb">
          <a href="/">Home</a> &rsaquo;
          <a href="/categories.html">Categories</a> &rsaquo;
          {html_mod.escape(category)}
        </div>
        <h1>{html_mod.escape(category)}</h1>
        <p class="category-count">{len(articles_in_category)} articles</p>
      </header>

      <div class="articles-grid">
{article_cards}
      </div>

{pagination_html}
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_homepage_html(articles, categories_with_counts):
    """Build dynamic homepage with latest articles and category stats."""
    # Sort articles by date (newest first) and get latest 8
    sorted_articles = sorted(articles, key=lambda x: x.get('date', ''), reverse=True)
    latest = sorted_articles[:LATEST_ARTICLES_COUNT]

    latest_html = ""
    for article in latest:
        latest_html += f"""
      <div class="article-card">
        <div class="article-card-category">{html_mod.escape(article.get('category', ''))}</div>
        <div class="article-card-title"><a href="/article/{article['slug']}.html">{html_mod.escape(article['title'])}</a></div>
        <div class="article-card-meta">
          <span>📅 {article.get('date', 'N/A')}</span>
          <span>⏱️ {article.get('read_time', '5 min')}</span>
        </div>
        <p class="article-card-excerpt">{html_mod.escape(article.get('excerpt', ''))}</p>
        <a href="/article/{article['slug']}.html" class="article-card-link">Read more &rarr;</a>
      </div>"""

    # Categories with counts
    category_html = ""
    for category_name, count in sorted(categories_with_counts.items()):
        cat_slug = slugify(category_name)
        category_html += f"""
      <div class="category-tile">
        <div class="category-tile-title"><a href="/category/{cat_slug}.html">{html_mod.escape(category_name)}</a></div>
        <div class="category-tile-count">{count} article{"s" if count != 1 else ""}</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DentalPedia — Expert Dental Information</title>
  <meta name="description" content="DentalPedia: AI-generated dental articles reviewed by licensed professionals. Explore {len(articles)} articles across all dental topics.">
  <meta property="og:title" content="DentalPedia — Expert Dental Information">
  <meta property="og:description" content="Explore expert dental information reviewed by licensed professionals.">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{DOMAIN}/">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="homepage">
    <div class="hero">
      <div class="container">
        <h1>🦷 Expert Dental Information</h1>
        <p>Over {len(articles)} articles reviewed by licensed dental professionals</p>
        <a href="/categories.html" class="btn btn-primary">Explore Topics</a>
      </div>
    </div>

    <div class="container content-width">
      <section class="latest-articles">
        <h2>Latest Articles</h2>
        <div class="articles-grid">
{latest_html}
        </div>
        <div class="view-all-link">
          <a href="/categories.html">View all articles &rarr;</a>
        </div>
      </section>

      <section class="categories-section">
        <h2>Browse Categories</h2>
        <div class="categories-grid">
{category_html}
        </div>
      </section>
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_categories_page_html(categories_with_counts):
    """Build a page listing all categories."""
    category_html = ""
    for category_name, count in sorted(categories_with_counts.items()):
        cat_slug = slugify(category_name)
        category_html += f"""
      <div class="category-list-item">
        <a href="/category/{cat_slug}.html" class="category-list-name">{html_mod.escape(category_name)}</a>
        <span class="category-list-count">{count} article{"s" if count != 1 else ""}</span>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>All Categories — DentalPedia</title>
  <meta name="description" content="Browse all dental categories on DentalPedia">
  <meta property="og:title" content="All Categories — DentalPedia">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{DOMAIN}/categories.html">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="categories-page">
    <div class="container content-width">
      <header class="categories-header">
        <div class="breadcrumb">
          <a href="/">Home</a> &rsaquo;
          Categories
        </div>
        <h1>All Categories</h1>
        <p class="categories-total">{sum(categories_with_counts.values())} articles across {len(categories_with_counts)} categories</p>
      </header>

      <div class="categories-list">
{category_html}
      </div>
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_dentists_page_html():
    """Build dentists page from data/reviewer_mappings.json grouped by state."""
    # Load reviewer mappings to build dentist profiles
    reviewer_mappings = {}
    reviewer_mappings_file = DATA_DIR / "reviewer_mappings.json"

    if reviewer_mappings_file.exists():
        try:
            with open(reviewer_mappings_file, 'r', encoding='utf-8') as f:
                reviewer_mappings = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load reviewer_mappings.json: {e}")

    # Build unique dentist map
    dentist_map = {}
    for article_slug, reviewer_info in reviewer_mappings.items():
        reviewer_name = reviewer_info.get('reviewer_name', '')
        if reviewer_name:
            key = reviewer_name.lower()
            if key not in dentist_map:
                dentist_map[key] = {
                    'name': reviewer_name,
                    'credentials': reviewer_info.get('reviewer_credentials', ''),
                    'practice': reviewer_info.get('reviewer_practice', ''),
                    'location': reviewer_info.get('reviewer_location', ''),
                    'url': reviewer_info.get('reviewer_url', ''),
                    'articles': []
                }
            dentist_map[key]['articles'].append(article_slug)

    # Group by state/location
    dentists_by_state = defaultdict(list)
    for dentist_info in dentist_map.values():
        location = dentist_info.get('location', 'Unknown')
        state = location.split(',')[-1].strip() if ',' in location else location
        dentists_by_state[state].append(dentist_info)

    dentists_html = ""
    for state in sorted(dentists_by_state.keys()):
        dentists_html += f'\n      <h3>{html_mod.escape(state)}</h3>\n'
        for dentist in dentists_by_state[state]:
            name = dentist.get('name', 'Unknown')
            credentials = dentist.get('credentials', '')
            practice = dentist.get('practice', '')
            location = dentist.get('location', '')
            url = dentist.get('url', '')

            url_display = ""
            if url:
                display_url = url.replace("https://", "").replace("http://", "").rstrip("/")
                url_display = f'<a href="{html_mod.escape(url)}" target="_blank">{html_mod.escape(display_url)}</a>'

            dentists_html += f"""
      <div class="dentist-card">
        <div class="dentist-name">{html_mod.escape(name)}</div>
        <div class="dentist-credentials">{html_mod.escape(credentials)}</div>
        <div class="dentist-practice">{html_mod.escape(practice)}</div>
        <div class="dentist-location">{html_mod.escape(location)}</div>
        <div class="dentist-link">{url_display}</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Expert Reviewers — DentalPedia</title>
  <meta name="description" content="Meet the licensed dental professionals who review DentalPedia articles">
  <meta property="og:title" content="Expert Reviewers — DentalPedia">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{DOMAIN}/dentists.html">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="dentists-page">
    <div class="container content-width">
      <header class="dentists-header">
        <div class="breadcrumb">
          <a href="/">Home</a> &rsaquo;
          Expert Reviewers
        </div>
        <h1>Expert Reviewers</h1>
        <p class="dentists-intro">Licensed dental professionals who review and verify our content</p>
      </header>

      <div class="dentists-grid">
{dentists_html}
      </div>
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_dentist_profile_html(dentist_name, dentist_info, articles):
    """Build an individual dentist profile page."""
    slug = slugify(dentist_name.split(",")[0])
    credentials = dentist_info.get('credentials', '')
    practice = dentist_info.get('practice', '')
    location = dentist_info.get('location', '')
    url = dentist_info.get('url', '')

    # Find articles reviewed by this dentist
    reviewed_articles = []
    for article in articles:
        if article.get('reviewer_name') == dentist_name:
            reviewed_articles.append(article)

    # Build articles list
    articles_html = ""
    if reviewed_articles:
        for article in reviewed_articles:
            articles_html += f"""
      <div class="article-item">
        <a href="/article/{article['slug']}.html" class="article-link">{html_mod.escape(article['title'])}</a>
        <span class="article-category">{html_mod.escape(article.get('category', ''))}</span>
      </div>"""
    else:
        articles_html = '<p>No articles reviewed yet.</p>'

    # Build website link
    website_link = ""
    if url:
        display_url = url.replace("https://", "").replace("http://", "").rstrip("/")
        website_link = f'<a href="{html_mod.escape(url)}" target="_blank" class="btn-visit-website">Visit Website →</a>'

    # Schema.org Person markup
    schema_person = f"""
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Person",
    "name": "{dentist_name}",
    "jobTitle": "{credentials}",
    "url": "{url}",
    "worksFor": {{
      "@type": "Organization",
      "name": "{practice}"
    }},
    "areaServed": "{location}"
  }}
  </script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html_mod.escape(dentist_name)} — DentalPedia</title>
  <meta name="description" content="Meet {html_mod.escape(dentist_name)}, a licensed dental professional who reviews articles on DentalPedia.">
  <meta property="og:title" content="{html_mod.escape(dentist_name)} — DentalPedia">
  <meta property="og:type" content="profile">
  <link rel="canonical" href="{DOMAIN}/dentist/{slug}.html">
  <link rel="stylesheet" href="/assets/css/style.css">
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}');
  </script>
  {schema_person}
</head>
<body>
  <nav class="navbar">
    <div class="container">
      <a href="/" class="navbar-brand"><span class="logo-icon">🦷</span> DentalPedia</a>
      <ul class="navbar-nav">
        <li><a href="/categories.html">Categories</a></li>
        <li><a href="/dentists.html">Expert Reviewers</a></li>
        <li><a href="/about.html">About</a></li>
        <li><button class="theme-toggle" aria-label="Toggle dark mode">🌙</button></li>
      </ul>
    </div>
  </nav>

  <main class="dentist-profile-page">
    <div class="container content-width">
      <div class="breadcrumb">
        <a href="/">Home</a> &rsaquo;
        <a href="/dentists.html">Expert Reviewers</a> &rsaquo;
        {html_mod.escape(dentist_name)}
      </div>

      <header class="dentist-header">
        <div class="dentist-icon">🦷</div>
        <h1>{html_mod.escape(dentist_name)}</h1>
        <p class="dentist-credentials">{html_mod.escape(credentials)}</p>
        <p class="dentist-practice">{html_mod.escape(practice)}</p>
        <p class="dentist-location">{html_mod.escape(location)}</p>
        {website_link}
      </header>

      <section class="dentist-articles">
        <h2>Articles Reviewed</h2>
        <div class="reviewed-articles">
{articles_html}
        </div>
      </section>
    </div>
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-text">© 2026 DentalPedia. AI-generated content reviewed by licensed dental professionals.<br><small>Not a substitute for professional dental advice. Always consult your dentist.</small></div>
        <ul class="footer-links">
          <li><a href="/about.html">About</a></li>
          <li><a href="/suggest.html">Suggest an Edit</a></li>
          <li><a href="/dentists.html">For Dentists</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/assets/js/main.js"></script>
</body>
</html>"""


def build_search_index(articles):
    """Generate search-index.json."""
    index = []
    for a in articles:
        index.append({
            "title": a.get("title", ""),
            "url": f'/article/{a["slug"]}.html',
            "category": a.get("category", ""),
            "excerpt": a.get("excerpt", "")
        })
    return index


def build_sitemap(articles, categories_with_counts):
    """Generate sitemap.xml for 200+ articles."""
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        f'  <url><loc>{DOMAIN}/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{DOMAIN}/categories.html</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{DOMAIN}/dentists.html</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>',
        f'  <url><loc>{DOMAIN}/about.html</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>',
    ]
    
    # Category pages
    for category_name in categories_with_counts.keys():
        category_slug = slugify(category_name)
        urls.append(
            f'  <url><loc>{DOMAIN}/category/{category_slug}.html</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>'
        )
    
    # Article pages
    for a in articles:
        date = a.get("date", today)
        urls.append(
            f'  <url><loc>{DOMAIN}/article/{a["slug"]}.html</loc><lastmod>{date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>'
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""


def process_article(md_file, all_articles):
    """Process a single article file. Returns (meta, success)."""
    try:
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        if not meta.get("title"):
            logger.warning(f"  WARNING: No title in {md_file.name}, skipping")
            return None, False

        # Convert markdown body to HTML with internal linking
        body_html = markdown_to_html(body, all_articles)

        # Extract TOC
        toc = extract_toc(body)

        # Find related articles
        related_articles = find_related_articles(meta, all_articles)

        # Build HTML
        article_html = build_article_html(meta, body_html, toc, related_articles)

        # Write output
        slug = meta.get("slug", md_file.stem)
        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.write_text(article_html, encoding="utf-8")

        return meta, True
    except Exception as e:
        logger.error(f"  ERROR processing {md_file.name}: {e}")
        return None, False


def main():
    """Main build function with parallel processing."""
    # Ensure output dir exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not CONTENT_DIR.exists():
        logger.info(f"Content directory not found: {CONTENT_DIR}")
        logger.info("Creating directory structure...")
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        return

    md_files = sorted(CONTENT_DIR.glob("*.md"))

    if not md_files:
        logger.info("No markdown files found in content/articles/")
        return

    logger.info(f"Found {len(md_files)} article(s) to build...\n")

    # First pass: collect all articles metadata for internal linking
    articles_meta = []
    for md_file in md_files:
        try:
            text = md_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if meta.get("title"):
                articles_meta.append(meta)
        except Exception:
            pass

    # Process articles in parallel (with thread pool)
    articles = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_article, md_file, articles_meta): md_file for md_file in md_files}
        
        for future in as_completed(futures):
            meta, success = future.result()
            if success and meta:
                logger.info(f"  → article/{meta['slug']}.html")
                articles.append(meta)

    logger.info(f"Processed {len(articles)} articles")

    if not articles:
        logger.info("No articles processed successfully.")
        return

    # Group articles by category
    categories = defaultdict(list)
    for article in articles:
        category = article.get("category", "Other")
        categories[category].append(article)

    # Sort articles within each category by date (newest first)
    for category in categories:
        categories[category] = sorted(categories[category], key=lambda x: x.get('date', ''), reverse=True)

    # Build category pages with pagination
    logger.info("Building category pages...")
    for category, category_articles in categories.items():
        category_slug = category_articles[0].get("category_slug", slugify(category))
        num_pages = math.ceil(len(category_articles) / ARTICLES_PER_PAGE)
        
        for page_num in range(1, num_pages + 1):
            html = build_category_page_html(category, category_slug, category_articles, page_num)
            
            if page_num == 1:
                output_file = BASE_DIR / f"category/{category_slug}.html"
            else:
                output_file = BASE_DIR / f"category/{category_slug}-page-{page_num}.html"
            
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(html, encoding="utf-8")
            logger.info(f"  → category/{output_file.name}")

    # Build dynamic homepage
    logger.info("\nBuilding dynamic pages...")
    categories_with_counts = {cat: len(arts) for cat, arts in categories.items()}
    homepage_html = build_homepage_html(articles, categories_with_counts)
    (BASE_DIR / "index.html").write_text(homepage_html, encoding="utf-8")
    logger.info("  → index.html")

    # Build categories page
    categories_page = build_categories_page_html(categories_with_counts)
    (BASE_DIR / "categories.html").write_text(categories_page, encoding="utf-8")
    logger.info("  → categories.html")

    # Build dentists page
    dentists_page = build_dentists_page_html()
    (BASE_DIR / "dentists.html").write_text(dentists_page, encoding="utf-8")
    logger.info("  → dentists.html")

    # Build individual dentist profile pages
    logger.info("Building dentist profiles...")
    unique_reviewers = {}
    for article in articles:
        reviewer_name = article.get("reviewer_name", "")
        if reviewer_name:
            key = reviewer_name.lower()
            if key not in unique_reviewers:
                unique_reviewers[key] = {
                    'name': reviewer_name,
                    'credentials': article.get('reviewer_credentials', ''),
                    'practice': article.get('reviewer_practice', ''),
                    'location': article.get('reviewer_location', ''),
                    'url': article.get('reviewer_url', '')
                }

    for reviewer_name, reviewer_info in unique_reviewers.items():
        dentist_html = build_dentist_profile_html(reviewer_info['name'], reviewer_info, articles)
        slug = slugify(reviewer_info['name'].split(",")[0])
        dentist_dir = BASE_DIR / "dentist"
        dentist_dir.mkdir(parents=True, exist_ok=True)
        dentist_file = dentist_dir / f"{slug}.html"
        dentist_file.write_text(dentist_html, encoding="utf-8")
        logger.info(f"  → dentist/{slug}.html")

    # Generate search index
    search_index = build_search_index(articles)
    SEARCH_INDEX_PATH.write_text(json.dumps(search_index, indent=2), encoding="utf-8")
    logger.info(f"  → search-index.json ({len(search_index)} entries)")

    # Generate sitemap
    sitemap = build_sitemap(articles, categories_with_counts)
    SITEMAP_PATH.write_text(sitemap, encoding="utf-8")
    total_urls = len(articles) + len(categories_with_counts) + 4
    logger.info(f"  → sitemap.xml ({total_urls} URLs)")

    logger.info(f"\n✅ Build complete!")
    logger.info(f"   {len(articles)} articles across {len(categories)} categories")
    logger.info(f"   {sum(len(cats) for cats in categories.values())} article pages")
    logger.info(f"   {len(categories)} category pages")
    logger.info(f"   {len(unique_reviewers)} dentist profile pages")
    logger.info(f"   4 dynamic pages (index, categories, dentists, + individual profiles)")


if __name__ == "__main__":
    main()
