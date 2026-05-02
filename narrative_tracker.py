"""
narrative_tracker.py — AZALYST Narrative Coherence Tracker (V2 Stub)

Paul Tudor Jones recommendation: markets move on stories, not just data points.
This module clusters news headlines and measures:
  - Narrative coherence: how many unique sources are telling the same story
  - Story persistence: how a narrative evolves over a rolling 5-day window
  - Credibility momentum: whether the story is gaining or losing consensus

Currently a stub that outputs to dashboard but does NOT affect signals.
MANUAL STEP: pip install sentence-transformers scikit-learn
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

log = logging.getLogger("azalyst.narrative")

# ── Constants ────────────────────────────────────────────────────────────────
NARRATIVE_WINDOW_DAYS = 5
MIN_SOURCES_FOR_NARRATIVE = 3


def cluster_headlines(headlines: List[Dict]) -> Dict:
    """
    Cluster headlines by semantic similarity.

    When sentence-transformers is installed, this will use:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode([h.get('text', '') for h in headlines])
    
    Currently uses simple keyword-overlap clustering as a fallback.
    """
    if not headlines:
        return {
            "clusters": [],
            "narrative_coherence_score": 0.0,
            "n_sources": 0,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Simple keyword-based overlap clustering ────────────────────────────
    keywords_by_source: Dict[str, set] = defaultdict(set)
    for h in headlines:
        source = h.get("source", "unknown")
        text = h.get("title", "").lower()
        if not text:
            text = (h.get("text", "") or "").lower()
        # Extract 2-gram and 1-gram keywords
        words = text.split()
        for i in range(len(words)):
            keywords_by_source[source].add(words[i])
            if i < len(words) - 1:
                keywords_by_source[source].add(f"{words[i]} {words[i+1]}")

    # Compute pairwise overlap between sources
    sources = list(keywords_by_source.keys())
    overlaps: List[float] = []
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            s1 = keywords_by_source[sources[i]]
            s2 = keywords_by_source[sources[j]]
            union = s1 | s2
            intersection = s1 & s2
            if union:
                overlaps.append(len(intersection) / len(union))
            else:
                overlaps.append(0.0)

    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
    n_sources = len(sources)

    # Coherence score: number of sources × average semantic overlap, scaled 0-100
    coherence = min((n_sources / MIN_SOURCES_FOR_NARRATIVE) * avg_overlap * 100, 100.0)

    return {
        "n_sources": n_sources,
        "sources": sources,
        "avg_keyword_overlap": round(avg_overlap, 4),
        "narrative_coherence_score": round(coherence, 1),
        "clusters": [],  # TODO: populate after sentence-transformers integration
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


def track_narrative_evolution(
    current_headlines: List[Dict],
    previous_clusters: Optional[Dict] = None,
) -> Dict:
    """
    Track how a narrative changes over successive cycles.
    Returns coherence, change from previous, and credibility flags.
    """
    current = cluster_headlines(current_headlines)

    momentum = 0.0
    gaining_credibility = False
    losing_credibility = False

    if previous_clusters:
        prev_coherence = previous_clusters.get("narrative_coherence_score", 0)
        curr_coherence = current.get("narrative_coherence_score", 0)
        momentum = curr_coherence - prev_coherence
        gaining_credibility = momentum > 5.0
        losing_credibility = momentum < -5.0

    return {
        **current,
        "momentum": round(momentum, 1),
        "gaining_credibility": gaining_credibility,
        "losing_credibility": losing_credibility,
        "window_days": NARRATIVE_WINDOW_DAYS,
    }


def compute_sector_narrative(sector_headlines: Dict[str, List[Dict]]) -> Dict[str, Dict]:
    """
    Compute narrative coherence per sector across all tracked sectors.
    Returns {sector_id: {coherence_score, n_sources, momentum}}
    """
    results = {}
    for sector_id, headlines in sector_headlines.items():
        if headlines:
            cluster = cluster_headlines(headlines)
            results[sector_id] = {
                "coherence_score": cluster.get("narrative_coherence_score", 0),
                "n_sources": cluster.get("n_sources", 0),
                "avg_overlap": cluster.get("avg_keyword_overlap", 0),
            }
    return results


# ── Quick test harness ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print("\\n" + "=" * 60)
    print("  NARRATIVE TRACKER — TEST RUN")
    print("=" * 60)

    test_headlines = [
        {"source": "Reuters", "title": "Gold hits record high on safe-haven demand"},
        {"source": "Bloomberg", "title": "Gold surges as investors seek safety from tariffs"},
        {"source": "CNBC", "title": "Gold rallies to new all-time high amid trade war fears"},
        {"source": "FT", "title": "Central banks accelerate gold reserves purchases"},
    ]
    result = cluster_headlines(test_headlines)
    print(f"  Sources:   {result['n_sources']}")
    print(f"  Coherence: {result['narrative_coherence_score']:.1f} / 100")
    print(f"  Overlap:   {result['avg_keyword_overlap']:.3f}")

    print("\\n  Narrative Evolution Test:")
    evolution = track_narrative_evolution(
        test_headlines,
        previous_clusters={"narrative_coherence_score": 42.0},
    )
    print(f"  Coherence: {evolution['narrative_coherence_score']:.1f} → Momentum: {evolution['momentum']:+.1f}")
    print(f"  Gaining credibility: {evolution['gaining_credibility']}")
