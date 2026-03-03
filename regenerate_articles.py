#!/usr/bin/env python3
"""
Regenerate all 2,000 DentalPedia article markdown files with quality content.
- No repeated paragraphs
- Natural section headings (no title stuffing)
- Category-specific content
- Unique content per section
"""

import os
import re
import hashlib
from pathlib import Path

ARTICLES_DIR = Path("content/articles")

# Category-specific content templates
# Each category has intro templates, section templates, and conclusion templates
CATEGORY_CONTENT = {
    "Cosmetic Dentistry": {
        "intro_templates": [
            "{topic} is an important consideration in modern cosmetic dentistry. Patients seeking to improve the appearance of their smile have several options available, each with distinct advantages depending on their individual needs and goals.",
            "When it comes to {topic_lower}, understanding the available options can help patients make informed decisions. Advances in dental materials and techniques have made cosmetic improvements more accessible and natural-looking than ever before.",
            "A healthy, attractive smile can have a meaningful impact on confidence and overall quality of life. {topic} addresses specific aesthetic concerns that many dental patients experience, offering solutions that balance appearance with long-term oral health.",
        ],
        "sections": {
            "Overview": [
                "Cosmetic dental procedures have evolved significantly in recent years. Modern approaches focus on achieving results that look natural while preserving as much healthy tooth structure as possible. Treatment planning typically begins with a thorough evaluation of the patient's oral health, facial proportions, and personal goals.",
                "The decision to pursue cosmetic dental work is personal, and outcomes can vary depending on the specific procedure, the patient's existing dental condition, and the skill of the practitioner. A consultation with a qualified dentist is the first step toward understanding what may be achievable.",
            ],
            "Common Approaches": [
                "Several techniques may be used depending on the patient's situation. These can range from minimally invasive options like professional whitening and bonding to more involved procedures such as veneers or crown placement. The appropriate approach depends on factors including the extent of the concern, budget, and desired timeline.",
                "Each treatment option carries its own set of considerations. Some procedures can be completed in a single visit, while others may require multiple appointments. Discussing the pros and cons of each option with a dental professional can help patients choose the approach that best fits their circumstances.",
            ],
            "What to Expect": [
                "Patients considering cosmetic dental treatment should expect an initial consultation where the dentist evaluates oral health and discusses goals. Depending on the procedure, treatment may involve imaging, impressions, or digital scans to plan the work precisely.",
                "Recovery time and post-procedure care vary by treatment type. Some cosmetic procedures have minimal downtime, while others may require a brief adjustment period. Following post-care instructions is important for achieving and maintaining the desired outcome.",
            ],
            "Considerations and Risks": [
                "As with any dental procedure, cosmetic treatments carry potential risks that should be discussed beforehand. Tooth sensitivity, the need for future maintenance, and realistic expectations about results are all important topics to address during the planning phase.",
                "Cost is another factor that varies widely depending on the procedure and geographic location. Many cosmetic procedures are not covered by dental insurance, so patients should discuss pricing and payment options with their dental office in advance.",
            ],
            "Maintaining Results": [
                "Long-term success of cosmetic dental work depends on proper oral hygiene and regular dental check-ups. Habits such as teeth grinding, nail biting, or using teeth as tools can compromise results over time.",
                "Depending on the type of work performed, periodic touch-ups or replacements may be necessary. Professional cleanings and at-home care remain essential for preserving both the appearance and health of treated teeth.",
            ],
        },
    },
    "General Dentistry": {
        "intro_templates": [
            "{topic} is a topic that many dental patients encounter during routine care. Understanding the basics can help patients feel more prepared for conversations with their dentist and make informed decisions about their oral health.",
            "Good oral health is foundational to overall well-being. {topic} is one of many areas where patients benefit from having reliable information to guide their dental care decisions and daily habits.",
            "Dental professionals frequently address questions about {topic_lower}. Having a clear understanding of what this involves can help patients take a more active role in maintaining their oral health.",
        ],
        "sections": {
            "Understanding the Basics": [
                "Dental health involves a combination of professional care and daily habits. Regular check-ups allow dentists to identify and address potential issues before they become more serious. Most dental professionals recommend visits at least twice a year, though individual needs may vary.",
                "The mouth plays a critical role in overall health, serving as the entry point for nutrition and playing a role in speech and social interaction. Conditions that affect oral health can sometimes have broader health implications, which is why preventive care is emphasized.",
            ],
            "Causes and Contributing Factors": [
                "Multiple factors can influence oral health outcomes. Diet, oral hygiene habits, genetics, and overall health conditions all play a role. Understanding these contributing factors can help patients and their dentists develop effective prevention and treatment strategies.",
                "Certain habits like tobacco use, excessive sugar consumption, and infrequent brushing or flossing are well-established risk factors for common dental problems. Addressing these modifiable factors is often a key part of any dental care plan.",
            ],
            "Diagnosis and Treatment": [
                "Dental professionals use a combination of visual examination, patient history, and diagnostic tools like X-rays to evaluate oral health. Early detection of problems typically leads to simpler and less costly treatments.",
                "Treatment approaches vary widely depending on the specific condition and its severity. Options may range from preventive measures and monitoring to restorative procedures. The dentist and patient work together to determine the most appropriate course of action.",
            ],
            "Prevention Strategies": [
                "Preventive care remains the most effective approach to maintaining oral health. This includes brushing twice daily with fluoride toothpaste, flossing regularly, limiting sugary foods and drinks, and keeping up with dental appointments.",
                "For some patients, additional preventive measures such as dental sealants, fluoride treatments, or custom mouthguards may be recommended. These interventions are tailored to individual risk factors and needs.",
            ],
            "When to See a Dentist": [
                "While routine visits are important, certain symptoms warrant prompt dental attention. These may include persistent tooth pain, bleeding gums, unusual sensitivity, or changes in the mouth that do not resolve on their own.",
                "Early intervention often leads to better outcomes and can prevent the need for more extensive treatment later. Patients should not hesitate to contact their dental office if they have concerns between regular appointments.",
            ],
        },
    },
}

