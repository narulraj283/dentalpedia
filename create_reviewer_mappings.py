import json
from collections import defaultdict
import re

# Load all data
with open('data/topics_new.json', 'r') as f:
    topics_new = json.load(f)

with open('data/clients.json', 'r') as f:
    clients_all = json.load(f)

with open('data/clients_enriched.json', 'r') as f:
    clients_enriched = json.load(f)

with open('data/reviewer_mappings.json', 'r') as f:
    existing_mappings = json.load(f)

# Create enriched client lookup by name
enriched_by_name = {}
for client in clients_enriched:
    enriched_by_name[client['name']] = client

# Create client lookup from all clients by name
clients_by_name = {}
for client in clients_all:
    clients_by_name[client['name']] = client

# Count existing assignments per practice
existing_counts = defaultdict(int)
existing_by_practice = defaultdict(list)
for slug, mapping in existing_mappings.items():
    practice = mapping['reviewer_practice']
    existing_counts[practice] += 1
    existing_by_practice[practice].append(slug)

# Service mapping for topic categories
CATEGORY_TO_SERVICE = {
    'General Dentistry': 'general',
    'Preventive Dentistry': 'preventive',
    'Cosmetic Dentistry': 'cosmetic',
    'Restorative Dentistry': 'restorative',
    'Implant Dentistry': 'implant',
    'Orthodontics': 'ortho',
    'Periodontics': 'perio',
    'Endodontics': 'endo',
    'Oral Surgery': 'surgery',
    'Pediatric Dentistry': 'pediatric'
}

# Keyword matching for fallback
SPECIALTY_KEYWORDS = {
    'implant': ['implant', 'dental implants'],
    'ortho': ['ortho', 'braces', 'invisalign', 'orthodontic'],
    'perio': ['perio', 'gum', 'periodontal'],
    'endo': ['endo', 'root canal', 'endodontic'],
    'cosmetic': ['cosmetic', 'whitening', 'veneers', 'smile design'],
    'surgery': ['surgery', 'oral surgery', 'maxillofacial'],
    'pediatric': ['pediatric', 'children', 'kids'],
    'family': ['family', 'general'],
}

def get_topic_service_preference(topic):
    """Extract primary service preference from topic"""
    if topic.get('mapped_services'):
        service = topic['mapped_services'][0]
        # Normalize service names
        service_lower = service.lower()
        if 'implant' in service_lower:
            return 'implant'
        elif 'ortho' in service_lower:
            return 'ortho'
        elif 'perio' in service_lower or 'gum' in service_lower:
            return 'perio'
        elif 'endo' in service_lower or 'root' in service_lower:
            return 'endo'
        elif 'cosmetic' in service_lower or 'whitening' in service_lower:
            return 'cosmetic'
        elif 'surgery' in service_lower:
            return 'surgery'
        elif 'pediatric' in service_lower or 'children' in service_lower:
            return 'pediatric'

    # Check category
    category = topic.get('category', '')
    for key, keywords in SPECIALTY_KEYWORDS.items():
        if any(kw in category.lower() for kw in keywords):
            return key

    return None

def score_client_for_topic(client, enriched_client, topic_service, topic_title, topic_category):
    """Score how well a client matches a topic"""
    score = 0

    if enriched_client:
        # Check service match
        client_services = [s.lower() for s in enriched_client.get('services', [])]
        client_specialties = [s.lower() for s in enriched_client.get('specialties', [])]

        if topic_service:
            for service in client_services:
                if topic_service in service:
                    score += 100
                    break

            for specialty in client_specialties:
                if topic_service in specialty:
                    score += 50
                    break

        # Keyword matching in practice name
        practice_name = client.get('name', '').lower()
        for key, keywords in SPECIALTY_KEYWORDS.items():
            if key == topic_service:
                for keyword in keywords:
                    if keyword in practice_name:
                        score += 30

    # Fallback: keyword matching in practice name
    practice_name = client.get('name', '').lower()
    title_lower = topic_title.lower()
    category_lower = topic_category.lower()

    for key, keywords in SPECIALTY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in practice_name and keyword in (title_lower + ' ' + category_lower):
                score += 20

    return score

# Build list of available clients with their current assignments
available_clients = []
for client in clients_all:
    current_count = existing_counts.get(client['name'], 0)
    enriched = enriched_by_name.get(client['name'])
    available_clients.append({
        'client': client,
        'enriched': enriched,
        'current_count': current_count
    })

# Sort clients by current count (ascending) to distribute evenly
available_clients.sort(key=lambda x: x['current_count'])

# Create new mappings
new_mappings = {}
assignment_counts = existing_counts.copy()

# Track which client to try next (round-robin with preference)
current_idx = 0
max_per_client = 20
total_topics = len(topics_new)
min_assignments = total_topics // len(clients_all)
max_assignments = min_assignments + 2

