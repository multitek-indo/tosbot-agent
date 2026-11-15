from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass(frozen=True)
class Settings:
    token: str
    owner_id: int
    db_path: Path
    out_dir: Path
    logo_path: Path
    groq_key: str
    groq_model: str
    groq_url: str
    gemini_key: str
    gemini_model: str
    gemini_url: str
    ai_primary: str
    timeout: int
    tz: ZoneInfo
    allowed_services: tuple[str, ...]
    name: str
    address: str
    phone: str
    email: str
    bank: str
    account: str
    account_name: str
    signer: str
    city: str
    offer_signature_path: Path

    @classmethod
    def load(cls) -> 'Settings':
        owner = env("TELEGRAM_OWNER_ID", "0")
        try: owner_id = int(owner)
        except ValueError: owner_id = 0
        timezone = env("TZ", "Asia/Jakarta")
        try: zone = ZoneInfo(timezone)
        except Exception: zone = ZoneInfo("Asia/Jakarta")
        services = tuple(x.strip() for x in env("ADMIN_ALLOWED_SERVICES").split(",") if x.strip())
        base = Path(__file__).resolve().parents[2]
        return cls(
            token=env("TELEGRAM_BOT_TOKEN"), owner_id=owner_id,
            db_path=Path(env("TOSBOT_DB_PATH", "/var/lib/tosbot-ai/tosbot.sqlite3")),
            out_dir=Path(env("TOSBOT_OUTPUT_DIR", "/var/lib/tosbot-ai/documents")),
            logo_path=Path(env("TOSBOT_LOGO_PATH", str(base / "assets/logo.png"))),
            groq_key=env("GROQ_API_KEY"), groq_model=env("GROQ_MODEL", "openai/gpt-oss-120b"),
            groq_url=env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            gemini_key=env("GEMINI_API_KEY"), gemini_model=env("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_url=env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
            ai_primary=env("AI_PRIMARY", "groq").lower(),
            timeout=max(8, min(120, int(env("AI_TIMEOUT", "40")))), tz=zone,
            allowed_services=services,
            name=env("COMPANY_NAME", "Perusahaan Anda"),
            address=env("COMPANY_ADDRESS"),phone=env("COMPANY_PHONE"),
            email=env("COMPANY_EMAIL"), bank=env("COMPANY_BANK", ""),
            account=env("COMPANY_ACCOUNT"),account_name=env("COMPANY_ACCOUNT_NAME"),
            signer=env("COMPANY_SIGNER", ""),city=env("COMPANY_CITY", ""),
            offer_signature_path=Path(env("TOSBOT_OFFER_SIGNATURE_PATH", str(base / "assets/offer-signature.png"))),
        )

    def validate(self):
        if not self.token or self.token == "ISI_TOKEN_BOTFATHER":
            raise ValueError("Isi TELEGRAM_BOT_TOKEN di /etc/tosbot-ai/tosbot.env")
        # owner_id=0 adalah mode onboarding yang hanya melayani /myid.
        # Semua tindakan lain ditolak sampai pemilik disetel.
        if self.ai_primary != "groq":
            raise ValueError("AI_PRIMARY harus groq. Ubah AI_PRIMARY=groq (konfigurasi lama xai tidak didukung).")
        if not self.groq_key or self.groq_key.startswith("ISI_"):
            raise ValueError("Isi GROQ_API_KEY untuk Groq AI sebagai provider utama.")
