# DentalPedia Article Scoring Script - User Guide

## Overview

The `score_articles.py` script provides comprehensive scoring analysis of DentalPedia articles (251-350 in alphabetical order) across four quality dimensions: SEO optimization, patient experience, professional credibility, and technical implementation.

## Quick Start

```bash
python3 score_articles.py
```

The script will:
1. Read articles 251-350 from `content/articles/` (sorted alphabetically)
2. Score each article on all criteria
3. Generate a detailed report at `ARTICLE-SCORES.md`
4. Display a summary to the console

## Output

**Report File:** `/sessions/loving-gifted-franklin/dentalpedia-push/ARTICLE-SCORES.md`

The report contains:
- Summary statistics and score distribution
- Top 10 highest-scoring articles
- Bottom 10 lowest-scoring articles
- Detailed per-article breakdown with subscores

## Scoring Framework

### 1. SEO Score (Max 30 points)

**Title Optimization (1-10)**
- Does the title contain a primary dental keyword?
- Does it include compelling words (best, guide, complete, etc.)?
- Optimal length: 40-70 characters
- Examples of good keywords: dental, teeth, dentist, gum, cavity, braces, implant, crown

**Meta Excerpt Quality (1-10)**
- Optimal length: 150-160 characters
- Contains relevant keywords
- Includes actionable language or CTA (learn, discover, guide, tips, benefits)

**Heading Structure (1-10)**
- H2 headings are natural and not keyword-stuffed
- Headings contain relevant keywords (not over 2 per heading)
- Optimal number: 6-12 H2s for article structure

### 2. Patient Experience Score (Max 30 points)

**Readability (1-10)**
- Word count: 1200-1800 words gets full score
- Average sentence length: 12-17 words is ideal
- Average word length: 4.5-5.5 characters is optimal
- Scores at 1000-2000 words get partial credit

**Practical Value (1-10)**
- Presence of practical phrases:
  - "ask your dentist"
  - "what to expect"
  - "recovery"
  - "cost"
  - "tips"
  - "steps"
  - "how to"
  - "common mistakes"
  - "questions to ask"
- 5+ phrases: 10/10
- 4 phrases: 8/10
- 3 phrases: 6/10
- 2 phrases: 4/10
- 1 phrase: 2/10

**Emotional Tone (1-10)**
- Warm, conversational language
- Use of "you" and "your"
- Avoids dense clinical jargon
- More warm words (20+): 5/10
- Fewer clinical terms (0): 5/10

### 3. Professional Credibility (Max 20 points)

**References Quality (1-10)**
- Academic references in frontmatter YAML
- 6+ references: 8/10
- 4-5 references: 6/10
- 2-3 references: 4/10
- Academic sources (Journal, DOI, PubMed, Cochrane): bonus points

**Accuracy Signals (1-10)**
- Hedging language: "may," "can," "might," "could," "studies suggest," "research indicates," etc.
- Statistical data and citations (15+ hedging instances): 5/10
- Data citations (5+ statistics): 5/10
- Less hedging (1-5): 2-3/10

### 4. Technical Quality (Max 20 points)

**Cross-linking (1-10)**
- Internal markdown links `[text](/path)` to other articles
- 5+ internal links: 10/10
- 3-4 links: 7/10
- 1-2 links: 4/10
- No links: 1/10

**Key Takeaway (1-10)**
- Blockquote with "**Key Takeaway:**"
- Full implementation: 10/10
- Partial blockquote with key/takeaway: 8/10
- Other blockquote present: 4/10
- No blockquote: 1/10

## Key Findings

### Score Distribution
- **Average Total Score:** 66.6/100
- **Score Range:** 42-81 out of 100
- **Median Score:** 68/100
- **Standard Deviation:** 6.5

### Category Performance
- **SEO Score:** 17.9/30 (59.7% efficiency)
  - Weakest area; titles and excerpts need optimization
- **Patient Experience:** 21.9/30 (73.0% efficiency)
  - Strongest area; articles are readable and practical
- **Professional Credibility:** 11.0/20 (55.0% efficiency)
  - Significant gap; needs more academic references
- **Technical Quality:** 15.8/20 (79.0% efficiency)
  - Good implementation; mostly well-structured

## Top Performers (75+)

1. **Hemostasis in Dentistry** (81/100)
   - Perfect balance across all metrics
   - Excellent patient experience (29/30)

2. **Braces Food Restrictions** (80/100)
   - Strong patient experience and practical value
   - Good SEO optimization

3. **Clinical Protocols for Tooth Extraction** (78/100)
   - Highest readability scores
   - Strong practical guidance

