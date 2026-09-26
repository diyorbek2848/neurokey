# -*- coding: utf-8 -*-
"""
NeuroKey - Omniscient System Indexer
Kompyuter fayl tizimini (Xaritasini) SQLite bazasiga saqlaydi. 
Shu orqali LLM kompyuterdagi qaysi dastur/fayl qayerda ekanligini 
soniyaning mingdan birida topa oladi.
"""

import os
import sqlite3
import logging
import threading
import time

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "system_map.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            filepath TEXT,
            ext TEXT,
            is_dir BOOLEAN
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)')
    conn.commit()
    conn.close()

def _scan_directory(start_path, cursor):
    """Bitta papkani chuqur skaner qilish"""
    count = 0
    try:
        for root, dirs, files in os.walk(start_path):
            # Ignore some very large/unnecessary hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['AppData', 'Windows', 'node_modules']]
            
            for d in dirs:
                cursor.execute('INSERT INTO files (filename, filepath, ext, is_dir) VALUES (?, ?, ?, ?)',
                               (d, os.path.join(root, d), '', True))
                count += 1
                
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                cursor.execute('INSERT INTO files (filename, filepath, ext, is_dir) VALUES (?, ?, ?, ?)',
                               (f, os.path.join(root, f), ext, False))
                count += 1
    except PermissionError:
        pass
    except Exception as e:
        log.error(f"[SystemIndexer] Skaner xatosi {start_path}: {e}")
    return count

def run_indexing():
    """Fonda ishga tushib, asosiy disk va muhim papkalarni skanerlaydi"""
    log.info("[SystemIndexer] Kompyuterni skanerlash boshlandi...")
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Eski ma'lumotlarni tozalaymiz (yangi Xarita tuzish uchun)
    cursor.execute('DELETE FROM files')
    
    # Skaner qilinadigan Asosiy papkalar
    user_home = os.path.expanduser("~")
    target_dirs = [
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Downloads"),
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    ]
    
    total_indexed = 0
    for t_dir in target_dirs:
        if os.path.exists(t_dir):
            c = _scan_directory(t_dir, cursor)
            total_indexed += c
            
    conn.commit()
    conn.close()
    log.info(f"[SystemIndexer] Skanerlash yakunlandi. Jami indekslandi: {total_indexed} ta fayl/papka.")

def start_indexing_thread():
    """Buni NeuroKey ishga tushganda orqa fonda chaqirish mumkin"""
    t = threading.Thread(target=run_indexing, daemon=True)
    t.start()

def search_system(query: str, limit: int = 10) -> list:
    """LLM berilgan fayl yoki dastur nomini izlaganda ishlaydi"""
    if not os.path.exists(DB_PATH):
        return []
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # LIKE orqali izlash
    cursor.execute('''
        SELECT filepath FROM files 
        WHERE filename LIKE ? 
        LIMIT ?
    ''', (f'%{query}%', limit))
    
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

if __name__ == "__main__":
    # Test uchun ishga tushirish
    run_indexing()
    res = search_system("juma")
    print("Topilganlar:", res)