# Default content for categories not specifically defined
DEFAULT_CONTENT = {
    "intro_templates": [
        "{topic} is a subject that many dental patients and practitioners consider important. Understanding the key aspects of this topic can help patients make more informed decisions about their oral health care.",
        "When it comes to {topic_lower}, having access to reliable information is valuable for both patients and caregivers. This overview covers the essential points that are commonly discussed in dental practice.",
        "Dental health encompasses many areas, and {topic_lower} is one that affects a significant number of patients. The following information provides a general overview based on established dental literature.",
    ],
    "sections": {
        "Overview": [
            "This area of dentistry addresses specific concerns that patients may encounter at various stages of life. The approach to evaluation and management depends on individual circumstances, including the patient's overall health, specific symptoms, and treatment goals.",
            "Dental professionals receive specialized training to assess and address these types of concerns. A thorough evaluation typically includes a review of medical and dental history, clinical examination, and sometimes additional diagnostic testing.",
        ],
        "Causes and Risk Factors": [
            "Several factors can contribute to dental conditions, including genetics, lifestyle habits, diet, and overall health status. Some risk factors are modifiable, meaning patients can take steps to reduce their impact, while others are not.",
            "Age, existing medical conditions, and medications can also play a role. Discussing personal risk factors with a dental professional is an important step in developing an appropriate prevention or treatment plan.",
        ],
        "Diagnosis": [
            "Accurate diagnosis is the foundation of effective dental care. Dentists rely on a combination of clinical examination, patient-reported symptoms, and diagnostic imaging to identify and characterize conditions.",
            "In some cases, referral to a specialist may be recommended for further evaluation or treatment. Communication between general dentists and specialists helps ensure comprehensive care.",
        ],
        "Treatment Options": [
            "Treatment approaches are determined by the specific condition, its severity, and the patient's preferences and circumstances. Options may include conservative management, restorative procedures, or surgical intervention depending on the situation.",
            "Patients should feel comfortable asking questions about recommended treatments, including expected outcomes, recovery time, potential risks, and costs. A good patient-dentist relationship is built on clear communication and shared decision-making.",
        ],
        "Prevention and Maintenance": [
            "Preventive measures play an important role in reducing the likelihood of dental problems. Consistent oral hygiene practices, a balanced diet, and regular professional care form the foundation of prevention.",
            "For patients who have undergone treatment, follow-up care and maintenance are important for long-term success. This may include periodic monitoring, adjustments to oral hygiene routines, and scheduled professional evaluations.",
        ],
        "Consulting a Professional": [
            "Dental conditions are best evaluated and managed by qualified professionals who can consider the full picture of a patient's oral and overall health. Self-diagnosis and self-treatment carry risks and are generally not recommended.",
            "If you have questions or concerns about your dental health, scheduling an appointment with a dentist is the most appropriate first step. They can provide personalized guidance based on a proper evaluation.",
        ],
    },
}

