"""Evaluation benchmark for Destination Recommender (Outstanding Level 1).

Measures Precision@10 of the IncuBrix Safety-Gated Recommender against:
1. Random baseline
2. Simple-score baseline (ranking purely by raw destination relevance_score)

EVALUATION LABELLING DISCLOSURE:
As required by the assessment brief, this evaluation set was hand-labelled by the engineer
(IncuBrix candidate). Relevance (1 = appropriate fit, 0 = irrelevant, blocked, or demoted)
was determined by checking vertical topic alignment, platform content guidelines, and rule
compliance (e.g. promotional posts to no-promo destinations are strictly negative/0).
"""

import json
import random
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import pytest

from app.models.destination import DestinationModel
from app.catalogue.recommender import recommender_engine, ContentItemSchema


def build_evaluation_destinations() -> List[DestinationModel]:
    """Construct a varied benchmark catalogue of 30 destinations across AI, SaaS, Video, and General domains."""
    recent_cert = datetime.now(timezone.utc) - timedelta(days=5)
    expired_cert = datetime.now(timezone.utc) - timedelta(days=45)

    destinations = []

    # 1. Ten AI & Deep Tech Destinations
    for i in range(1, 11):
        is_demoted = (i == 10)  # dest_eval_ai_10 is demoted
        destinations.append(
            DestinationModel(
                id=f"dest_eval_ai_{i}",
                name=f"AI Deep Tech Community {i}",
                url=f"https://ai-community{i}.example.com",
                normalised_url=f"ai-community{i}.example.com",
                platform_key="discourse" if i % 2 == 0 else "lemmy",
                connector_key="discourse" if i % 2 == 0 else "lemmy",
                category="ai",
                audience_tags=["ai", "machine learning", "llm", "neural"],
                self_promo_allowed=True if i != 1 else False,  # ai_1 prohibits promo
                link_policy="allowed",
                frequency_cap=10,
                relevance_score=3.5 if i < 5 else 4.0,  # Lower static score than some non-AI
                status="demoted" if is_demoted else "active",
                last_certified_at=recent_cert if not is_demoted else expired_cert
            )
        )

    # 2. Ten SaaS & Founder Destinations (High static scores 4.5-5.0)
    for i in range(1, 11):
        destinations.append(
            DestinationModel(
                id=f"dest_eval_saas_{i}",
                name=f"SaaS Founders Forum {i}",
                url=f"https://saas-hub{i}.example.com",
                normalised_url=f"saas-hub{i}.example.com",
                platform_key="discourse",
                connector_key="discourse",
                category="saas",
                audience_tags=["saas", "b2b", "founders", "startups"],
                self_promo_allowed=True,
                link_policy="allowed",
                frequency_cap=10,
                relevance_score=4.8,  # High static score to challenge simple baseline
                status="active",
                last_certified_at=recent_cert
            )
        )

    # 3. Ten Irrelevant / Demoted / Broken Destinations (Cooking, Gardening, Cars, Broken)
    irrel_topics = [
        ("cooking", ["recipes", "food"]),
        ("gardening", ["plants", "flowers"]),
        ("automotive", ["cars", "engines"]),
        ("chess", ["chess", "openings"]),
        ("music", ["guitar", "chords"]),
        ("pets", ["dogs", "cats"]),
        ("fitness", ["workouts", "gym"]),
        ("travel", ["flights", "hotels"]),
        ("broken_platform_1", ["general"]),
        ("broken_platform_2", ["general"])
    ]
    for idx, (cat, tags) in enumerate(irrel_topics, start=1):
        is_demoted = idx > 8
        destinations.append(
            DestinationModel(
                id=f"dest_eval_irrel_{idx}",
                name=f"General {cat.title()} Hub",
                url=f"https://{cat}.example.com",
                normalised_url=f"{cat}.example.com",
                platform_key="discourse",
                connector_key="discourse",
                category=cat,
                audience_tags=tags,
                self_promo_allowed=True,
                link_policy="allowed",
                frequency_cap=10,
                relevance_score=4.5 if idx <= 4 else 2.0,  # Some have deceivingly high static score
                status="demoted" if is_demoted else "active",
                last_certified_at=recent_cert if not is_demoted else expired_cert
            )
        )

    return destinations


