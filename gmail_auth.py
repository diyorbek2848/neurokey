import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    # agar keyin "o‘chirish/archivelash/yuborish" ham qilmoqchi bo‘lsang:
    # "https://www.googleapis.com/auth/gmail.modify",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# credentials file: credentials.json yoki credentials (agar extension yashirilgan bo‘lsa)
cred_path_1 = os.path.join(BASE_DIR, "credentials.json")
cred_path_2 = os.path.join(BASE_DIR, "credentials")

if os.path.exists(cred_path_1):
    CREDENTIALS_FILE = cred_path_1
elif os.path.exists(cred_path_2):
    CREDENTIALS_FILE = cred_path_2
else:
    raise FileNotFoundError(f"credentials.json topilmadi. Google Cloud Console dan yuklab olib shu papkaga qo’ying: {BASE_DIR}")

TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

    # Brauzer avtomatik ochiladi. Ochilmasa, terminal URL beradi.
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=True,
        authorization_prompt_message="Brauzerda Google login qiling va Allow bosing. Agar brauzer ochilmasa, shu yerda berilgan URL'ni copy qilib oching: {url}",
        success_message="OK! Gmail ruxsat berildi. Endi bu tabni yopishingiz mumkin.",
    )

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print("\n✅ DONE: token.json yaratildi:", TOKEN_FILE)
    print("Endi gmail_bridge.py / main.py token.json bilan ishlaydi.")

if __name__ == "__main__":
    main()
