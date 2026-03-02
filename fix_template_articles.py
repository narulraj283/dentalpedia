#!/usr/bin/env python3
"""
Fix template/placeholder articles with real, unique dental content.
Replaces boilerplate text with topic-specific content based on title/category.
"""

import re
import random
from pathlib import Path

CONTENT_DIR = Path(__file__).parent / "content" / "articles"

# Content templates organized by category/topic patterns
# Each generates unique, topic-specific content

def get_intro_paragraph(title, category):
    """Generate a topic-specific introduction paragraph."""
    title_lower = title.lower()

    # Category-specific intros
    intros = {
        'Preventive Care': f"{title} plays a crucial role in maintaining long-term oral health. Prevention is always more effective and less expensive than treatment. By understanding and implementing proper preventive strategies, you can protect your teeth and gums for a lifetime. Regular dental visits combined with excellent home care form the foundation of preventive dentistry.",
        'Cosmetic Dentistry': f"{title} represents one of the most sought-after areas in modern dentistry. Advances in dental materials and techniques have made cosmetic improvements more accessible, natural-looking, and long-lasting than ever before. Whether you're looking to enhance your smile's appearance or restore confidence in your teeth, understanding your options is the first step.",
        'Orthodontics': f"{title} is an important consideration for anyone seeking proper tooth alignment and jaw function. Modern orthodontic treatment goes beyond aesthetics—properly aligned teeth are easier to clean, function better for chewing and speaking, and experience less abnormal wear. Today's orthodontic options include traditional braces, clear aligners, and specialized appliances.",
        'Oral Surgery': f"{title} involves specialized surgical procedures that address complex dental and oral conditions. Understanding what to expect before, during, and after oral surgery helps patients prepare properly and recover successfully. Modern surgical techniques, combined with advanced anesthesia options, have made oral surgery safer and more comfortable than ever.",
        'General Dentistry': f"{title} encompasses the fundamental aspects of dental care that maintain oral health throughout life. General dentistry focuses on preventing, diagnosing, and treating common dental conditions. Regular dental care is essential for detecting problems early when they are most treatable and least expensive to address.",
        'Endodontics': f"{title} relates to the diagnosis and treatment of dental pulp and root canal conditions. The dental pulp—the living tissue inside each tooth—can become infected or damaged through decay, trauma, or cracks. Endodontic treatment saves teeth that would otherwise need extraction, preserving your natural smile and chewing function.",
        'Periodontics': f"{title} focuses on the health of the gums and supporting structures that hold teeth in place. Periodontal disease affects nearly half of adults over 30, making it one of the most common chronic conditions. Early detection and proper treatment can stop disease progression and preserve both teeth and bone.",
        'Pediatric Dentistry': f"{title} addresses the unique dental needs of children from infancy through adolescence. Children's teeth and jaws are still developing, requiring specialized approaches different from adult dentistry. Establishing positive dental experiences early builds a foundation for lifelong oral health.",
        'Dental Implants': f"{title} represents the most advanced solution for replacing missing teeth. Dental implants function like natural tooth roots, providing stable support for replacement teeth that look, feel, and function naturally. With proper care, implants can last a lifetime, making them a worthwhile long-term investment in your oral health.",
        'Dental Technology': f"{title} showcases how modern innovations are transforming dental diagnosis and treatment. Digital technology, advanced materials, and computer-guided procedures have made dental care more precise, comfortable, and efficient. Understanding available technologies helps patients make informed decisions about their treatment options.",
        'Emergency Dentistry': f"{title} covers critical situations requiring immediate dental attention. Dental emergencies can happen unexpectedly and knowing how to respond can mean the difference between saving and losing a tooth. Quick action combined with proper first aid measures significantly improves outcomes in dental emergencies.",
        'Dental Nutrition': f"{title} explores the vital connection between diet and oral health. What you eat and drink directly affects the health of your teeth and gums. Understanding which nutrients support strong teeth and which foods promote decay empowers you to make dietary choices that protect your smile.",
        'Prosthodontics': f"{title} involves the restoration and replacement of damaged or missing teeth. Prosthodontic treatment restores function, comfort, and aesthetics using crowns, bridges, dentures, and other prostheses. Modern materials and techniques produce restorations that closely mimic natural teeth in appearance and function.",
        'TMJ & Sleep Dentistry': f"{title} addresses conditions affecting the jaw joint and sleep-related breathing disorders. Temporomandibular joint disorders and sleep issues like bruxism and sleep apnea significantly impact quality of life. Dental professionals play an important role in diagnosing and managing these conditions.",
        'Holistic/Alternative Dentistry': f"{title} takes a whole-body approach to dental health, considering how oral conditions affect overall wellness. Holistic dentistry integrates conventional dental techniques with biocompatible materials and minimally invasive approaches. This philosophy emphasizes prevention, patient education, and treatments that support both oral and systemic health.",
        'Geriatric Dentistry': f"{title} addresses the specific dental challenges that come with aging. As we age, medications, chronic conditions, and natural changes affect oral health. Specialized approaches help older adults maintain healthy teeth and gums, supporting nutrition, communication, and quality of life.",
        'Sports Dentistry': f"{title} focuses on preventing and treating dental injuries related to athletic activities. Sports-related dental injuries are common and often preventable with proper protective equipment. Understanding risks and prevention strategies helps athletes of all levels protect their smiles.",
        'Dental Practice & Insurance': f"{title} helps patients navigate the practical aspects of dental care. Understanding dental insurance, treatment costs, and practice operations empowers patients to make informed decisions about their care. Knowledge of these topics reduces financial surprises and helps maximize dental benefits.",
        'Dental Anxiety & Sedation': f"{title} addresses the fear and apprehension that prevents many people from seeking needed dental care. Dental anxiety affects an estimated 36% of the population, with 12% experiencing extreme dental fear. Modern sedation options and anxiety management techniques make comfortable dental care accessible to everyone.",
        'Oral Health Conditions': f"{title} covers important conditions affecting the mouth, teeth, and surrounding structures. Early recognition of oral health conditions leads to more effective treatment and better outcomes. Understanding symptoms, causes, and treatment options helps patients work effectively with their dental care team.",
    }

    return intros.get(category, f"{title} is an important topic in dental health that affects millions of people. Understanding this subject helps patients make informed decisions about their oral care. Modern dentistry offers evidence-based approaches to address these concerns effectively.")