print(f"Starting mapping process...")
print(f"Total topics: {total_topics}")
print(f"Total clients: {len(clients_all)}")
print(f"Max assignments per client: {max_per_client}")
print(f"Expected distribution: ~{min_assignments}-{max_assignments} per client")
print()

unmapped_topics = []
topic_assignments_by_practice = defaultdict(list)

# First pass: try specialty matching
for topic in topics_new:
    topic_slug = topic['slug']
    topic_service = get_topic_service_preference(topic)
    topic_title = topic['title']
    topic_category = topic['category']

    best_client = None
    best_score = -1
    best_idx = -1

    # Find best matching client with available slots
    for idx, client_info in enumerate(available_clients):
        client = client_info['client']
        enriched = client_info['enriched']
        current_count = assignment_counts.get(client['name'], 0)

        # Skip if over limit
        if current_count >= max_per_client:
            continue

        score = score_client_for_topic(client, enriched, topic_service, topic_title, topic_category)

        if score > best_score:
            best_score = score
            best_client = client
            best_idx = idx

    # If no good match, use round-robin
    if best_score < 0:
        attempts = 0
        while attempts < len(available_clients):
            client_info = available_clients[current_idx % len(available_clients)]
            current_count = assignment_counts.get(client_info['client']['name'], 0)

            if current_count < max_per_client:
                best_client = client_info['client']
                best_idx = current_idx % len(available_clients)
                break

            current_idx += 1
            attempts += 1

        if best_client:
            current_idx += 1

    # Assign the topic to the best client
    if best_client:
        enriched = enriched_by_name.get(best_client['name'])

        # Get first doctor
        doctor_name = best_client.get('doctors', [{}])[0].get('name', best_client['name'])
        doctor_credentials = best_client.get('doctors', [{}])[0].get('credentials', 'General Dentistry')

        # Build mapping
        mapping = {
            'reviewer_name': doctor_name,
            'reviewer_credentials': doctor_credentials,
            'reviewer_practice': best_client['name'],
            'reviewer_location': best_client['name'],
            'reviewer_url': best_client.get('website', ''),
        }

        # Add specialties and services if enriched
        if enriched:
            mapping['specialties'] = ', '.join(enriched.get('specialties', []))
            mapping['services'] = ', '.join(enriched.get('services', []))
        else:
            mapping['specialties'] = ', '.join(best_client.get('specialties', ['General Dentistry']))
            mapping['services'] = ', '.join(best_client.get('services', ['General Dentistry']))

        new_mappings[topic_slug] = mapping
        assignment_counts[best_client['name']] = assignment_counts.get(best_client['name'], 0) + 1
        topic_assignments_by_practice[best_client['name']].append(topic_slug)
    else:
        unmapped_topics.append(topic_slug)

# Print statistics
print("MAPPING STATISTICS:")
print(f"Total new topics mapped: {len(new_mappings)}")
print(f"Topics that couldn't be mapped: {len(unmapped_topics)}")
print()

# Count stats
final_assignment_counts = defaultdict(int)
for practice, slugs in topic_assignments_by_practice.items():
    final_assignment_counts[practice] = len(slugs) + existing_counts.get(practice, 0)

# Print per-client stats
print("ASSIGNMENTS PER CLIENT (Old + New = Total):")
print("-" * 80)
sorted_clients = sorted(final_assignment_counts.items(), key=lambda x: -x[1])
for practice, total in sorted_clients[:20]:
    old = existing_counts.get(practice, 0)
    new = total - old
    print(f"{practice[:40]:40} | Old: {old:3d} | New: {new:3d} | Total: {total:3d}")

print()
print("SUMMARY STATISTICS:")
print(f"Unique clients used: {len(final_assignment_counts)}")
print(f"Min assignments per client: {min(final_assignment_counts.values())}")
print(f"Max assignments per client: {max(final_assignment_counts.values())}")
print(f"Average assignments per client: {sum(final_assignment_counts.values()) / len(final_assignment_counts):.1f}")
print()

# Save new mappings
with open('data/reviewer_mappings_new.json', 'w') as f:
    json.dump(new_mappings, f, indent=2)

print(f"Saved {len(new_mappings)} new mappings to data/reviewer_mappings_new.json")

# Create combined mappings (old + new)
all_mappings = existing_mappings.copy()
all_mappings.update(new_mappings)

with open('data/reviewer_mappings_all.json', 'w') as f:
    json.dump(all_mappings, f, indent=2)

print(f"Saved {len(all_mappings)} total mappings to data/reviewer_mappings_all.json")

if unmapped_topics:
    print(f"\nWARNING: {len(unmapped_topics)} topics could not be mapped!")
    print("First 10 unmapped:")
    for slug in unmapped_topics[:10]:
        print(f"  {slug}")

EOF
