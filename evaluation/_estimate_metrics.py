"""Estimate RAG retrieval and agent eval metrics without a live backend."""
import sys, json, random
sys.path.insert(0, ".")
from evaluation.metrics import summarize, hit_rate, recall_at_k, precision_at_k, reciprocal_rank

# ── RAG Retrieval dataset ──────────────────────────────────────────────────────
with open("evaluation/network_rag_eval.json", encoding="utf-8") as f:
    data = json.load(f)

cases = data["cases"]
k = int(data["k"])

TOPIC_POOL = ["dns", "tcp", "network", "http", "tls", "routing", "ssl", "udp", "icmp", "arp"]

# Simulate two scenarios
for scenario, hit_prob, rank_range in [
    ("Optimistic (hit prob=0.80, rank 1-2)", 0.80, (0, 1)),
    ("Pessimistic (hit prob=0.50, rank 1-4)", 0.50, (0, 3)),
]:
    random.seed(42)
    rows = []
    for case in cases:
        relevant = set(case["relevant"])
        retrieved = random.sample([t for t in TOPIC_POOL if t not in relevant], k)
        if random.random() < hit_prob:
            insert_pos = random.randint(*rank_range)
            rel_item = random.choice(sorted(relevant))
            retrieved.insert(insert_pos, rel_item)
            retrieved = retrieved[:k]
        latency = round(random.uniform(120, 600), 2)
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "relevant": sorted(relevant),
            "retrieved": retrieved,
            "latency_ms": latency,
        })

    summary = summarize(rows, k=k)
    print(f"\n{'='*55}")
    print(f"  Scenario: {scenario}")
    print(f"{'='*55}")
    for key, val in summary.items():
        bar = "#" * int(val * 20) if val <= 1.0 else ""
        print(f"  {key:<22}: {val:>7.4f}  {bar}")

    print(f"\n  {'ID':<5} {'Hit@5':<8} {'Recall@5':<10} {'Prec@5':<8} {'MRR':<8} {'Latency ms'}")
    print(f"  {'-'*55}")
    for row in rows:
        rel = set(row["relevant"])
        ret = row["retrieved"]
        h  = hit_rate(ret, rel, k)
        rc = recall_at_k(ret, rel, k)
        pr = precision_at_k(ret, rel, k)
        rr = reciprocal_rank(ret, rel)
        print(f"  {row['id']:<5} {h:<8.0f} {rc:<10.3f} {pr:<8.3f} {rr:<8.3f} {row['latency_ms']}")

# ── Agent eval dataset ─────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print("  Agent Evaluation Cases (qualitative)")
print(f"{'='*55}")
with open("evaluation/agents.json", encoding="utf-8") as f:
    agent_data = json.load(f)

for tc in agent_data["agent_evaluation"]:
    tool = tc.get("expected_tool", "—")
    print(f"  {tc['id']}: expected_tool={tool:<14} | {tc['expected_behavior']}")

# ── RAG HTTP eval dataset ──────────────────────────────────────────────────────
print(f"\n{'='*55}")
print("  RAG HTTP Eval Cases (require live backend)")
print(f"{'='*55}")
with open("evaluation/rag_evals.json", encoding="utf-8") as f:
    rag_data = json.load(f)

for tc in rag_data["rag_evaluation"]:
    print(f"  {tc['id']}: {tc['expected_behavior']}")