4. **Tooth Color Optimization** (77/100)
   - Excellent SEO (27/30)
   - Well-optimized title and structure

## Articles Needing Improvement

### Common Issues in Lower-Scoring Articles (< 55/100)

**Biocompatible Material Selection (42/100)**
- Practical Value: 0/10 - No actionable advice phrases
- Cross-linking: 2/10 - Missing internal links
- Title Optimization: 5/10 - Overly technical, unclear CTA

**Bone Grafting Procedure (58/100)**
- SEO Score: 12/30 - Poor title optimization
- Patient Experience: 18/30 - Complex content, limited practical guidance

**Buccal Corridors (50/100)**
- References Quality: 7/10 - Very few academic sources
- Patient Experience: 15/30 - Low practical value
- Emotional Tone: Overly technical

## Recommendations for Improvement

### Quick Wins (30 minutes per article)
1. **Add Key Takeaway blockquotes** (if missing)
   - Format: `> **Key Takeaway:** [Main point]`
   - Adds 7 points to Technical Quality score

2. **Optimize title and excerpt**
   - Ensure title contains primary keyword
   - Make excerpt 150-160 characters
   - Each adds 2-4 points to SEO score

3. **Add cross-internal links**
   - Link to related DentalPedia articles
   - Target: 3-5 internal links per article
   - Adds 3-6 points to Technical Quality

### Medium-term Improvements (1-2 hours per article)
1. **Enhance practical value**
   - Add "Ask Your Dentist" section
   - Include "What to Expect" guidance
   - Add cost information or recovery timeline
   - Adds 4-6 points to Patient Experience

2. **Add academic references**
   - Research peer-reviewed sources
   - Format: `Author. Title. Journal. Year;Volume(Issue):Pages.`
   - Target: 4-6 academic references
   - Adds 4-6 points to Professional Credibility

3. **Improve warm language**
   - Replace clinical jargon where possible
   - Use "you/your" language
   - Add comfort-oriented phrases
   - Adds 2-4 points to Patient Experience

### Long-term Strategy
1. **Develop template**
   - Use top-performing articles as models
   - Establish consistent structure
   - Standardize Key Takeaway format

2. **Audit for keyword density**
   - Avoid over-optimization in headings
   - Maintain natural heading language
   - Balance SEO with readability

3. **Create reference database**
   - Compile dental research sources
   - Organize by topic
   - Expedite reference integration

## Script Architecture

### Classes and Methods

**ArticleScorer**
- `get_articles_251_to_350()` - Retrieves articles from range
- `parse_article()` - Extracts frontmatter and body
- `score_seo_*()` - Three SEO scoring methods
- `score_*()` - Seven content scoring methods
- `run()` - Main execution loop
- `generate_report()` - Report formatting and output

### Key Features

1. **Alphabetical Ordering** - Articles 251-350 by filename
2. **Regex-based Analysis** - Patterns for headings, links, statistics
3. **Statistical Metrics** - Mean, median, standard deviation
4. **Sorted Rankings** - Top 10 and Bottom 10 articles
5. **Detailed Breakdown** - Per-article subscores
6. **Markdown Output** - Clean, readable report format

## Extending the Script

To modify scoring criteria:

1. **Change weight** of existing metrics:
   - Edit the `score_*()` method return statements
   - Adjust the `+= X` values

2. **Add new scoring criterion**:
   - Create new `score_new_criterion()` method
   - Call it in `score_article()`
   - Add to category total and report

3. **Modify article range**:
   - Change `[250:350]` in `get_articles_251_to_350()`
   - Update documentation

## Troubleshooting

**Issue:** Script runs but produces no output
- Check that `/content/articles/` directory exists
- Verify articles are in `.md` format
- Ensure proper frontmatter (YAML between `---` markers)

**Issue:** Very low scores on all articles
- Verify parsing logic (check article format)
- Ensure regex patterns match your content
- Test with a single known-good article

**Issue:** Report file not created
- Check write permissions in directory
- Verify output path is correct
- Look for file naming conflicts

## File Details

**Script:** `score_articles.py`
- Size: 21.4 KB
- Lines: 550+
- Language: Python 3
- Dependencies: None (uses stdlib only)

**Report:** `ARTICLE-SCORES.md`
- Size: 58 KB (after first run)
- Lines: 2,404 (after first run)
- Format: Markdown
- Regenerates on each script run

## License and Usage

This script is provided as-is for DentalPedia content analysis. Modify as needed for your specific evaluation criteria or publishing workflow.
