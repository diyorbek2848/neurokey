# -*- coding: utf-8 -*-
"""
NeuroKey - Graph RAG (Long-term Knowledge Engine)

Bu modul NeuroKey ga loyihaning butun kod bazasi, eski hujjatlar va tunda o'rgangan 
narsalarini chuqur xotiraga (Graph RAG) saqlash imkonini beradi. 
Shu orqali u har bir faylni o'qimay turib ham uning ichida nima borligini biladi.
"""

import os
import json
import logging
from typing import Dict, List, Optional
import config as C

log = logging.getLogger(__name__)

KNOWLEDGE_GRAPH_FILE = os.path.join(C.APP_DIR, "data", "graph_rag_memory.json")
IGNORE_DIRS = {".git", "__pycache__", "venv", ".gemini", "sandbox", "neurokey_mobile"}
VALID_EXTENSIONS = {".py", ".md", ".txt", ".json"}

def _load_graph() -> Dict:
    """Xotira grafigini yuklash"""
    if os.path.exists(KNOWLEDGE_GRAPH_FILE):
        try:
            with open(KNOWLEDGE_GRAPH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[GraphRAG] Xotira o'qishda xatolik: {e}")
    
    return {"nodes": {}, "edges": [], "last_indexed": None}

def _save_graph(graph: Dict):
    """Xotira grafigini saqlash"""
    os.makedirs(os.path.dirname(KNOWLEDGE_GRAPH_FILE), exist_ok=True)
    try:
        with open(KNOWLEDGE_GRAPH_FILE, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[GraphRAG] Xotira saqlashda xatolik: {e}")

def index_local_workspace():
    """Lokal papkadagi muhim fayllarni indekslash"""
    log.info("[GraphRAG] Workspace fayllari indekslanmoqda...")
    graph = _load_graph()
    
    for root, dirs, files in os.walk(C.APP_DIR):
        # Ignore ayrim papkalar
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in VALID_EXTENSIONS:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, C.APP_DIR)
                
                # Oddiy fayl node
                if rel_path not in graph["nodes"]:
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read(2000) # Faqat boshini indekslaymiz
                        
                        graph["nodes"][rel_path] = {
                            "type": "file",
                            "name": file,
                            "summary": content[:500] + "...",
                            "path": file_path
                        }
                    except Exception:
                        pass
                        
    graph["last_indexed"] = "now"
    _save_graph(graph)
    log.info("[GraphRAG] Indekslash yakunlandi.")

def add_learned_knowledge(topic: str, summary: str):
    """Curiosity Engine orqali tunda o'rgangan bilimlarini qo'shadi."""
    graph = _load_graph()
    node_id = f"knowledge_{topic.replace(' ', '_')}"
    
    graph["nodes"][node_id] = {
        "type": "learned_concept",
        "name": topic,
        "summary": summary
    }
    
    _save_graph(graph)
    log.info(f"[GraphRAG] Yangi bilim qo'shildi: {topic}")

def query_knowledge_graph(query: str, limit: int = 3) -> str:
    """LLM ga muammo berilganda o'z xotirasidan o'xshash narsalarni izlaydi."""
    graph = _load_graph()
    query_lower = query.lower()
    
    results = []
    for node_id, data in graph["nodes"].items():
        if query_lower in node_id.lower() or query_lower in data.get("name", "").lower() or query_lower in data.get("summary", "").lower():
            results.append(data)
            
    if not results:
        return "Tizim xotirasida bu mavzuga oid fayl yoki bilim topilmadi."
        
    # Faqat birinchi limit tasi
    output = "Topilgan xotira qismlari (Graph RAG):\n"
    for r in results[:limit]:
        output += f"- Fayl/Mavzu: {r.get('name')}\n"
        output += f"  Qisqacha: {r.get('summary', '')[:200]}\n"
        
    return output

if __name__ == "__main__":
    index_local_workspace()