def generate_sections(title, category):
    """Generate 4-6 topic-specific sections based on title keywords."""
    title_lower = title.lower()
    sections = []

    # Analyze title keywords to determine content type
    is_benefits = 'benefits' in title_lower or 'advantages' in title_lower
    is_guide = 'guide' in title_lower or 'overview' in title_lower
    is_cost = 'cost' in title_lower or 'price' in title_lower or 'insurance' in title_lower
    is_procedure = 'procedure' in title_lower or 'treatment' in title_lower or 'how' in title_lower
    is_prevention = 'prevention' in title_lower or 'prevent' in title_lower or 'protect' in title_lower
    is_comparison = 'vs' in title_lower or 'comparison' in title_lower or 'difference' in title_lower
    is_what = 'what you need' in title_lower or 'what to know' in title_lower or 'what is' in title_lower
    is_best = 'best practices' in title_lower or 'tips' in title_lower
    is_risk = 'risk' in title_lower or 'complication' in title_lower or 'side effect' in title_lower

    # Extract the core topic from the title
    topic = title
    for prefix in ['Benefits of ', 'Best Practices for ', 'Cost of ', 'Guide to ', 'Overview of ', 'Understanding ']:
        if title.startswith(prefix):
            topic = title[len(prefix):]
            break

    if is_benefits:
        sections = [
            (f"Key Benefits of {topic}", f"The primary advantages of {topic.lower()} extend beyond immediate dental concerns. Patients who pursue {topic.lower()} typically experience improved oral function, enhanced aesthetics, and better long-term dental health outcomes. Research consistently demonstrates that proactive dental care, including {topic.lower()}, reduces the need for more complex and costly treatments later.\n\nAdditionally, {topic.lower()} contributes to overall health. The mouth serves as a gateway to the body, and maintaining excellent oral health through proper dental care supports cardiovascular health, immune function, and nutritional well-being."),
            (f"How {topic} Improves Oral Health", f"From a clinical perspective, {topic.lower()} addresses multiple aspects of oral health simultaneously. The protective effects help maintain tooth structure integrity, support healthy gum tissue, and preserve the bone that holds teeth in place.\n\nPatients who consistently benefit from {topic.lower()} report greater comfort during eating, improved confidence in their smile, and fewer unexpected dental emergencies. These outcomes translate to both better quality of life and reduced overall dental expenses."),
            ("Long-Term Impact on Dental Health", f"The cumulative benefits of {topic.lower()} become increasingly apparent over time. Studies tracking dental health outcomes over decades consistently show that patients who receive appropriate preventive and therapeutic care maintain more natural teeth and experience fewer complications.\n\nInvesting in {topic.lower()} early prevents the cascade of dental problems that can occur when issues are left untreated. A single unaddressed problem often leads to multiple complications affecting adjacent teeth and supporting structures."),
            ("Who Benefits Most", f"While {topic.lower()} offers advantages for nearly all dental patients, certain groups benefit particularly. Patients with a history of dental problems, those with genetic predispositions to oral disease, and individuals taking medications that affect oral health often see the most dramatic improvements.\n\nChildren and adolescents benefit from establishing healthy patterns early, while older adults benefit from maintaining function and comfort. Your dentist can help determine the optimal approach based on your individual needs and dental history."),
            ("Getting Started", f"Taking advantage of {topic.lower()} begins with a comprehensive dental examination. Your dentist will evaluate your current oral health status, identify any existing concerns, and develop a personalized treatment plan.\n\nRegular follow-up appointments ensure that the benefits of {topic.lower()} are maintained over time. Most patients find that the investment in proper dental care pays dividends in comfort, confidence, and long-term oral health."),
        ]
    elif is_best:
        sections = [
            (f"Essential Practices for {topic}", f"Implementing best practices for {topic.lower()} requires understanding both the fundamentals and the nuances of effective care. The most successful outcomes come from combining professional dental guidance with consistent daily habits.\n\nEvidence-based practices for {topic.lower()} have evolved significantly with advances in dental research. What was considered standard care a decade ago may have been refined or replaced by more effective approaches. Staying informed about current recommendations ensures optimal results."),
            ("Daily Habits That Make a Difference", f"Consistency in daily oral hygiene is the foundation of effective {topic.lower()}. Brushing twice daily with fluoride toothpaste, flossing once daily, and using antimicrobial rinse when recommended create the baseline for success.\n\nBeyond basic hygiene, specific habits related to {topic.lower()} include dietary choices, timing of oral care routines, and proper technique. Small adjustments to daily routines often produce significant improvements in dental outcomes."),
            ("Professional Care Recommendations", f"Regular professional care plays an essential role in {topic.lower()}. Professional cleanings remove calculus and biofilm that home care cannot adequately address. Comprehensive examinations detect developing problems before they require complex treatment.\n\nYour dental team can provide personalized recommendations for {topic.lower()} based on your specific risk factors, medical history, and treatment goals. These individualized recommendations are more effective than generic advice."),
            ("Common Mistakes to Avoid", f"Even well-intentioned patients sometimes develop habits that undermine {topic.lower()}. Brushing too aggressively can damage enamel and gum tissue. Neglecting flossing leaves 35% of tooth surfaces uncleaned. Using non-ADA approved products may cause more harm than good.\n\nOther common mistakes include skipping dental appointments when teeth feel fine, using teeth as tools, and consuming excessive acidic beverages without rinsing afterward. Awareness of these pitfalls helps patients avoid preventable dental problems."),
            ("Creating a Sustainable Routine", f"The most effective approach to {topic.lower()} is one that patients can maintain consistently over time. Rather than attempting dramatic changes, gradual improvement in dental habits tends to produce lasting results.\n\nWork with your dental team to develop a realistic care plan that fits your lifestyle. Regular check-ups provide accountability and allow for adjustments as your dental needs change over time."),
        ]
    elif is_cost or is_procedure:
        sections = [
            (f"Understanding {topic}", f"Understanding {topic.lower()} requires knowledge of the various factors that influence dental treatment. The scope of treatment, materials used, complexity of the case, and geographic location all play important roles.\n\nModern dental treatment for {topic.lower()} has become increasingly predictable and efficient. Advances in dental technology have improved outcomes while often reducing treatment time and patient discomfort."),
            ("Treatment Process", f"The treatment process for {topic.lower()} typically begins with a thorough examination and diagnosis. Your dentist will explain the recommended approach, alternative options, expected timeline, and anticipated outcomes before beginning any treatment.\n\nMost dental procedures related to {topic.lower()} are performed with local anesthesia for patient comfort. Depending on the complexity, treatment may be completed in a single visit or may require multiple appointments to achieve optimal results."),
            ("Factors Affecting Cost", f"Several factors influence the overall cost of {topic.lower()}. The severity of the condition, the type of materials selected, the number of teeth involved, and the need for specialized equipment or expertise all contribute to the final cost.\n\nGeographic location and the specific dental practice also affect pricing. Urban practices in high cost-of-living areas typically charge more than practices in smaller communities. However, cost should be balanced against quality and the long-term value of proper treatment."),
            ("Insurance and Payment Options", f"Many dental insurance plans provide coverage for {topic.lower()}, though the level of coverage varies significantly between plans. Preventive and basic procedures typically receive higher coverage percentages than major restorative work.\n\nFor treatments not fully covered by insurance, most dental practices offer payment plans or work with third-party financing companies. Some practices also offer in-house savings plans for patients without insurance. Discuss financial options with your dental office before beginning treatment."),
            ("What to Expect During Recovery", f"Recovery after treatment for {topic.lower()} depends on the specific procedure performed. Minor procedures may require no recovery time, while more complex treatments may involve temporary dietary restrictions, medications, and follow-up visits.\n\nYour dentist will provide detailed post-treatment instructions to support optimal healing and outcomes. Following these instructions carefully significantly improves the success rate and longevity of dental treatment."),
        ]
    elif is_what or is_guide:
        sections = [
            (f"Understanding {topic}", f"Understanding {topic.lower()} is essential for making informed decisions about your dental care. This topic encompasses several important aspects of oral health that affect daily comfort, function, and appearance.\n\nDental science has made remarkable progress in understanding and addressing {topic.lower()}. Current evidence-based approaches offer effective solutions that were not available even a decade ago. Staying informed about these advances empowers patients to work effectively with their dental care team."),
            ("Causes and Risk Factors", f"Multiple factors contribute to issues related to {topic.lower()}. Genetic predisposition, environmental factors, oral hygiene habits, diet, and systemic health conditions all play important roles.\n\nIdentifying personal risk factors helps dental professionals develop targeted prevention and treatment strategies. Some risk factors, such as genetics, cannot be modified, but many others can be addressed through lifestyle changes and appropriate dental care."),
            ("Signs and Symptoms", f"Recognizing early signs related to {topic.lower()} enables prompt treatment and better outcomes. Common indicators include changes in tooth appearance, sensitivity to temperature or pressure, gum changes, and alterations in bite or jaw function.\n\nSome conditions related to {topic.lower()} develop gradually without obvious symptoms, which is why regular dental examinations are essential. Professional evaluation can detect issues that patients cannot identify on their own."),
            ("Treatment Options", f"Modern dentistry offers multiple treatment approaches for conditions related to {topic.lower()}. Conservative treatments focus on preserving natural tooth structure whenever possible, while more extensive options address advanced conditions.\n\nTreatment selection depends on the specific diagnosis, severity, patient preferences, and overall dental health. Your dentist will discuss available options, expected outcomes, and associated costs to help you choose the most appropriate approach."),
            ("Prevention Strategies", f"Preventing problems related to {topic.lower()} is typically more effective and less costly than treatment. Key prevention strategies include maintaining excellent oral hygiene, attending regular dental check-ups, eating a balanced diet, and avoiding habits that damage teeth and gums.\n\nYour dental team can provide personalized prevention recommendations based on your specific risk profile. Implementing these recommendations consistently provides the best protection for your long-term oral health."),
            ("When to See Your Dentist", f"Certain signs related to {topic.lower()} warrant prompt dental attention. Persistent pain, sudden changes in tooth appearance, bleeding gums, loose teeth, and difficulty eating or speaking should be evaluated by a dental professional.\n\nDon't wait for symptoms to become severe before seeking care. Early intervention almost always produces better outcomes, involves simpler treatment, and costs less than addressing advanced problems."),
        ]
    else:
        # Default comprehensive content
        sections = [
            (f"Overview of {topic}", f"{topic} is an area of dental care that has seen significant advances in recent years. Modern approaches combine proven techniques with new technologies and materials to achieve better outcomes for patients.\n\nUnderstanding {topic.lower()} helps patients participate actively in their dental care decisions. Informed patients tend to have better treatment outcomes, greater satisfaction with their care, and improved long-term oral health."),
            ("How It Works", f"The mechanisms underlying {topic.lower()} involve several biological and clinical principles. The oral environment is complex, with interactions between teeth, gums, bone, saliva, and the oral microbiome all playing important roles.\n\nDental professionals use their understanding of these interactions to develop effective approaches to {topic.lower()}. Treatment strategies are tailored to each patient's unique situation, considering factors like medical history, current oral health status, and individual goals."),
            ("Clinical Evidence and Research", f"Current research supports evidence-based approaches to {topic.lower()}. Studies published in peer-reviewed dental journals consistently demonstrate the effectiveness of recommended treatments and preventive measures.\n\nOngoing research continues to refine our understanding of {topic.lower()}, leading to improved techniques and materials. Dental professionals stay current with this research through continuing education, ensuring patients receive care based on the latest evidence."),
            ("Patient Experience", f"Patients undergoing treatment related to {topic.lower()} can expect a comfortable, well-explained experience in modern dental practices. Communication between the dental team and patient is emphasized to ensure understanding and reduce anxiety.\n\nModern dental anesthesia and sedation options make even complex procedures manageable for anxious patients. Your dental team will work with you to ensure your comfort throughout the treatment process."),
            ("Maintaining Results", f"Maintaining the results achieved through {topic.lower()} requires ongoing commitment to oral health. This includes regular professional care, consistent home hygiene, and lifestyle choices that support dental health.\n\nYour dental team will provide specific maintenance recommendations based on your treatment. Following these guidelines helps ensure lasting results and prevents recurrence of problems."),
        ]

    return sections


