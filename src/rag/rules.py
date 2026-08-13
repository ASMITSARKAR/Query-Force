import re
import yaml
from pathlib import Path
from src.rag.embedder import get_or_create_collection

def load_metrics():
    yaml_path = Path(__file__).parent.parent.parent / "data" / "metrics.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

METRICS = load_metrics()
metrics_collection = get_or_create_collection("metrics_catalog")

if metrics_collection.count() == 0:
    for metric_name, data in METRICS.items():
        aliases = data.get("aliases", [])
        if aliases:
            metrics_collection.upsert(
                ids=[f"{metric_name}_{i}" for i in range(len(aliases))],
                documents=aliases,
                metadatas=[{"metric_name": metric_name}] * len(aliases)
            )

def is_broad_intent(query: str) -> bool:
    broad_keywords = ["metric", "metrics", "kpi", "kpis", "summary", "overview", "stats", "statistics", "insight", "insights", "hi", "hello", "hey", "help", "who"]
    return any(re.search(rf"\b{kw}\b", query, re.IGNORECASE) for kw in broad_keywords)

def inject_business_rules(user_query: str, rag_mode: str = "schema_rag") -> str:
    if rag_mode == "doc_rag":
        return user_query
        
    injected_rules = []
    is_broad = is_broad_intent(user_query)
    
    if is_broad:
        for metric_name, data in METRICS.items():
            injected_rules.append(f"- {metric_name}: {data.get('rule', '')}")
    else:
        results = metrics_collection.query(query_texts=[user_query], n_results=3)
        if results['ids'] and results['ids'][0]:
            matched_metrics = set()
            for i, doc_id in enumerate(results['ids'][0]):
                dist = results['distances'][0][i]
                if dist < 0.5: # 50% confidence threshold
                    m_name = results['metadatas'][0][i]['metric_name']
                    if m_name not in matched_metrics:
                        matched_metrics.add(m_name)
                        injected_rules.append(f"- {m_name}: {METRICS[m_name].get('rule', '')}")

    if not injected_rules:
        return user_query
        
    rules_context = "\n\nBusiness Rules to strictly follow:\n" + "\n".join(injected_rules)
    
    if is_broad:
        rules_context += "\n\nSystem Note: The user is asking for general insights or metrics. Please formulate a valid SQL query that calculates the business metrics above using ONLY the provided schema tables (e.g. SELECT ..., ... FROM ...). Do NOT treat metric names as table names."
        
    return user_query + rules_context

if __name__ == "__main__":
    queries = [
        "What is our income?",
        "Who are the most active customers this month?",
        "Show me gross revenues by country"
    ]
    for q in queries:
        print(f"Original: {q}")
        print(f"Injected:\n{inject_business_rules(q)}")
        print("-" * 50)
