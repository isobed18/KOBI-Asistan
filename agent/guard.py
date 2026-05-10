"""
Prompt Police — Guvenlik Katmani
=================================
1. Regex tabanli hizli filtre (maliyet: 0)
2. Konu uygunlugu kontrolu (keyword match)
3. Gelecekte: lightweight LLM classifier ile degistirilecek
"""

import re

# ── Injection Kaliplari ──
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"forget\s+(all\s+)?instructions",
    r"disregard\s+(all\s+)?",
    r"you\s+are\s+now",
    r"act\s+as\s+",
    r"pretend\s+(to\s+be|you)",
    r"new\s+instructions?\s*:",
    r"override\s+(system|instructions)",
    r"sen\s+art[iı]k",
    r"[oö]nceki\s+talimat",
    r"sistem\s+prompt",
    r"system\s+prompt",
    r"show\s+me\s+your\s+prompt",
    r"what\s+are\s+your\s+instructions",
    r"repeat\s+your\s+(system|initial)",
    r"DROP\s+TABLE",
    r"SELECT\s+\*\s+FROM",
    r"UNION\s+SELECT",
    r"INSERT\s+INTO",
    r"DELETE\s+FROM",
    r"UPDATE\s+.+\s+SET",
    r";\s*--",
    r"1\s*=\s*1",
    r"OR\s+1\s*=\s*1",
    r"'\s*OR\s+'",
]

# ── Izin Verilen Konular (whitelist keywords) ──
ALLOWED_TOPICS = [
    # Siparis
    "siparis", "sipariş", "order", "siparisim", "siparişim",
    "nerede", "durumu", "takip", "tracking",
    # Urun/Stok
    "urun", "ürün", "stok", "stock", "fiyat", "price",
    "var mi", "var mı", "mevcut", "kaldi", "kaldı",
    # Kargo
    "kargo", "teslimat", "teslim", "delivery", "gonderi", "gönder",
    "gecikme", "ne zaman", "gelir", "gelecek",
    # Ozet/Rapor
    "ozet", "özet", "rapor", "report", "bugun", "bugün",
    "durum", "summary", "kritik", "alarm", "uyari", "uyarı",
    # Genel
    "merhaba", "selam", "hello", "hi", "tesekkur", "teşekkür",
    "thanks", "yardim", "yardım", "help", "nasil", "nasıl",
    "kimsin", "ne yapabilirsin", "bilgi",
    # Numara/kod
    "numara", "no", "kod", "code", "telefon",
]

# ── Yasakli Konular ──
BLOCKED_TOPICS = [
    r"(python|java|sql|code|kod)\s+(yaz|write|generate)",
    r"(script|program)\s+(yaz|olustur|create)",
    r"(hack|exploit|bypass|crack)",
    r"(sifre|password|token|key|secret)",
    r"(admin|root|sudo|shell|terminal|cmd)",
]


class PromptPoliceResult:
    """Prompt police sonucu."""
    def __init__(self, is_safe: bool, reason: str = "", category: str = "safe"):
        self.is_safe = is_safe
        self.reason = reason
        self.category = category  # safe, injection, off_topic, blocked_topic


def check_message(message: str) -> PromptPoliceResult:
    """
    Mesaji 3 katmanda kontrol eder:
    1. Injection pattern tara
    2. Yasakli konu kontrolu
    3. Konu uygunlugu (whitelist)

    Returns: PromptPoliceResult
    """
    msg_lower = message.lower().strip()

    # Katman 1: Injection kontrolu
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return PromptPoliceResult(
                False,
                "Guvenlik filtresi: supheli pattern tespit edildi.",
                "injection"
            )

    # Katman 2: Yasakli konu kontrolu
    for pattern in BLOCKED_TOPICS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return PromptPoliceResult(
                False,
                "Bu konuda size yardimci olamiyorum. Lutfen siparis, urun veya kargo ile ilgili bir soru sorun.",
                "blocked_topic"
            )

    # Katman 3: Konu uygunlugu (cok kisa mesajlar veya selamlar pas gecer)
    if len(msg_lower) <= 10:
        return PromptPoliceResult(True)

    # Uzun mesajlarda en az bir ilgili keyword olmali
    has_relevant = any(kw in msg_lower for kw in ALLOWED_TOPICS)
    if not has_relevant and len(msg_lower) > 30:
        return PromptPoliceResult(
            False,
            "Bu konuda size yardimci olamiyorum. Siparis, urun, stok veya kargo ile ilgili sorular sorabilirsiniz.",
            "off_topic"
        )

    return PromptPoliceResult(True)
