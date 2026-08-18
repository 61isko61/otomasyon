"""
Geri Bildirim Sunucusu v2 — SQLite + Telegram
================================================
İlk sürümden fark: işletmeler artık kod içindeki sabit bir sözlük yerine
küçük bir SQLite veritabanında (isletmeler.db) tutuluyor. Yeni işletme
eklemek için bu dosyayı değiştirmenize gerek yok — add_business.py
betiğini çalıştırmanız yeterli. Adım adım kurulum için KURULUM.md'ye
bakın.

ÇALIŞTIRMA
----------
pip install flask requests
export TELEGRAM_BOT_TOKEN="botfather'dan aldığınız token"
python feedback_server.py

ÖNEMLİ (yasal / uyumluluk)
---------------------------
'puan' alanı SADECE dahili önceliklendirme ve Telegram mesajının tonunu
belirler. Bu backend hiçbir koşulda Google linkinin frontend'de
gösterilip gösterilmeyeceğini etkilemiyor ve etkilememeli — o karar
tamamen HTML/JS tarafında, puan ne olursa olsun sabit kalacak şekilde
kurulu. Bu dosyayı değiştirirken bu ayrımı bozmayın.
"""

from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import requests
import os
from datetime import datetime
from contextlib import closing

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "isletmeler.db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

ETIKETLER = {1: "ÇOK KÖTÜ", 2: "KÖTÜ", 3: "ORTALAMA", 4: "İYİ", 5: "HARİKA"}
EMOJILER = {1: "😠", 2: "🙁", 3: "😐", 4: "🙂", 5: "🤩"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS isletmeler (
                slug TEXT PRIMARY KEY,
                ad TEXT NOT NULL,
                google_link TEXT NOT NULL,
                telegram_chat_id TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS geri_bildirimler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isletme_slug TEXT NOT NULL,
                puan INTEGER,
                yorum TEXT,
                zaman TEXT
            )
        """)
        conn.commit()


def telegram_gonder(chat_id, text):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        print("UYARI: bot token veya chat_id eksik, Telegram mesajı gönderilmedi.")
        return
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as exc:
        print(f"Telegram gönderim hatası: {exc}")


@app.route("/")
def anasayfa():
    """
    QR kodu bu adrese (?isletme=<slug> ile) yönlendirir. sablon.html'i
    burada, aynı sunucudan servis ediyoruz ki sayfa içindeki
    fetch('/api/isletme/...') çağrısı ayrı bir adrese değil, aynı
    sunucuya gitsin — ayrı bir yere yüklemenize gerek kalmıyor.
    """
    return send_from_directory(BASE_DIR, "sablon.html")


@app.route("/api/geri-bildirim/<slug>", methods=["POST"])
def geri_bildirim_al(slug):
    with closing(db()) as conn:
        isletme = conn.execute("SELECT * FROM isletmeler WHERE slug = ?", (slug,)).fetchone()
        if not isletme:
            return jsonify({"hata": "İşletme bulunamadı"}), 404

        veri = request.get_json(force=True) or {}
        try:
            puan = int(veri.get("puan", 0))
        except (TypeError, ValueError):
            puan = 0
        yorum = (veri.get("yorum") or "").strip()
        zaman = datetime.now().strftime("%d.%m.%Y %H:%M")

        conn.execute(
            "INSERT INTO geri_bildirimler (isletme_slug, puan, yorum, zaman) VALUES (?, ?, ?, ?)",
            (slug, puan, yorum, zaman),
        )
        conn.commit()
        isletme_ad = isletme["ad"]
        chat_id = isletme["telegram_chat_id"]

    etiket = ETIKETLER.get(puan, "belirtilmedi")
    emoji = EMOJILER.get(puan, "")
    oncelik = "ACİL" if puan in (1, 2) else "Bilgi"
    mesaj = (
        f"[{oncelik}] {isletme_ad}\n"
        f"Puan: {emoji} {etiket}\n"
        f"Yorum: {yorum or '(yazılmadı)'}\n"
        f"Zaman: {zaman}"
    )
    telegram_gonder(chat_id, mesaj)
    return jsonify({"durum": "iletildi"})


@app.route("/api/telegram-webhook", methods=["POST"])
def telegram_webhook():
    """Bir işletme sahibi bota /start yazınca chat_id'sini yakalar ve loglar."""
    update = request.get_json(force=True) or {}
    msg = update.get("message", {})
    if msg.get("text") == "/start":
        chat_id = msg.get("chat", {}).get("id")
        print(f"Yeni chat_id: {chat_id} -> add_business.py ile ilgili işletmeye bağlayın.")
        telegram_gonder(chat_id, f"Bağlantı başarılı. Chat ID: {chat_id}\nBu ID'yi işletme kaydınıza ekleyin.")
    return jsonify({"ok": True})


@app.route("/api/isletme/<slug>", methods=["GET"])
def isletme_bilgisi(slug):
    """Frontend sayfası işletme adı ve Google linkini buradan çeker."""
    with closing(db()) as conn:
        isletme = conn.execute(
            "SELECT slug, ad, google_link FROM isletmeler WHERE slug = ?", (slug,)
        ).fetchone()
        if not isletme:
            return jsonify({"hata": "İşletme bulunamadı"}), 404
        return jsonify(dict(isletme))


if __name__ == "__main__":
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
