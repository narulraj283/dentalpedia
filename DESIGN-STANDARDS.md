# DentalPedia Design & SEO Standards

## Page Width Standards
- **Container (outer):** max-width: 1200px — used for navigation, footer, category grids, directory pages
- **Content-width (reading):** max-width: 720px — used for articles, guides, clinical protocols (optimal reading width)
- **All pages:** padding: 0 1rem on mobile, centered with margin: 0 auto

## Mobile Breakpoints
- **Desktop:** > 768px — full nav, side-by-side layouts
- **Mobile:** ≤ 768px — hamburger menu, stacked layouts, full-width content
- **Touch targets:** minimum 44px × 44px for all interactive elements
- **Font-size:** base 16px, never below 14px on mobile

## SEO Standards

### Title Tags
- Format: `{Article Title} — DentalPedia`
- Max 60 characters (Google truncates at ~60)
- Primary keyword near the front
- No quotes wrapping the title
- Clinical pages: `Clinical: {Title} — DentalPedia`

### Meta Descriptions
- 150-160 characters
- Include primary keyword naturally
- End with a call-to-action or value proposition
- Unique per page — no duplicates

### H1 Tags
- Exactly ONE H1 per page
- Matches the title tag content (minus " — DentalPedia")
- Primary keyword included naturally

### Schema Markup
- Patient articles: `@type: Article`
- Clinical articles: `@type: MedicalScholarlyArticle` with `about.MedicalSpecialty`
- Breadcrumbs: `BreadcrumbList` on all pages
- Directory: `Dentist` schema on practice pages
- No fake `reviewedBy` — only claim what's real

### Cross-Linking
- Patient ↔ Clinical: `rel="alternate"` in `<head>`
- Patient pages: "Dental professional? View Clinical Protocol →" banner
- Clinical pages: "Looking for the patient guide? View Patient Version →" banner
- Internal links: auto-link same-category article titles in body text
- Guide cards: related cornerstone guide linked at article bottom

### URL Structure
- Patient articles: `/article/{slug}.html`
- Clinical articles: `/clinical/{slug}.html`
- Categories: `/category/{category-slug}.html`
- Subcategories: `/subcategory/{category-slug}/{subcategory-slug}/`
- Guides: `/guides/{slug}.html`
- Directory: `/find-a-dentist/{state}/{city}.html`

### Sitemaps
- Split sitemaps: articles, clinical, categories, locations, guides, dentists
- Sitemap index at `/sitemap-index.xml`
- All pages must be in a sitemap

## Content Standards

### Patient Articles (grade 8-10)
- Reading level: Flesch-Kincaid grade 8-10
- Tone: warm, conversational, like a friendly dentist
- Structure: 6-8 sections with ## headings
- Length: 1,200-1,800 words
- Headings: short, natural (not keyword-stuffed)
- No clinical jargon without explanation
- Practical advice: what to expect, what to ask, recovery tips
- No duplicate paragraphs

### Clinical Articles (professional)
- Full clinical detail, protocols, measurements
- Academic references with links
- Specialty-tagged with reviewer qualification
- Evidence-based with citation numbers

## Typography
- Font: Inter (system fallback: -apple-system, BlinkMacSystemFont, sans-serif)
- Body: 16px / 1.6 line-height
- H1: 2rem, H2: 1.5rem, H3: 1.25rem
- Text color: #1a1a2e (light), #e2e8f0 (dark)

## Color System
- Accent: #2563eb (blue)
- Clinical badge: #6366f1 (indigo)
- Patient crosslink: #16a34a (green)
- Dark mode: #0f172a background, #e2e8f0 text
- Key takeaway: #eff6ff background, #2563eb left border