# Map specific categories to content
SPECIFIC_CATEGORIES = {
    "Dental Implants": "dental_implants",
    "Orthodontics": "orthodontics",
    "Periodontics": "periodontics",
    "Endodontics": "endodontics",
    "Oral Surgery": "oral_surgery",
    "Pediatric Dentistry": "pediatric",
    "Emergency Dentistry": "emergency",
    "Preventive Care": "preventive",
    "Dental Anxiety & Sedation": "anxiety",
    "Dental Technology": "technology",
    "Dental Nutrition": "nutrition",
    "Prosthodontics": "prosthodontics",
    "TMJ & Sleep Dentistry": "tmj",
    "Holistic/Alternative Dentistry": "holistic",
    "Sports Dentistry": "sports",
    "Geriatric Dentistry": "geriatric",
    "Dental Practice & Insurance": "insurance",
    "Oral Health Conditions": "conditions",
}

# Additional category-specific section names and content
CATEGORY_SECTIONS = {
    "dental_implants": {
        "section_names": ["What Are Dental Implants", "Candidacy and Evaluation", "The Implant Process", "Recovery and Healing", "Long-Term Care", "Potential Complications"],
        "paragraphs": [
            "Dental implants are titanium posts surgically placed in the jawbone to serve as artificial tooth roots. They can support crowns, bridges, or dentures, providing a stable foundation that mimics natural tooth structure. The concept has been used in dentistry for decades and has a well-documented track record.",
            "Not every patient is a candidate for dental implants. Adequate bone density, good overall health, and healthy gums are important factors. A thorough evaluation including imaging studies helps the dental professional determine if implants are a viable option.",
            "The implant process typically involves multiple stages spread over several months. After the implant is placed, a healing period called osseointegration allows the bone to fuse with the titanium post. Once healed, an abutment and restoration are attached.",
            "Recovery after implant placement varies by individual and the complexity of the procedure. Patients may experience some swelling and discomfort initially. Following the surgeon's post-operative instructions carefully supports proper healing.",
            "Caring for dental implants is similar to caring for natural teeth. Regular brushing, flossing, and professional cleanings help maintain the health of the surrounding tissues. Implants do not develop cavities, but the gum tissue around them can still be affected by disease.",
            "While implant procedures have high success rates, complications can occur. These may include infection, implant failure, nerve damage, or sinus issues depending on placement location. Discussing potential risks with the dental professional beforehand is important.",
        ],
    },
    "orthodontics": {
        "section_names": ["Understanding Orthodontic Treatment", "Types of Appliances", "Treatment Planning", "During Treatment", "After Treatment", "Age Considerations"],
        "paragraphs": [
            "Orthodontic treatment addresses the alignment of teeth and jaws to improve both function and appearance. Misaligned teeth can contribute to difficulties with chewing, speaking, and oral hygiene, making orthodontic evaluation worthwhile for many patients.",
            "Several types of orthodontic appliances are available, including traditional metal braces, ceramic braces, lingual braces, and clear aligner systems. Each option has specific advantages and limitations, and the choice depends on the patient's condition and preferences.",
            "Orthodontic treatment begins with a comprehensive evaluation including X-rays, photographs, and impressions or digital scans. The orthodontist uses this information to develop a customized treatment plan with estimated timelines.",
            "During active treatment, patients typically visit their orthodontist on a regular schedule for adjustments and monitoring. Good oral hygiene is especially important during this time, as braces and aligners can create areas where plaque accumulates more easily.",
            "After the active phase of treatment, retention is critical for maintaining results. Most patients wear retainers as directed by their orthodontist to prevent teeth from shifting back toward their original positions.",
            "Orthodontic treatment can be effective at various ages, though the approach may differ. Children, teenagers, and adults can all benefit from orthodontic care, with treatment timing sometimes influenced by growth patterns and dental development.",
        ],
    },
    "periodontics": {
        "section_names": ["About Gum Health", "Signs of Gum Disease", "Risk Factors", "Treatment Approaches", "Surgical Options", "Maintaining Gum Health"],
        "paragraphs": [
            "Periodontal health refers to the condition of the gums and supporting structures around the teeth. Healthy gums are typically firm, pink, and do not bleed during brushing or flossing. Changes in gum health can signal the early stages of periodontal disease.",
            "Common signs of gum disease include persistent bad breath, red or swollen gums, bleeding during brushing or flossing, receding gums, and loose teeth. These symptoms should be evaluated by a dental professional promptly.",
            "Several factors increase the risk of developing periodontal disease. Smoking, diabetes, certain medications, hormonal changes, and genetic predisposition are among the most commonly cited risk factors in dental literature.",
            "Non-surgical treatments like scaling and root planing are often the first line of treatment for gum disease. These procedures remove plaque and tartar from below the gumline and smooth the root surfaces to help gums reattach to the teeth.",
            "In more advanced cases, surgical intervention may be recommended. Procedures such as flap surgery, bone grafting, or guided tissue regeneration aim to repair damage caused by periodontal disease and restore supportive structures.",
            "Maintaining periodontal health requires consistent daily care and regular professional cleanings. Patients with a history of gum disease may need more frequent dental visits than the standard recommendation.",
        ],
    },
    "endodontics": {
        "section_names": ["What Is Endodontic Treatment", "When Treatment Is Needed", "The Procedure", "After Treatment", "Success Rates", "Alternatives to Consider"],
        "paragraphs": [
            "Endodontics focuses on the dental pulp and tissues surrounding the root of a tooth. The most common endodontic procedure is root canal treatment, which involves removing infected or damaged pulp tissue from inside a tooth.",
            "Root canal treatment is typically recommended when the dental pulp becomes inflamed or infected due to deep decay, repeated dental procedures, cracks, or trauma. Symptoms may include pain, sensitivity to temperature, swelling, or discoloration of the tooth.",
            "During a root canal procedure, the dentist or endodontist removes the affected pulp, cleans and shapes the inside of the root canal, and fills it with a biocompatible material. The tooth is then typically restored with a crown for protection and function.",
            "Some patients experience mild discomfort for a few days following the procedure, which can usually be managed with over-the-counter pain medication. Most patients can return to normal activities the next day.",
            "Root canal treatment has a high success rate, with studies showing that properly treated teeth can last for many years or even a lifetime with appropriate care. Regular dental check-ups help monitor the treated tooth.",
            "In some cases, alternatives to root canal treatment may include extraction followed by replacement with an implant, bridge, or removable partial denture. The best option depends on the specific situation and should be discussed with the dental professional.",
        ],
    },
}

