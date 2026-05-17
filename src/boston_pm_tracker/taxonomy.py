"""Domain and company-stage taxonomy. Single source of truth for extract.py and score.py."""

DOMAIN_WEIGHTS: dict[str, int] = {
    "ai_agentic": 5,
    "developer_platform": 4,
    "consumer_at_scale": 4,
    "iot_edge": 3,
    "connectivity_telecom": 3,
    "silicon": 3,
    "space": 3,
    "quantum": 3,
    "health_bio": 2,
}

DOMAIN_DEFINITIONS: dict[str, str] = {
    "ai_agentic": "AI/agentic/LLM platforms, foundation models, agent infra",
    "developer_platform": "Developer platforms, partner ecosystems, public APIs, SDKs",
    "consumer_at_scale": "Consumer products with 1M+ active users",
    "iot_edge": "IoT, edge computing, smart home, embedded systems",
    "connectivity_telecom": "Telecom, networking, 5G, ISPs, connectivity infra, CDN/edge networks",
    "silicon": "Chips, semiconductors, photonics, hardware acceleration",
    "space": "Space tech, satellites, launch, earth observation, in-orbit services",
    "quantum": "Quantum computing hardware, software, cloud services",
    "health_bio": "Clinical AI, diagnostics, life-sciences tooling, bio platforms",
}

STAGE_WEIGHTS: dict[str, int] = {
    "series_b_d_ai_native": 4,
    "public_new_ai_line": 3,
    "late_stage_pre_ipo": 3,
    "mega_corp_10k": 2,
    "seed_series_a": 1,
}

STAGE_DEFINITIONS: dict[str, str] = {
    "series_b_d_ai_native": "Series B-D, AI-native or platform-native company",
    "public_new_ai_line": "Public company launching a new AI/platform product line",
    "late_stage_pre_ipo": "Late-stage private with strong product culture, pre-IPO",
    "mega_corp_10k": "Public/private mega-corp with 10K+ employees, slower but stable",
    "seed_series_a": "Seed or Series A, usually founder-led PM",
}

COMP_FLOOR_USD = 140_000

YOE_MAIN_QUEUE_MAX = 7

# Roles open longer than this are excluded from the digest as likely
# resume-fishing posts (always-on reqs, evergreen JDs).
STALE_DAYS = 30
