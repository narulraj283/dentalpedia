# 🦷 DentalPedia

**The AI-Powered Dental Encyclopedia** — [dentalpedia.co](https://dentalpedia.co)

AI-generated, expert-reviewed dental articles hosted on GitHub Pages. Updated weekly.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/dentalpedia.git
cd dentalpedia

# Build articles from Markdown → HTML
python build.py

# View locally (any simple HTTP server)
python -m http.server 8000
# Open http://localhost:8000
```

## How It Works

1. **Write articles** as Markdown files in `content/articles/` with YAML frontmatter
2. **Run `python build.py`** to convert them to HTML pages in `article/`
3. **Push to `main`** — GitHub Actions automatically rebuilds and deploys

The site also rebuilds automatically every Monday (weekly schedule).

## Adding a New Article

Create a file in `content/articles/your-article.md`:

```markdown
---
title: Your Article Title
slug: your-article-slug
category: General Dentistry
category_slug: general-dentistry
excerpt: A brief description of the article.
reviewer_name: Dr. Jane Smith, DDS
reviewer_credentials: Board-Certified General Dentist
reviewer_practice: Smith Dental
reviewer_location: City, ST
reviewer_url: https://smithdental.com
sources:
  - title: ADA Source
    url: https://ada.org/...
  - title: NIH Source
    url: https://pubmed.ncbi.nlm.nih.gov/...
date: 2026-03-01
read_time: 6 min
---

## First Section

Your article content here...

## Second Section

More content...
```

Then run `python build.py` and commit.

## Project Structure

```
dentalpedia/
├── index.html              # Homepage
├── categories.html         # Category browser
├── dentists.html           # Expert reviewer directory
├── about.html              # About page
├── suggest.html            # Suggest an edit form
├── 404.html                # Custom 404 page
├── build.py                # Markdown → HTML build script
├── search-index.json       # Auto-generated search index
├── sitemap.xml             # Auto-generated sitemap
├── robots.txt              # Search engine directives
├── CNAME                   # Custom domain config
├── assets/
│   ├── css/style.css       # All styles (light + dark theme)
│   └── js/main.js          # Search, theme toggle, animations
├── article/                # Generated HTML article pages
├── content/
│   └── articles/           # Source Markdown files
└── .github/
    └── workflows/
        └── deploy.yml      # GitHub Pages CI/CD + weekly schedule
```

## Custom Domain Setup

1. Buy `dentalpedia.co` from your registrar
2. Add DNS records:
   - `A` record → `185.199.108.153`
   - `A` record → `185.199.109.153`
   - `A` record → `185.199.110.153`
   - `A` record → `185.199.111.153`
   - `CNAME` record: `www` → `YOUR_USERNAME.github.io`
3. In GitHub repo → Settings → Pages → Custom domain: `dentalpedia.co`
4. Enable "Enforce HTTPS"

## Tech Stack

- Pure HTML/CSS/JS (no frameworks, no build tools beyond Python)
- Python build script for Markdown → HTML conversion
- GitHub Pages for free static hosting
- GitHub Actions for automated builds
- Client-side search (JSON index)
- Dark/light theme with system preference detection