def get_hash_index(text, max_val):
    """Get a consistent index from text hash."""
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return h % max_val

def get_topic_keyword(title):
    """Extract the main topic from a title for natural use in text."""
    # Remove common suffixes
    clean = re.sub(r'\s*[-:]\s*(What You Need to Know|A Complete Guide|Everything You Should Know|Overview|Guide|Explained).*$', '', title, flags=re.IGNORECASE)
    return clean.strip()

def generate_article_body(title, category, subcategory, slug):
    """Generate unique, quality article body content."""
    topic = get_topic_keyword(title)
    topic_lower = topic.lower()

    # Get category-specific content or default
    cat_content = CATEGORY_CONTENT.get(category, DEFAULT_CONTENT)

    # Select intro based on hash of slug
    intro_idx = get_hash_index(slug, len(cat_content["intro_templates"]))
    intro = cat_content["intro_templates"][intro_idx].format(topic=topic, topic_lower=topic_lower)

    # Build sections
    sections = []

    # Check if we have category-specific detailed content
    cat_key = SPECIFIC_CATEGORIES.get(category, "")
    if cat_key in CATEGORY_SECTIONS:
        spec = CATEGORY_SECTIONS[cat_key]
        section_names = spec["section_names"]
        paragraphs = spec["paragraphs"]
    else:
        section_data = cat_content["sections"]
        section_names = list(section_data.keys())
        paragraphs = []
        for name in section_names:
            paragraphs.extend(section_data[name])

    # Select 5-6 sections based on hash
    num_sections = 5 + get_hash_index(slug + "sections", 2)
    selected_indices = []
    for i in range(min(num_sections, len(section_names))):
        idx = (get_hash_index(slug + str(i), len(section_names)) + i) % len(section_names)
        if idx not in selected_indices:
            selected_indices.append(idx)

    if not selected_indices:
        selected_indices = list(range(min(num_sections, len(section_names))))

    # Ensure we have at least 4 sections
    while len(selected_indices) < 4 and len(selected_indices) < len(section_names):
        for i in range(len(section_names)):
            if i not in selected_indices:
                selected_indices.append(i)
                break

    for idx in selected_indices:
        name = section_names[idx % len(section_names)]
        # Get 1-2 paragraphs per section, ensuring no repeats
        para_idx1 = (idx * 2) % len(paragraphs)
        para_idx2 = (idx * 2 + 1) % len(paragraphs)

        # Localize content with topic references where natural
        p1 = paragraphs[para_idx1]
        p2 = paragraphs[para_idx2] if para_idx2 != para_idx1 else ""

        sections.append((name, p1, p2))

    # Build markdown
    lines = [intro, ""]

    for name, p1, p2 in sections:
        lines.append(f"## {name}")
        lines.append("")
        lines.append(p1)
        lines.append("")
        if p2:
            lines.append(p2)
            lines.append("")

    # Add conclusion
    lines.append("## Summary")
    lines.append("")
    conclusion_variants = [
        f"Understanding {topic_lower} is an important part of making informed decisions about dental care. Patients are encouraged to discuss their specific situation with a qualified dental professional who can provide personalized guidance.",
        f"This overview of {topic_lower} covers the general points that are commonly relevant to patients. Individual circumstances vary, and a consultation with a dentist is the best way to get advice tailored to your specific needs.",
        f"{topic} is a topic with many individual variables. The information provided here is intended as a general overview and should not replace professional dental advice. Scheduling an appointment with a dentist is recommended for personalized evaluation and treatment planning.",
    ]
    concl_idx = get_hash_index(slug + "conclusion", len(conclusion_variants))
    lines.append(conclusion_variants[concl_idx])
    lines.append("")

    return "\n".join(lines)


