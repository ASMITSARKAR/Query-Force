import asyncio
import sqlite3
from pathlib import Path
from tabulate import tabulate
import sys
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.db.inspector import get_full_schema
from src.rag.embedder import get_or_create_collection

async def ingest_schema_catalog():
    print("Starting schema catalog ingestion...")
    
    collection = get_or_create_collection()
    
    schema = await get_full_schema()
    
    db_path = Path(settings.ANALYTICS_DB_PATH).absolute()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    metrics_path = Path(__file__).parent.parent / "data" / "metrics.yaml"
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = yaml.safe_load(f)
    
    ids = []
    documents = []
    metadatas = []
    summary_data = []
    
    for table_name, data in schema.items():
        safe_name = f'[{table_name}]'
        cursor.execute(f"SELECT * FROM {safe_name} LIMIT 3")
        rows = cursor.fetchall()
        
        if rows:
            cols = list(rows[0].keys())
        else:
            col_cursor = conn.execute(f"PRAGMA table_info({table_name})")
            cols = [c[1] for c in col_cursor.fetchall()]
            
        sample_data = [dict(row) for row in rows]
            
        fks_str = "None"
        if data["foreign_keys"]:
            fks_str = ", ".join([f"{fk['from']} -> {fk['table']}.{fk['to']}" for fk in data["foreign_keys"]])
            
        related_metrics = []
        for metric_name, m_data in metrics.items():
            if table_name in m_data.get("rule", "").lower():
                aliases = ", ".join(m_data.get("aliases", []))
                related_metrics.append(f"{metric_name} ({aliases})")
                
        metrics_str = "None"
        if related_metrics:
            metrics_str = ", ".join(related_metrics)
            
        broad_keywords = "metric, metrics, kpi, kpis, summary, overview, stats, statistics, insight, insights, hi, hello, hey, help, who"
            
        doc = (
            f"Table: {table_name} | "
            f"Columns: {', '.join(cols)} | "
            f"Foreign Keys: {fks_str} | "
            f"Related Business Metrics: {metrics_str} | "
            f"Broad Match Keywords: {broad_keywords} | "
            f"Sample Data (top 3 rows): {sample_data}"
        )
        
        ids.append(table_name)
        documents.append(doc)
        metadatas.append({"ddl": data["ddl"]})
        
        summary_data.append([table_name, len(doc), len(data["ddl"])])
        
    conn.close()
    
    print(f"Upserting {len(ids)} tables into ChromaDB...")
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    
    print("\nIngestion Complete! Summary:")
    print(tabulate(summary_data, headers=["Table ID", "Doc Char Count", "DDL Char Count"], tablefmt="pretty"))

if __name__ == "__main__":
    asyncio.run(ingest_schema_catalog())
