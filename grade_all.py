#!/usr/bin/env python3
"""
Comprehensive grading script for patient and clinical dental articles.
Evaluates first 350 files alphabetically with detailed scoring criteria.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class GradeResult:
    filename: str
    title: str
    word_count: int
    score_pct: float
    grade: str
    category: str  # "patient" or "clinical"
    details: Dict

class DentalArticleGrader:
    """Grade dental articles based on SEO, UX, quality, and linking criteria."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        self.articles_path = os.path.join(base_path, "content", "articles")
        self.clinical_path = os.path.join(base_path, "content", "clinical")
        self.results = {"patient": [], "clinical": []}
        self.broken_links = []
        self.differentiation_check = []

    def parse_frontmatter(self, content: str) -> Tuple[Dict, str]:
        """Extract YAML frontmatter and body from markdown."""
        lines = content.split('\n')
        if not lines[0].strip() == '---':
            return {}, content

        frontmatter_lines = []
        body_start = 1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                body_start = i + 1
                break
            frontmatter_lines.append(line)

        frontmatter = {}
        for line in frontmatter_lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                if key == 'references':
                    continue
                frontmatter[key] = value

        body = '\n'.join(lines[body_start:])
        return frontmatter, body

    def extract_references(self, content: str) -> List[str]:
        """Extract references from frontmatter."""
        lines = content.split('\n')
        refs = []
        in_refs = False
        for line in lines:
            if line.strip().startswith('references:'):
                in_refs = True
                continue
            if in_refs:
                if line.strip().startswith('- "'):
                    refs.append(line.strip('- "\''))
                elif line.strip() and not line.startswith(' '):
                    break
        return refs

    def count_words(self, text: str) -> int:
        """Count words in text, excluding frontmatter."""
        # Remove frontmatter
        if text.startswith('---'):
            parts = text.split('---', 2)
            if len(parts) > 2:
                text = parts[2]

        # Remove markdown headers and formatting
        text = re.sub(r'#{1,6}\s+', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Links
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)  # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Code

        words = text.split()
        return len(words)

    def extract_headings(self, text: str) -> List[Tuple[str, int]]:
        """Extract H2 headings and their positions."""
        headings = []
        for match in re.finditer(r'^## (.+)$', text, re.MULTILINE):
            headings.append((match.group(1), match.start()))
        return headings

    def extract_body_text(self, content: str) -> str:
        """Extract only the body text after frontmatter."""
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) > 2:
                return parts[2]
        return content

    def get_section_text(self, body: str, heading_idx: int, headings: List[Tuple[str, int]]) -> str:
        """Get text under a specific heading until next heading."""
        start_pos = headings[heading_idx][1]
        if heading_idx + 1 < len(headings):
            end_pos = headings[heading_idx + 1][1]
            return body[start_pos:end_pos]
        return body[start_pos:]

    def count_you_your(self, text: str) -> int:
        """Count occurrences of 'you' or 'your' (case-insensitive)."""
        pattern = r'\b(you|your)\b'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return len(matches)

    def has_practical_phrases(self, text: str) -> bool:
        """Check for practical advice phrases."""
        phrases = [
            r'ask your dentist', r'what to expect', r'recovery',
            r'cost', r'tip:', r'tips:', r'what happens',
            r'before.*surgery', r'after.*surgery', r'preparation'
        ]
        for phrase in phrases:
            if re.search(phrase, text, re.IGNORECASE):
                return True
        return False

    def check_clinical_terms(self, text: str) -> bool:
        """Check for professional terminology."""
        terms = [
            'biomechanical', 'protocol', 'etiology', 'pathogenesis',
            'histological', 'pharmacokinetic', 'kinase', 'receptor',
            'enzymatic', 'polymerization', 'osseointegration'
        ]
        count = sum(1 for term in terms if term.lower() in text.lower())
        return count >= 2

    def extract_internal_links(self, text: str) -> List[str]:
        """Extract /article/ links from markdown."""
        pattern = r'\(/article/([a-z0-9\-]+)\.html\)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return matches

    def grade_patient_article(self, filename: str, content: str) -> GradeResult:
        """Grade patient article with 25% weight per category."""
        fm, body = self.parse_frontmatter(content)
        refs = self.extract_references(content)

        title = fm.get('title', '')
        excerpt = fm.get('excerpt', '')
        word_count = self.count_words(body)
        headings = self.extract_headings(body)
        you_count = self.count_you_your(body)
        internal_links = self.extract_internal_links(body)

        scores = {}

        # SEO (25%)
        seo_score = 0
        seo_details = {}

        # Primary keyword in title (not generic)
        has_primary_kw = not any(x in title.lower() for x in ['best practices', 'complete guide', 'everything about', 'what is'])
        seo_details['primary_keyword'] = has_primary_kw
        if has_primary_kw: seo_score += 25

        # Excerpt length and keyword
        excerpt_len = len(excerpt)
        excerpt_ok = 100 <= excerpt_len <= 180
        seo_details['excerpt_length'] = excerpt_len
        if excerpt_ok: seo_score += 25

        # H2 headings (5+)
        h2_count = len(headings)
        seo_details['h2_count'] = h2_count
        if h2_count >= 5: seo_score += 25

        # No generic title pattern
        no_old_pattern = 'Best Practices for' not in title
        seo_details['no_old_pattern'] = no_old_pattern
        if no_old_pattern: seo_score += 25

        scores['seo'] = seo_score

        # Patient Experience (25%)
        ux_score = 0
        ux_details = {}

        # Word count grades
        if 1200 <= word_count <= 1800:
            ux_score += 25
            ux_details['word_count_grade'] = 'A'
        elif 1000 <= word_count <= 1200 or 1800 <= word_count <= 2200:
            ux_score += 15
            ux_details['word_count_grade'] = 'B'
        else:
            ux_details['word_count_grade'] = 'C'

        # You/your frequency
        you_ratio = you_count / max(1, word_count / 100)  # per 100 words
        ux_details['you_your_count'] = you_count
        if you_ratio > 5:  # > 5 per 100 words
            ux_score += 25
        elif you_ratio > 2:
            ux_score += 15

        # Practical phrases
        has_practical = self.has_practical_phrases(body)
        ux_details['has_practical_phrases'] = has_practical
        if has_practical: ux_score += 15

        # Dense jargon (check for medical terms without explanations)
        jargon_terms = ['periodontal', 'endodontic', 'prosthodontic', 'orthodontic']
        jargon_count = sum(1 for term in jargon_terms if term in body.lower())
        explained = len(re.findall(r'\([^)]+\)', body))  # parenthetical explanations
        has_unexplained_jargon = jargon_count > explained
        ux_details['has_unexplained_jargon'] = has_unexplained_jargon
        if not has_unexplained_jargon: ux_score += 10

        scores['ux'] = ux_score

        # Content Quality (25%)
        quality_score = 0
        quality_details = {}

        # Key takeaway section
        has_key_takeaway = 'Key Takeaway' in body or 'key takeaway' in body.lower()
        quality_details['has_key_takeaway'] = has_key_takeaway
        if has_key_takeaway: quality_score += 25

        # References in frontmatter
        has_references = len(refs) > 0 and fm.get('reviewed') == 'true'
        quality_details['has_references'] = has_references
        if has_references: quality_score += 25

        # No repeated paragraphs
        paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
        unique_paragraphs = len(set(paragraphs))
        no_duplicates = unique_paragraphs >= len(paragraphs) * 0.95
        quality_details['no_duplicates'] = no_duplicates
        if no_duplicates: quality_score += 25

        # Section word counts (100+ words)
        min_section_words = 100
        section_text = [self.get_section_text(body, i, headings) for i in range(len(headings))]
        sections_adequate = all(self.count_words(s) >= min_section_words for s in section_text)
        quality_details['sections_adequate'] = sections_adequate
        if sections_adequate: quality_score += 25

        scores['quality'] = quality_score

        # Interlinking (25%)
        link_score = 0
        link_details = {}

        # Check if links exist
        valid_links = 0
        for slug in internal_links:
            link_file = os.path.join(self.articles_path, f"{slug}.md")
            if os.path.exists(link_file):
                valid_links += 1
            else:
                self.broken_links.append({
                    'from': filename,
                    'to': slug,
                    'type': 'patient'
                })

        link_details['total_internal_links'] = len(internal_links)
        link_details['valid_links'] = valid_links

        if len(internal_links) >= 2: link_score += 25
        if valid_links == len(internal_links) and len(internal_links) > 0: link_score += 25

        # Links contextual (not just at end) - simplified check
        first_link_pos = body.find('](/article/')
        last_para_start = body.rfind('\n\n')
        is_contextual = first_link_pos < last_para_start * 0.8
        link_details['links_contextual'] = is_contextual
        if is_contextual and len(internal_links) > 0: link_score += 25

        scores['linking'] = link_score

        # Calculate overall score
        overall_score = (scores['seo'] * 0.25 + scores['ux'] * 0.25 +
                        scores['quality'] * 0.25 + scores['linking'] * 0.25) / 100 * 100

        # Map to letter grade
        grade = self.score_to_grade(overall_score)

        details = {
            'seo': {'score': scores['seo'], 'details': seo_details},
            'ux': {'score': scores['ux'], 'details': ux_details},
            'quality': {'score': scores['quality'], 'details': quality_details},
            'linking': {'score': scores['linking'], 'details': link_details}
        }

        return GradeResult(
            filename=filename,
            title=title,
            word_count=word_count,
            score_pct=overall_score,
            grade=grade,
            category='patient',
            details=details
        )

    def grade_clinical_article(self, filename: str, content: str, patient_content: str = None) -> GradeResult:
        """Grade clinical article."""
        fm, body = self.parse_frontmatter(content)
        refs = self.extract_references(content)

        title = fm.get('title', '')
        word_count = self.count_words(body)
        headings = self.extract_headings(body)

        scores = {}

        # Professional Depth (30%)
        depth_score = 0
        depth_details = {}

        # Professional terminology
        has_clinical_terms = self.check_clinical_terms(body)
        depth_details['has_clinical_terms'] = has_clinical_terms
        if has_clinical_terms: depth_score += 30

        # Word count 800+
        depth_details['word_count'] = word_count
        if word_count >= 800: depth_score += 30

        # Has H2 headings
        depth_details['h2_count'] = len(headings)
        if len(headings) >= 3: depth_score += 40

        scores['depth'] = depth_score

        # Academic Credibility (30%)
        cred_score = 0
        cred_details = {}

        # References count
        cred_details['reference_count'] = len(refs)
        if len(refs) >= 3: cred_score += 50
        elif len(refs) >= 1: cred_score += 25

        # References look academic
        academic_refs = 0
        for ref in refs:
            if any(x in ref for x in ['J ', 'et al', '19', '20']) and 'Journal' in ref:
                academic_refs += 1

        cred_details['academic_refs'] = academic_refs
        if academic_refs >= len(refs) * 0.7: cred_score += 50

        scores['credibility'] = cred_score

        # Differentiation (40%)
        diff_score = 100
        diff_details = {}

        if patient_content:
            # Compare first 200 chars
            patient_body = self.extract_body_text(patient_content)
            clinical_body = body

            patient_start = patient_body[:200].lower()
            clinical_start = clinical_body[:200].lower()

            # Similarity check (if too similar, reduce score)
            similarity = self.text_similarity(patient_start, clinical_start)
            diff_details['body_similarity'] = similarity

            # Compare H2 headings
            patient_fm, patient_body_full = self.parse_frontmatter(patient_content)
            patient_headings = self.extract_headings(patient_body_full)
            clinical_headings = self.extract_headings(clinical_body)

            patient_h2_set = set(h[0].lower() for h in patient_headings)
            clinical_h2_set = set(h[0].lower() for h in clinical_headings)

            heading_overlap = len(patient_h2_set & clinical_h2_set) / max(1, len(patient_h2_set | clinical_h2_set))
            diff_details['heading_similarity'] = heading_overlap

            if similarity > 0.8 or heading_overlap > 0.8:
                diff_score = 0  # F - nearly identical
                diff_details['verdict'] = 'IDENTICAL'
            elif similarity > 0.6:
                diff_score = 30
                diff_details['verdict'] = 'SIMILAR'
            else:
                diff_score = 100
                diff_details['verdict'] = 'DIFFERENTIATED'

        scores['differentiation'] = diff_score

        # Calculate overall score
        overall_score = (scores['depth'] * 0.30 + scores['credibility'] * 0.30 +
                        scores['differentiation'] * 0.40) / 100 * 100

        grade = self.score_to_grade(overall_score)

        details = {
            'depth': {'score': scores['depth'], 'details': depth_details},
            'credibility': {'score': scores['credibility'], 'details': cred_details},
            'differentiation': {'score': scores['differentiation'], 'details': diff_details}
        }

        return GradeResult(
            filename=filename,
            title=title,
            word_count=word_count,
            score_pct=overall_score,
            grade=grade,
            category='clinical',
            details=details
        )

    def text_similarity(self, text1: str, text2: str) -> float:
        """Simple word overlap similarity 0-1."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        overlap = len(words1 & words2)
        total = len(words1 | words2)
        return overlap / total if total > 0 else 0.0

    def score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 97:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    def grade_all(self):
        """Grade all articles in both directories."""
        # Get sorted file lists
        patient_files = sorted(os.listdir(self.articles_path))[:350]
        clinical_files = sorted(os.listdir(self.clinical_path))[:350]

        print(f"Grading {len(patient_files)} patient articles...")

        for i, filename in enumerate(patient_files):
            if not filename.endswith('.md'):
                continue

            filepath = os.path.join(self.articles_path, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            result = self.grade_patient_article(filename, content)
            self.results['patient'].append(result)

            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(patient_files)}")

        print(f"Grading {len(clinical_files)} clinical articles...")

        for i, filename in enumerate(clinical_files):
            if not filename.endswith('.md'):
                continue

            filepath = os.path.join(self.clinical_path, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Try to load patient version for comparison
            patient_filepath = os.path.join(self.articles_path, filename)
            patient_content = None
            if os.path.exists(patient_filepath):
                with open(patient_filepath, 'r', encoding='utf-8') as f:
                    patient_content = f.read()

            result = self.grade_clinical_article(filename, content, patient_content)
            self.results['clinical'].append(result)

            # Track differentiation
            if patient_content:
                self.differentiation_check.append({
                    'filename': filename,
                    'verdict': result.details['differentiation']['details'].get('verdict', 'UNKNOWN')
                })

            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(clinical_files)}")

    def generate_report(self) -> str:
        """Generate comprehensive markdown report."""
        report = []
        report.append("# Dentalpedia Article Grading Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Summary statistics
        report.append("## Summary Statistics\n")

        patient_results = self.results['patient']
        clinical_results = self.results['clinical']

        patient_grades = [r.grade for r in patient_results]
        clinical_grades = [r.grade for r in clinical_results]

        def count_grades(grades):
            return {
                'A+': grades.count('A+'),
                'A': grades.count('A'),
                'B': grades.count('B'),
                'C': grades.count('C'),
                'D': grades.count('D'),
                'F': grades.count('F')
            }

        patient_counts = count_grades(patient_grades)
        clinical_counts = count_grades(clinical_grades)

        report.append("### Patient Articles (Content/Articles/)\n")
        report.append(f"- Total Graded: {len(patient_results)}")
        report.append(f"- A+: {patient_counts['A+']} | A: {patient_counts['A']} | B: {patient_counts['B']} | C: {patient_counts['C']} | D: {patient_counts['D']} | F: {patient_counts['F']}\n")

        patient_avg = sum(r.score_pct for r in patient_results) / len(patient_results) if patient_results else 0
        report.append(f"- Overall Average Score: {patient_avg:.1f}%")
        report.append(f"- Average Grade: {self.score_to_grade(patient_avg)}\n")

        report.append("### Clinical Articles (Content/Clinical/)\n")
        report.append(f"- Total Graded: {len(clinical_results)}")
        report.append(f"- A+: {clinical_counts['A+']} | A: {clinical_counts['A']} | B: {clinical_counts['B']} | C: {clinical_counts['C']} | D: {clinical_counts['D']} | F: {clinical_counts['F']}\n")

        clinical_avg = sum(r.score_pct for r in clinical_results) / len(clinical_results) if clinical_results else 0
        report.append(f"- Overall Average Score: {clinical_avg:.1f}%")
        report.append(f"- Average Grade: {self.score_to_grade(clinical_avg)}\n")

        # Top 20 patient articles
        report.append("## Top 20 Patient Articles (Highest Scores)\n")
        sorted_patient = sorted(patient_results, key=lambda x: x.score_pct, reverse=True)[:20]

        for rank, result in enumerate(sorted_patient, 1):
            report.append(f"{rank}. **{result.title}** ({result.grade}, {result.score_pct:.1f}%)")
            report.append(f"   - File: {result.filename} | Words: {result.word_count}")

        report.append("")

        # Bottom 20 patient articles
        report.append("## Bottom 20 Patient Articles (Lowest Scores)\n")
        sorted_patient_bottom = sorted(patient_results, key=lambda x: x.score_pct)[:20]

        for rank, result in enumerate(sorted_patient_bottom, 1):
            report.append(f"{rank}. **{result.title}** ({result.grade}, {result.score_pct:.1f}%)")
            report.append(f"   - File: {result.filename} | Words: {result.word_count}")

        report.append("")

        # Broken links
        report.append("## Broken Interlinks\n")
        if self.broken_links:
            report.append(f"Found {len(self.broken_links)} broken internal links:\n")
            for link in self.broken_links[:50]:  # Show first 50
                report.append(f"- {link['from']} → /article/{link['to']}.html [NOT FOUND]")
            if len(self.broken_links) > 50:
                report.append(f"\n... and {len(self.broken_links) - 50} more broken links\n")
        else:
            report.append("No broken interlinks found!\n")

        # Differentiation check
        report.append("## Clinical vs Patient Article Differentiation\n")

        identical = sum(1 for d in self.differentiation_check if d['verdict'] == 'IDENTICAL')
        similar = sum(1 for d in self.differentiation_check if d['verdict'] == 'SIMILAR')
        differentiated = sum(1 for d in self.differentiation_check if d['verdict'] == 'DIFFERENTIATED')

        report.append(f"- Fully Differentiated: {differentiated} ({100*differentiated/max(1,len(self.differentiation_check)):.1f}%)")
        report.append(f"- Similar Content: {similar} ({100*similar/max(1,len(self.differentiation_check)):.1f}%)")
        report.append(f"- Identical/Needs Work: {identical} ({100*identical/max(1,len(self.differentiation_check)):.1f}%)\n")

        if identical > 0:
            report.append("### Articles with Identical/Similar Content\n")
            for d in self.differentiation_check:
                if d['verdict'] in ['IDENTICAL', 'SIMILAR']:
                    report.append(f"- {d['filename']} ({d['verdict']})")
            report.append("")

        # Recommendations
        report.append("## Key Recommendations for Improvement\n")

        # Patient article recommendations
        low_patient = [r for r in patient_results if r.score_pct < 70]
        if low_patient:
            report.append(f"### Patient Articles Scoring Below 70%: {len(low_patient)} articles\n")

            ux_issues = sum(1 for r in low_patient if r.details['ux']['score'] < 20)
            seo_issues = sum(1 for r in low_patient if r.details['seo']['score'] < 25)
            quality_issues = sum(1 for r in low_patient if r.details['quality']['score'] < 25)
            link_issues = sum(1 for r in low_patient if r.details['linking']['score'] < 25)

            report.append("**Common Issues:**")
            if seo_issues > 0:
                report.append(f"- SEO problems in {seo_issues} articles: Add keywords to titles, improve excerpts (100-180 chars), add 5+ H2 headings")
            if ux_issues > 0:
                report.append(f"- UX problems in {ux_issues} articles: Adjust word count to 1200-1800, add 'you/your', include practical phrases")
            if quality_issues > 0:
                report.append(f"- Quality problems in {quality_issues} articles: Add Key Takeaway sections, add references, ensure 100+ word sections")
            if link_issues > 0:
                report.append(f"- Linking problems in {link_issues} articles: Add 2+ internal links, ensure links are contextual")
            report.append("")

        # Clinical article recommendations
        report.append("### Clinical Article Recommendations\n")
        low_clinical = [r for r in clinical_results if r.score_pct < 70]

        if len(low_clinical) > 0:
            report.append(f"- {len(low_clinical)} clinical articles below 70%: Review for professional depth and academic credibility")
            report.append(f"- Ensure 3+ academic references with proper journal citations")
            report.append(f"- Include technical terminology and detailed explanations\n")

        if identical > 0:
            report.append(f"- **URGENT**: {identical} clinical articles are too similar to patient versions. Rewrite for professional/academic tone and depth\n")

        report.append("### General Recommendations\n")
        report.append("- Implement automated link validation in build process")
        report.append("- Set word count targets during content creation (1200-1800 for patient)")
        report.append("- Create template for clinical articles to ensure differentiation from patient versions")
        report.append("- Establish SEO checklist: title keywords, excerpt length, 5+ H2 headings\n")

        return "\n".join(report)

def main():
    base_path = "/sessions/loving-gifted-franklin/dentalpedia-push"
    grader = DentalArticleGrader(base_path)

    print("Starting comprehensive article grading...")
    grader.grade_all()

    print("Generating report...")
    report = grader.generate_report()

    # Save report
    output_path = os.path.join(base_path, "GRADE-REPORT.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport saved to: {output_path}")

    # Print summary to console
    print("\n" + "="*60)
    print("GRADING SUMMARY")
    print("="*60)

    patient_results = grader.results['patient']
    clinical_results = grader.results['clinical']

    patient_avg = sum(r.score_pct for r in patient_results) / len(patient_results) if patient_results else 0
    clinical_avg = sum(r.score_pct for r in clinical_results) / len(clinical_results) if clinical_results else 0

    patient_grades = [r.grade for r in patient_results]
    clinical_grades = [r.grade for r in clinical_results]

    print(f"\nPatient Articles: {len(patient_results)} graded")
    print(f"  A+: {patient_grades.count('A+')}, A: {patient_grades.count('A')}, B: {patient_grades.count('B')}")
    print(f"  C: {patient_grades.count('C')}, D: {patient_grades.count('D')}, F: {patient_grades.count('F')}")
    print(f"  Average: {patient_avg:.1f}% ({grader.score_to_grade(patient_avg)})")

    print(f"\nClinical Articles: {len(clinical_results)} graded")
    print(f"  A+: {clinical_grades.count('A+')}, A: {clinical_grades.count('A')}, B: {clinical_grades.count('B')}")
    print(f"  C: {clinical_grades.count('C')}, D: {clinical_grades.count('D')}, F: {clinical_grades.count('F')}")
    print(f"  Average: {clinical_avg:.1f}% ({grader.score_to_grade(clinical_avg)})")

    print(f"\nBroken Links Found: {len(grader.broken_links)}")

    identical = sum(1 for d in grader.differentiation_check if d['verdict'] == 'IDENTICAL')
    print(f"Clinical Articles Needing Differentiation: {identical}")

    print("\n" + "="*60)

if __name__ == "__main__":
    main()
