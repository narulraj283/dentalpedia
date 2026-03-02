#!/usr/bin/env python3
"""
DentalPedia Build Script
========================
Converts Markdown articles in content/articles/ into HTML pages in article/
Generates search-index.json and sitemap.xml

Usage:
  python build.py

Each markdown file should have YAML-like frontmatter:
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
from datetime import datetime
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content" / "articles"
OUTPUT_DIR = BASE_DIR / "article"
SEARCH_INDEX_PATH = BASE_DIR / "search-index.json"
SITEMAP_PATH = BASE_DIR / "sitemap.xml"
DOMAIN = "https://dentalpedia.co"


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
            # Check if it's a dict-like item (title: ..., url: ...)
            if current_list and isinstance(current_list, list):
                # Simple list item or start of dict
                if ":" in item_text:
                    key, val = item_text.split(":", 1)
                    current_list.append({key.strip(): val.strip()})
                else:
                    current_list.append(item_text)
            continue

        # continuation of a dict item in list
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
                # Start of a list
                current_key = key
                current_list = []
                meta[key] = current_list
            else:
                current_key = key
                current_list = None
                meta[key] = val

    return meta, body


def markdown_to_html(md_text):
    """Simple markdown to HTML converter."""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False
    list_type = None

    for line in lines:
        stripped = line.strip()

        # Empty line
        if not stripped:
            if in_list:
                html_lines.append(f"</{list_type}>")
                in_list = False
            html_lines.append("")
            continue

        # Headers
        if stripped.startswith("######"):
            html_lines.append(f'<h6>{process_inline(stripped[6:].strip())}</h6>')
            continue
        if stripped.startswith("#####"):
            html_lines.append(f'<h5>{process_inline(stripped[5:].strip())}</h5>')
            continue
        if stripped.startswith("####"):
            html_lines.append(f'<h4>{process_inline(stripped[4:].strip())}</h4>')
            continue
        if stripped.startswith("###"):
            content = stripped[3:].strip()
            slug = slugify(content)
            html_lines.append(f'<h3 id="{slug}">{process_inline(content)}</h3>')
            continue
        if stripped.startswith("##"):
            content = stripped[2:].strip()
            slug = slugify(content)
            html_lines.append(f'<h2 id="{slug}">{process_inline(content)}</h2>')
            continue
        if stripped.startswith("#"):
            content = stripped[1:].strip()
            html_lines.append(f'<h1>{process_inline(content)}</h1>')
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list or list_type != "ul":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ul>")
                in_list = True
                list_type = "ul"
            html_lines.append(f"<li>{process_inline(stripped[2:].strip())}</li>")
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
            html_lines.append(f"<li>{process_inline(ol_match.group(1))}</li>")
            continue

        # Close list if we hit a non-list item
        if in_list:
            html_lines.append(f"</{list_type}>")
            in_list = False

        # Paragraph
        html_lines.append(f"<p>{process_inline(stripped)}</p>")

    if in_list:
        html_lines.append(f"</{list_type}>")

    return "\n".join(html_lines)


def process_inline(text):
    """Process inline markdown (bold, italic, links, code)."""
    # Links [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    # Bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Code `text`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    text = text.strip('-')
    return text


def extract_toc(md_text):
    """Extract table of contents from h2 headers."""
    toc = []
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            title = stripped[3:].strip()
            toc.append({"title": title, "slug": slugify(title)})
    return toc


def build_article_html(meta, body_html, toc):
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
        toc_items = "\n".join(f'          <li><a href="#{t["slug"]}">{html_mod.escape(t["title"])}</a></li>' for t in toc)
        toc_html = f"""
      <div class="toc">
        <div class="toc-title">Contents</div>
        <ol class="toc-list">
{toc_items}
        </ol>
      </div>"""

    # Build reviewer card
    reviewer_html = ""
    if reviewer_name:
        reviewer_link = ""
        if reviewer_url:
            display_url = reviewer_url.replace("https://", "").replace("http://", "").rstrip("/")
            reviewer_link = f'<div class="eeat-link"><a href="{html_mod.escape(reviewer_url)}" target="_blank" rel="noopener">&rarr; {html_mod.escape(display_url)}</a></div>'

        reviewer_html = f"""
      <div class="eeat-card">
        <div class="eeat-icon">🦷</div>
        <div class="eeat-content">
          <div class="eeat-label">Expert Reviewer</div>
          <div class="eeat-name">{html_mod.escape(reviewer_name)}</div>
          <div class="eeat-credentials">{html_mod.escape(reviewer_credentials)} &middot; {html_mod.escape(reviewer_practice)} &middot; {html_mod.escape(reviewer_location)}</div>
          {reviewer_link}
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
                source_items.append(f'<li><a href="{html_mod.escape(s_url)}" target="_blank" rel="noopener">{html_mod.escape(s_title)}</a></li>')
        if source_items:
            sources_html = f"""
      <div class="sources-card">
        <div class="sources-title">📚 Sources</div>
        <ul class="sources-list">
          {"".join(source_items)}
        </ul>
      </div>"""

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


def build_search_index(articles):
    """Generate search-index.json."""
    index = []
    for a in articles:
        index.append({
            "title": a["title"],
            "url": f'/article/{a["slug"]}.html',
            "category": a.get("category", ""),
            "excerpt": a.get("excerpt", "")
        })
    return index


def build_sitemap(articles):
    """Generate sitemap.xml."""
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        f'  <url><loc>{DOMAIN}/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{DOMAIN}/categories.html</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{DOMAIN}/dentists.html</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>',
        f'  <url><loc>{DOMAIN}/about.html</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>',
    ]
    for a in articles:
        date = a.get("date", today)
        urls.append(f'  <url><loc>{DOMAIN}/article/{a["slug"]}.html</loc><lastmod>{date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>')

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""


def main():
    # Ensure output dir exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}")
        print("Creating it with a sample article...")
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        return

    articles = []
    md_files = sorted(CONTENT_DIR.glob("*.md"))

    if not md_files:
        print("No markdown files found in content/articles/")
        return

    print(f"Found {len(md_files)} article(s) to build...\n")

    for md_file in md_files:
        print(f"  Building: {md_file.name}")
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        if not meta.get("title"):
            print(f"    WARNING: No title found, skipping {md_file.name}")
            continue

        # Convert markdown body to HTML
        body_html = markdown_to_html(body)

        # Extract TOC
        toc = extract_toc(body)

        # Build HTML
        article_html = build_article_html(meta, body_html, toc)

        # Write output
        slug = meta.get("slug", md_file.stem)
        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.write_text(article_html, encoding="utf-8")
        print(f"    → article/{slug}.html")

        articles.append(meta)

    # Generate search index
    search_index = build_search_index(articles)
    SEARCH_INDEX_PATH.write_text(json.dumps(search_index, indent=2), encoding="utf-8")
    print(f"\n  Search index: {len(search_index)} entries → search-index.json")

    # Generate sitemap
    sitemap = build_sitemap(articles)
    SITEMAP_PATH.write_text(sitemap, encoding="utf-8")
    print(f"  Sitemap: {len(articles) + 4} URLs → sitemap.xml")

    print(f"\n✅ Build complete! {len(articles)} articles generated.")


if __name__ == "__main__":
    main()
