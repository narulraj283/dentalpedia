#!/usr/bin/env python3
"""
Comprehensive scoring script for DentalPedia articles 251-350.
Scores articles on SEO, Patient Experience, Professional Credibility, and Technical Quality.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict
import statistics

class ArticleScorer:
    """Score DentalPedia articles based on multiple criteria."""

    def __init__(self, articles_dir: str):
        self.articles_dir = Path(articles_dir)
        self.scores: Dict[str, Dict[str, Any]] = {}

    def get_articles_251_to_350(self) -> List[Path]:
        """Get articles 251-350 in alphabetical order."""
        all_articles = sorted([f for f in self.articles_dir.glob("*.md")])
        return all_articles[250:350]  # 0-indexed, so 250:350 gives us 251-350

    def parse_article(self, filepath: Path) -> Dict[str, Any]:
        """Parse article frontmatter and content."""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split frontmatter from content
        parts = content.split('---')
        if len(parts) < 3:
            return {}

        frontmatter = parts[1]
        body = '---'.join(parts[2:]).strip()

        # Parse frontmatter
        data = {'body': body}
        for line in frontmatter.split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip()
                val = val.strip().strip('"\'')
                data[key] = val

        return data

    def score_seo_title_optimization(self, title: str) -> int:
        """Score title optimization (1-10)."""
        score = 0

        # Check for primary keyword presence
        title_lower = title.lower()
        dental_keywords = ['dental', 'teeth', 'dentist', 'gum', 'tooth', 'enamel', 'cavity', 'braces', 'implant', 'crown', 'filling', 'whitening', 'flossing', 'plaque', 'tartar', 'orthodont', 'root canal', 'extraction', 'bridge', 'veneer']
        has_keyword = any(kw in title_lower for kw in dental_keywords)
        score += 5 if has_keyword else 0

        # Check for compelling words
        compelling_words = ['best', 'guide', 'complete', 'comprehensive', 'ultimate', 'essential', 'effective', 'benefits', 'how to', 'what', 'why', 'avoid']
        has_compelling = any(word in title_lower for word in compelling_words)
        score += 3 if has_compelling else 0

        # Check length (optimal 50-60 chars)
        title_len = len(title)
        if 40 <= title_len <= 70:
            score += 2
        elif 30 <= title_len <= 80:
            score += 1

        return min(score, 10)

    def score_meta_excerpt(self, excerpt: str) -> int:
        """Score meta excerpt quality (1-10)."""
        score = 0

        if not excerpt:
            return 0

        # Check length (150-160 chars is ideal)
        excerpt_len = len(excerpt)
        if 150 <= excerpt_len <= 160:
            score += 4
        elif 140 <= excerpt_len <= 170:
            score += 2
        elif 100 <= excerpt_len <= 200:
            score += 1

        # Check for keyword presence
        dental_keywords = ['dental', 'teeth', 'dentist', 'gum', 'tooth', 'enamel', 'cavity', 'care', 'health', 'treatment', 'oral']
        has_keyword = any(kw in excerpt.lower() for kw in dental_keywords)
        score += 3 if has_keyword else 0

        # Check for CTA or actionable language
        cta_phrases = ['learn', 'discover', 'understand', 'guide', 'tips', 'advice', 'benefits', 'help', 'prevent', 'improve']
        has_cta = any(phrase in excerpt.lower() for phrase in cta_phrases)
        score += 3 if has_cta else 0

        return min(score, 10)

    def score_heading_structure(self, body: str) -> int:
        """Score heading structure (1-10)."""
        score = 0

        # Extract H2 headings
        h2_pattern = r'^## (.+)$'
        h2_matches = re.findall(h2_pattern, body, re.MULTILINE)

        if not h2_matches:
            return 1

        # Check for natural language (not keyword stuffed)
        dental_keywords = ['dental', 'teeth', 'dentist', 'gum', 'tooth', 'enamel']
        keyword_stuffed = 0
        for heading in h2_matches:
            keyword_count = sum(1 for kw in dental_keywords if kw in heading.lower())
            if keyword_count > 2:
                keyword_stuffed += 1

        # Score based on keyword stuffing
        if keyword_stuffed == 0:
            score += 5
        elif keyword_stuffed < len(h2_matches) * 0.3:
            score += 3
        else:
            score += 1

        # Check for keyword relevance (at least some should have dental terms)
        keywords_present = any(any(kw in h.lower() for kw in dental_keywords) for h in h2_matches)
        score += 3 if keywords_present else 1

        # Check for natural structure (8-12 H2s is good)
        h2_count = len(h2_matches)
        if 6 <= h2_count <= 12:
            score += 2
        elif 4 <= h2_count <= 15:
            score += 1

        return min(score, 10)

    def score_readability(self, body: str) -> int:
        """Score readability based on word count and reading level (1-10)."""
        score = 0

        # Count words
        words = body.split()
        word_count = len(words)

        # Optimal word count 1200-1800
        if 1200 <= word_count <= 1800:
            score += 5
        elif 1000 <= word_count <= 2000:
            score += 3
        elif 800 <= word_count <= 2200:
            score += 1

        # Calculate readability metrics
        sentences = re.split(r'[.!?]+', body)
        sentences = [s.strip() for s in sentences if s.strip()]

        if sentences:
            avg_sentence_length = word_count / len(sentences)
            avg_word_length = sum(len(w) for w in words) / len(words) if words else 0

            # Grade level estimate (simplified Flesch-Kincaid)
            # Grade level = (0.39 * words/sentences) + (11.8 * syllables/words) - 15.59
            # Rough estimate: lower score is better for general audience

            # Check for good balance: 12-17 words per sentence
            if 12 <= avg_sentence_length <= 17:
                score += 3
            elif 10 <= avg_sentence_length <= 20:
                score += 2
            elif avg_sentence_length <= 25:
                score += 1

            # Check for good word length: 4.5-5.5 characters average
            if 4.5 <= avg_word_length <= 5.5:
                score += 2
            elif 4 <= avg_word_length <= 6:
                score += 1

        return min(score, 10)

    def score_practical_value(self, body: str) -> int:
        """Score practical value (1-10)."""
        score = 0

        # Look for practical advice phrases
        practical_phrases = [
            r'ask your dentist',
            r'what to expect',
            r'recovery',
            r'cost',
            r'advice',
            r'tips',
            r'steps?',
            r'how to',
            r'questions to ask',
            r'common mistakes',
            r'before and after',
            r'preparation',
            r'aftercare'
        ]

        phrase_count = 0
        for phrase in practical_phrases:
            if re.search(phrase, body, re.IGNORECASE):
                phrase_count += 1

        # Score based on phrase count
        if phrase_count >= 5:
            score += 10
        elif phrase_count >= 4:
            score += 8
        elif phrase_count >= 3:
            score += 6
        elif phrase_count >= 2:
            score += 4
        elif phrase_count >= 1:
            score += 2
        else:
            score += 0

        return min(score, 10)

    def score_emotional_tone(self, body: str) -> int:
        """Score emotional tone (1-10)."""
        score = 0

        body_lower = body.lower()

        # Check for warm language
        warm_words = ['you', 'your', 'we', 'our', 'together', 'help', 'care', 'comfort', 'understand', 'easier', 'simple', 'worry']
        warm_count = 0
        for word in warm_words:
            warm_count += body_lower.count(' ' + word + ' ')
            warm_count += body_lower.count('\n' + word + ' ')

        if warm_count > 20:
            score += 5
        elif warm_count > 10:
            score += 3
        elif warm_count > 5:
            score += 1

        # Check for clinical jargon density (look for overly complex terms)
        clinical_jargon = ['pathophysiology', 'etiopathogenesis', 'manifestation', 'amelioration', 'modulation', 'dysbiosis', 'microbial', 'immunopathological', 'nosocomial', 'iatrogenic']
        jargon_count = sum(body_lower.count(term) for term in clinical_jargon)

        # Lower jargon is better
        if jargon_count == 0:
            score += 5
        elif jargon_count < 3:
            score += 3
        elif jargon_count < 6:
            score += 1

        return min(score, 10)

    def score_references_quality(self, frontmatter_data: Dict[str, Any]) -> int:
        """Score references quality (1-10)."""
        score = 0

        # Check for references key
        references = frontmatter_data.get('references', '')
        if not references:
            return 2

        # Count references
        ref_lines = [line.strip() for line in str(references).split('\n') if line.strip().startswith('-')]
        ref_count = len(ref_lines)

        if ref_count >= 6:
            score += 8
        elif ref_count >= 4:
            score += 6
        elif ref_count >= 2:
            score += 4
        else:
            score += 2

        # Check for academic references
        academic_markers = ['journal', 'doi', 'pubmed', 'cochrane', 'lancet', 'jama']
        academic_refs = 0
        for ref in ref_lines:
            if any(marker in ref.lower() for marker in academic_markers):
                academic_refs += 1

        if academic_refs >= ref_count * 0.7:
            score += 2
        elif academic_refs >= ref_count * 0.5:
            score += 1

        return min(score, 10)

    def score_content_accuracy_signals(self, body: str) -> int:
        """Score content accuracy signals (1-10)."""
        score = 0

        body_lower = body.lower()

        # Check for hedging language
        hedging_words = ['may', 'can', 'might', 'could', 'studies suggest', 'research indicates', 'evidence shows', 'appears to', 'tends to', 'often', 'generally', 'typically', 'usually']
        hedging_count = 0
        for word in hedging_words:
            hedging_count += body_lower.count(' ' + word + ' ')

        if hedging_count > 15:
            score += 5
        elif hedging_count > 10:
            score += 4
        elif hedging_count > 5:
            score += 3
        elif hedging_count > 0:
            score += 2

        # Check for statistics/data citations
        stats_pattern = r'\d+[-\s]?\d*\s*(%|percent|year|month|day|time)'
        stats_matches = re.findall(stats_pattern, body)

        if len(stats_matches) >= 5:
            score += 5
        elif len(stats_matches) >= 3:
            score += 4
        elif len(stats_matches) >= 1:
            score += 3

        return min(score, 10)

    def score_cross_linking(self, body: str) -> int:
        """Score cross-linking presence (1-10)."""
        score = 0

        # Look for internal links markdown format [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        links = re.findall(link_pattern, body)

        if not links:
            return 2

        # Count valid internal links (not external URLs)
        internal_links = 0
        for link_text, url in links:
            if not url.startswith('http') and url.startswith('/'):
                internal_links += 1

        if internal_links >= 5:
            score += 10
        elif internal_links >= 3:
            score += 7
        elif internal_links >= 1:
            score += 4
        else:
            score += 1

        return min(score, 10)

    def score_key_takeaway(self, body: str) -> int:
        """Score for Key Takeaway blockquote (1-10)."""
        score = 0

        # Look for blockquote with Key Takeaway
        if '> **Key Takeaway:' in body or '**Key Takeaway:**' in body:
            score = 10
        elif '> ' in body and 'key' in body.lower() and 'takeaway' in body.lower():
            score = 8
        elif '> ' in body:
            score = 4
        else:
            score = 1

        return score

    def score_article(self, filepath: Path, filename: str) -> Dict[str, Any]:
        """Score a single article."""
        article_data = self.parse_article(filepath)

        if not article_data:
            return {'filename': filename, 'error': 'Could not parse article'}

        title = article_data.get('title', '')
        excerpt = article_data.get('excerpt', '')
        body = article_data.get('body', '')

        # Calculate SEO Score (max 30)
        seo_title = self.score_seo_title_optimization(title)
        seo_excerpt = self.score_meta_excerpt(excerpt)
        seo_heading = self.score_heading_structure(body)
        seo_score = seo_title + seo_excerpt + seo_heading

        # Calculate Patient Experience Score (max 30)
        ux_readability = self.score_readability(body)
        ux_practical = self.score_practical_value(body)
        ux_tone = self.score_emotional_tone(body)
        ux_score = ux_readability + ux_practical + ux_tone

        # Calculate Professional Credibility (max 20)
        prof_references = self.score_references_quality(article_data)
        prof_accuracy = self.score_content_accuracy_signals(body)
        prof_score = prof_references + prof_accuracy

        # Calculate Technical Quality (max 20)
        tech_links = self.score_cross_linking(body)
        tech_takeaway = self.score_key_takeaway(body)
        tech_score = tech_links + tech_takeaway

        total_score = seo_score + ux_score + prof_score + tech_score

        return {
            'filename': filename,
            'title': title,
            'seo': {
                'title_optimization': seo_title,
                'meta_excerpt': seo_excerpt,
                'heading_structure': seo_heading,
                'total': seo_score
            },
            'patient_experience': {
                'readability': ux_readability,
                'practical_value': ux_practical,
                'emotional_tone': ux_tone,
                'total': ux_score
            },
            'professional_credibility': {
                'references_quality': prof_references,
                'accuracy_signals': prof_accuracy,
                'total': prof_score
            },
            'technical_quality': {
                'cross_linking': tech_links,
                'key_takeaway': tech_takeaway,
                'total': tech_score
            },
            'total_score': total_score
        }

    def run(self) -> Dict[str, Any]:
        """Run scoring on all articles 251-350."""
        articles = self.get_articles_251_to_350()

        print(f"Scoring articles 251-350 ({len(articles)} articles)...")

        for i, filepath in enumerate(articles, 1):
            filename = filepath.name
            score_result = self.score_article(filepath, filename)
            self.scores[filename] = score_result

            if i % 20 == 0:
                print(f"  Processed {i}/{len(articles)}...")

        return self.scores

    def generate_report(self) -> str:
        """Generate formatted report."""
        if not self.scores:
            return "No articles scored."

        # Calculate statistics
        total_scores = [s['total_score'] for s in self.scores.values()]
        avg_total = statistics.mean(total_scores)

        seo_scores = [s['seo']['total'] for s in self.scores.values()]
        avg_seo = statistics.mean(seo_scores)

        ux_scores = [s['patient_experience']['total'] for s in self.scores.values()]
        avg_ux = statistics.mean(ux_scores)

        prof_scores = [s['professional_credibility']['total'] for s in self.scores.values()]
        avg_prof = statistics.mean(prof_scores)

        tech_scores = [s['technical_quality']['total'] for s in self.scores.values()]
        avg_tech = statistics.mean(tech_scores)

        # Sort for top and bottom
        sorted_articles = sorted(self.scores.items(), key=lambda x: x[1]['total_score'], reverse=True)
        top_10 = sorted_articles[:10]
        bottom_10 = sorted_articles[-10:]

        # Build report
        report = []
        report.append("# DentalPedia Article Scoring Report (Articles 251-350)\n")
        report.append(f"Generated: {len(self.scores)} articles scored\n")

        # Summary Statistics
        report.append("## Summary Statistics\n")
        report.append(f"- **Average Total Score**: {avg_total:.1f}/100")
        report.append(f"- **Average SEO Score**: {avg_seo:.1f}/30")
        report.append(f"- **Average Patient Experience Score**: {avg_ux:.1f}/30")
        report.append(f"- **Average Professional Credibility Score**: {avg_prof:.1f}/20")
        report.append(f"- **Average Technical Quality Score**: {avg_tech:.1f}/20\n")

        # Distribution
        report.append("### Score Distribution\n")
        report.append(f"- **Highest Score**: {max(total_scores):.0f}/100")
        report.append(f"- **Lowest Score**: {min(total_scores):.0f}/100")
        report.append(f"- **Median Score**: {statistics.median(total_scores):.0f}/100")
        report.append(f"- **Standard Deviation**: {statistics.stdev(total_scores):.1f}\n")

        # Top 10
        report.append("## Top 10 Highest Scoring Articles\n")
        for rank, (filename, score) in enumerate(top_10, 1):
            report.append(f"{rank}. **{score['title']}** ({filename})")
            report.append(f"   - Total Score: {score['total_score']:.0f}/100")
            report.append(f"   - SEO: {score['seo']['total']}/30 | Patient Experience: {score['patient_experience']['total']}/30 | Credibility: {score['professional_credibility']['total']}/20 | Technical: {score['technical_quality']['total']}/20\n")

        # Bottom 10
        report.append("## Bottom 10 Lowest Scoring Articles\n")
        for rank, (filename, score) in enumerate(bottom_10, 1):
            report.append(f"{rank}. **{score['title']}** ({filename})")
            report.append(f"   - Total Score: {score['total_score']:.0f}/100")
            report.append(f"   - SEO: {score['seo']['total']}/30 | Patient Experience: {score['patient_experience']['total']}/30 | Credibility: {score['professional_credibility']['total']}/20 | Technical: {score['technical_quality']['total']}/20\n")

        # Detailed Scoring
        report.append("## Detailed Article Scores\n")
        for filename in sorted(self.scores.keys()):
            score = self.scores[filename]
            if 'error' in score:
                continue

            report.append(f"### {score['title']}")
            report.append(f"**File:** {filename}\n")
            report.append(f"**Total Score: {score['total_score']:.0f}/100**\n")

            report.append("#### SEO Score: {}/30".format(score['seo']['total']))
            report.append(f"- Title Optimization: {score['seo']['title_optimization']}/10")
            report.append(f"- Meta Excerpt Quality: {score['seo']['meta_excerpt']}/10")
            report.append(f"- Heading Structure: {score['seo']['heading_structure']}/10\n")

            report.append("#### Patient Experience Score: {}/30".format(score['patient_experience']['total']))
            report.append(f"- Readability: {score['patient_experience']['readability']}/10")
            report.append(f"- Practical Value: {score['patient_experience']['practical_value']}/10")
            report.append(f"- Emotional Tone: {score['patient_experience']['emotional_tone']}/10\n")

            report.append("#### Professional Credibility: {}/20".format(score['professional_credibility']['total']))
            report.append(f"- References Quality: {score['professional_credibility']['references_quality']}/10")
            report.append(f"- Accuracy Signals: {score['professional_credibility']['accuracy_signals']}/10\n")

            report.append("#### Technical Quality: {}/20".format(score['technical_quality']['total']))
            report.append(f"- Cross-linking: {score['technical_quality']['cross_linking']}/10")
            report.append(f"- Key Takeaway: {score['technical_quality']['key_takeaway']}/10\n")

        return '\n'.join(report)


def main():
    """Main entry point."""
    articles_dir = "/sessions/loving-gifted-franklin/dentalpedia-push/content/articles"

    scorer = ArticleScorer(articles_dir)
    print("Starting article scoring process...\n")

    scores = scorer.run()
    print(f"\nCompleted scoring {len(scores)} articles.\n")

    # Generate and save report
    report = scorer.generate_report()

    output_file = "/sessions/loving-gifted-franklin/dentalpedia-push/ARTICLE-SCORES.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"Report saved to {output_file}")
    print("\n" + "="*80)
    print("REPORT SUMMARY")
    print("="*80 + "\n")

    # Print first 100 lines to console
    lines = report.split('\n')
    for line in lines[:100]:
        print(line)

    if len(lines) > 100:
        print(f"\n... (Report continues for {len(lines) - 100} more lines)")
        print(f"Full report available at {output_file}")


if __name__ == "__main__":
    main()