def build_evaluation_dataset() -> List[Dict[str, Any]]:
    """Construct 5 labelled queries with ground-truth binary relevance."""
    ai_active_ids = {f"dest_eval_ai_{i}" for i in range(1, 10)}  # ai_10 is demoted
    ai_promo_safe_ids = {f"dest_eval_ai_{i}" for i in range(2, 10)}  # ai_1 forbids promo
    saas_active_ids = {f"dest_eval_saas_{i}" for i in range(1, 11)}

    return [
        {
            "query_id": "q1_ai_technical_guide",
            "content": ContentItemSchema(
                title="Fine-Tuning Open-Weights LLMs with LoRA: Benchmark and Optimization",
                body="A deep technical guide on parameter efficient fine tuning for LLMs, evaluating loss curves and inference cost across GPU setups.",
                tags=["ai", "machine learning", "llm", "neural"],
                category="ai"
            ),
            "relevant_ids": ai_active_ids  # All active AI destinations
        },
        {
            "query_id": "q2_ai_product_announcement_promo",
            "content": ContentItemSchema(
                title="We built an AI Video Tool for Creators - Try our free beta",
                body="Check out our new SaaS platform at https://incubrix.ai! Sign up for 50% discount on the founder plan.",
                tags=["ai", "saas", "video", "startup"],
                category="ai"
            ),
            # dest_eval_ai_1 forbids self-promo, so it is blocked! dest_eval_ai_10 is demoted!
            "relevant_ids": ai_promo_safe_ids | saas_active_ids
        },
        {
            "query_id": "q3_llm_inference_latency",
            "content": ContentItemSchema(
                title="Benchmarking vLLM vs TensorRT-LLM on NVIDIA H100",
                body="Empirical study of token throughput, time to first token, and KV cache paging strategies for generative AI serving.",
                tags=["ai", "llm", "neural", "machine learning"],
                category="ai"
            ),
            "relevant_ids": ai_active_ids
        },
        {
            "query_id": "q4_saas_pricing_playbook",
            "content": ContentItemSchema(
                title="B2B SaaS Pricing Playbook: Transitioning from Usage to Hybrid Tiers",
                body="How enterprise SaaS founders structure annual commitments with consumption overage buffers.",
                tags=["saas", "b2b", "founders", "startups"],
                category="saas"
            ),
            "relevant_ids": saas_active_ids
        },
        {
            "query_id": "q5_neural_search_embeddings",
            "content": ContentItemSchema(
                title="Dense Retrieval and Vector Search with ColBERT and BGE",
                body="Implementation guide for late interaction neural embeddings in generative ai search architectures.",
                tags=["ai", "machine learning", "neural"],
                category="ai"
            ),
            "relevant_ids": ai_active_ids
        }
    ]


@pytest.mark.anyio
async def test_recommender_precision_at_10_evaluation():
    """
    Run Precision@10 benchmark comparing:
    - Proposed IncuBrix Safety-Gated Recommender
    - Simple-score Baseline
    - Random Baseline
    Saves outputs/test_runs/recommender_precision_eval.json
    """
    destinations = build_evaluation_destinations()
    dataset = build_evaluation_dataset()

    k = 10
    incubrix_precisions = []
    simple_precisions = []
    random_precisions = []

    random.seed(42)

    for item in dataset:
        content = item["content"]
        relevant_ids = item["relevant_ids"]

        # 1. IncuBrix Proposed Recommender
        recs = await recommender_engine.rank_destinations(content, destinations, db=None, limit=k)
        rec_ids = [r.destination_id for r in recs]
        hits_incubrix = sum(1 for d_id in rec_ids if d_id in relevant_ids)
        p10_incubrix = hits_incubrix / len(rec_ids) if rec_ids else 0.0
        incubrix_precisions.append(p10_incubrix)

        # 2. Simple-Score Baseline (Sorts purely by destination.relevance_score, ignores rules, vertical & demotions)
        simple_ranked = sorted(destinations, key=lambda d: d.relevance_score, reverse=True)[:k]
        simple_ids = [d.id for d in simple_ranked]
        hits_simple = sum(1 for d_id in simple_ids if d_id in relevant_ids)
        p10_simple = hits_simple / len(simple_ids)
        simple_precisions.append(p10_simple)

        # 3. Random Baseline
        random_sample = random.sample(destinations, k)
        random_ids = [d.id for d in random_sample]
        hits_random = sum(1 for d_id in random_ids if d_id in relevant_ids)
        p10_random = hits_random / len(random_ids)
        random_precisions.append(p10_random)

    mean_p10_incubrix = sum(incubrix_precisions) / len(incubrix_precisions)
    mean_p10_simple = sum(simple_precisions) / len(simple_precisions)
    mean_p10_random = sum(random_precisions) / len(random_precisions)

    eval_report = {
        "evaluation_name": "IncuBrix Destination Recommender Precision@10 Evaluation",
        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_test_queries": len(dataset),
        "catalogue_size": len(destinations),
        "metrics": {
            "incubrix_recommender_mean_p10": round(mean_p10_incubrix, 4),
            "simple_score_baseline_mean_p10": round(mean_p10_simple, 4),
            "random_baseline_mean_p10": round(mean_p10_random, 4),
            "improvement_over_simple_baseline": f"{round((mean_p10_incubrix - mean_p10_simple) * 100, 2)}%",
            "improvement_over_random_baseline": f"{round((mean_p10_incubrix - mean_p10_random) * 100, 2)}%"
        },
        "query_breakdown": [
            {
                "query_id": dataset[i]["query_id"],
                "incubrix_p10": incubrix_precisions[i],
                "simple_p10": simple_precisions[i],
                "random_p10": random_precisions[i]
            }
            for i in range(len(dataset))
        ],
        "disclosure": "Labelled ground truth created by candidate based on destination audience alignment, recertification status, and posting rule safety gating."
    }

    # Save to outputs/test_runs/recommender_precision_eval.json
    with open("outputs/test_runs/recommender_precision_eval.json", "w") as f:
        json.dump(eval_report, f, indent=2)

    # Assert that IncuBrix recommender delivers superior precision over simple and random baselines
    assert mean_p10_incubrix > mean_p10_simple, f"Recommender ({mean_p10_incubrix}) did not beat simple baseline ({mean_p10_simple})"
    assert mean_p10_incubrix > mean_p10_random, f"Recommender ({mean_p10_incubrix}) did not beat random baseline ({mean_p10_random})"
    assert mean_p10_incubrix >= 0.85, f"Recommender precision ({mean_p10_incubrix}) was below 0.85"
