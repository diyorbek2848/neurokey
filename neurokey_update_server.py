# -*- coding: utf-8 -*-
"""
Yangilanish serveri — o'z kompingizda ishlatadi.
NeuroKey.zip ni tarmoq orqali boshqa kompga beradi. OneDrive/Dropbox shart emas.

Ishga tushirish: python neurokey_update_server.py [port]
Default port: 8766. Boshqa kompda .env da: NEUROKEY_UPDATE_URL=http://SIZNING_IP:8766
"""
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
UPDATE_RELEASE = os.path.join(SOURCE_DIR, "update_release")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    os.makedirs(UPDATE_RELEASE, exist_ok=True)
    zip_path = os.path.join(SOURCE_DIR, "NeuroKey.zip")
    if os.path.isfile(zip_path):
        import shutil
        dest = os.path.join(UPDATE_RELEASE, "NeuroKey.zip")
        shutil.copy2(zip_path, dest)
    os.chdir(UPDATE_RELEASE)
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Yangilanish serveri: http://0.0.0.0:{port}/  (NeuroKey.zip shu yerdan yuklanadi).", flush=True)
    print("Boshqa kompda .env: NEUROKEY_UPDATE_URL=http://BU_KOMP_IP:8766", flush=True)
    print("To'xtatish: Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.shutdown()


if __name__ == "__main__":
    main()