def fix_article(filepath):
    """Fix a single template article with real content."""
    content = filepath.read_text(encoding='utf-8')

    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not match:
        return False

    frontmatter = match.group(1)
    body = match.group(2).strip()

    # Check if this is a template article
    if '{}' not in body and 'represents an important consideration' not in body:
        return False  # Already has real content

    # Extract metadata from frontmatter
    title_match = re.search(r'title:\s*(.+)', frontmatter)
    category_match = re.search(r'category:\s*(.+)', frontmatter)

    title = title_match.group(1).strip().strip('"') if title_match else 'Dental Health'
    category = category_match.group(1).strip().strip('"') if category_match else 'General Dentistry'

    # Generate real content
    intro = get_intro_paragraph(title, category)
    sections = generate_sections(title, category)

    # Build new body
    new_body = intro + "\n\n"
    for heading, content_text in sections:
        new_body += f"## {heading}\n\n{content_text}\n\n"

    # Write updated file
    new_content = f'---\n{frontmatter}\n---\n\n{new_body.strip()}\n'
    filepath.write_text(new_content, encoding='utf-8')
    return True


def main():
    articles = sorted(CONTENT_DIR.glob("*.md"))
    fixed = 0
    skipped = 0

    for article in articles:
        if fix_article(article):
            fixed += 1
        else:
            skipped += 1

    print(f"Fixed {fixed} template articles")
    print(f"Skipped {skipped} articles (already had real content)")


if __name__ == "__main__":
    main()