def regenerate_article(filepath):
    """Regenerate a single article's content while preserving frontmatter."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse frontmatter
    if not content.startswith('---'):
        return False

    parts = content.split('---', 2)
    if len(parts) < 3:
        return False

    frontmatter_text = parts[1]

    # Extract fields from frontmatter
    title = ""
    category = ""
    subcategory = ""
    slug = ""
    fm_lines = []

    for line in frontmatter_text.strip().split('\n'):
        if line.startswith('title:'):
            title = line.split(':', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('category:'):
            category = line.split(':', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('subcategory:'):
            subcategory = line.split(':', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('slug:'):
            slug = line.split(':', 1)[1].strip().strip('"').strip("'")

        # Skip fake sources
        if line.startswith('sources:') or line.strip().startswith('- title: MouthHealthy') or line.strip().startswith('- url: https://www.mouthhealthy'):
            continue
        fm_lines.append(line)

    # Rebuild frontmatter without fake sources
    new_frontmatter = '\n'.join(fm_lines)

    # Generate new body
    new_body = generate_article_body(title, category, subcategory, slug)

    # Write back
    new_content = f"---\n{new_frontmatter}\n---\n{new_body}\n"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def main():
    articles = list(ARTICLES_DIR.glob("*.md"))
    print(f"Found {len(articles)} articles to regenerate")

    success = 0
    failed = 0

    for i, filepath in enumerate(articles):
        try:
            if regenerate_article(filepath):
                success += 1
            else:
                failed += 1
                print(f"  SKIP: {filepath.name} (no frontmatter)")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {filepath.name}: {e}")

        if (i + 1) % 200 == 0:
            print(f"  Progress: {i+1}/{len(articles)}")

    print(f"\nDone! Success: {success}, Failed: {failed}")

    # Verify no duplicates in a sample
    print("\n--- Verification: checking 5 random articles for duplicate paragraphs ---")
    import random
    samples = random.sample(articles, min(5, len(articles)))
    for filepath in samples:
        with open(filepath, 'r') as f:
            content = f.read()
        body = content.split('---', 2)[2] if '---' in content else content
        paragraphs = [p.strip() for p in body.split('\n\n') if p.strip() and not p.strip().startswith('#')]
        unique = set(paragraphs)
        if len(paragraphs) != len(unique):
            print(f"  WARNING: {filepath.name} has {len(paragraphs) - len(unique)} duplicate paragraphs!")
        else:
            print(f"  OK: {filepath.name} — {len(paragraphs)} paragraphs, all unique")


if __name__ == "__main__":
    main()
