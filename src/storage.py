import datetime
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

RECIPIENTS_FILE = DATA_DIR / "recipients.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
SESSION_FILE = DATA_DIR / "tiktok-session.json"

DEFAULT_MESSAGE = "<3"
TIKTOK_HOME_URL = "https://www.tiktok.com/"

try:
    VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    VIETNAM_TZ = datetime.timezone(datetime.timedelta(hours=7))


def get_now() -> datetime.datetime:
    return datetime.datetime.now(VIETNAM_TZ)


def get_now_iso() -> str:
    return get_now().isoformat(timespec="seconds")


def is_sent_today(last_sent_date: str | None) -> bool:
    if not last_sent_date:
        return False

    today_date = get_now().date()

    try:
        dt = datetime.datetime.fromisoformat(last_sent_date)
        if dt.tzinfo is not None:
            dt_target = dt.astimezone(VIETNAM_TZ)
        else:
            dt_target = dt
        return dt_target.date() == today_date
    except Exception:
        return last_sent_date.startswith(today_date.strftime("%Y-%m-%d"))


def notify(title: str, message: str) -> bool:
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("TikTok Streak CLI")
        toast = Toast([title, message])
        toaster.show_toast(toast)
        return True
    except Exception as exc:
        logger.debug("Failed to send Windows Toast notification: %s", exc)
        return False


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}. Please repair or restore the file before continuing."
        ) from exc


def initialize_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RECIPIENTS_FILE.exists():
        _atomic_write_json(RECIPIENTS_FILE, [])
    if not SETTINGS_FILE.exists():
        _atomic_write_json(
            SETTINGS_FILE,
            {
                "default_message": DEFAULT_MESSAGE,
            },
        )


def load_settings() -> dict:
    return _read_json(SETTINGS_FILE, {})


def save_settings(settings: dict) -> None:
    _atomic_write_json(SETTINGS_FILE, settings)


@dataclass(slots=True)
class Recipient:
    username: str
    user_id: str | None = None
    message: str | None = None
    last_sent_date: str | None = None
    created_at: str = ""

    @classmethod
    def create(
        cls,
        username: str,
        user_id: str | None = None,
    ) -> "Recipient":
        normalized = username.strip().removeprefix("@")
        return cls(
            username=normalized,
            user_id=user_id.strip() if user_id else None,
            created_at=get_now_iso(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Recipient":
        return cls(
            username=str(data["username"]),
            user_id=data.get("user_id"),
            message=data.get("message"),
            last_sent_date=data.get("last_sent_date"),
            created_at=str(data.get("created_at", "")),
        )


def load_recipients() -> list[Recipient]:
    raw = _read_json(RECIPIENTS_FILE, [])
    if not isinstance(raw, list):
        raise ValueError(f"{RECIPIENTS_FILE} must contain a JSON array.")
    return [Recipient.from_dict(item) for item in raw]


def save_recipients(recipients: list[Recipient]) -> None:
    _atomic_write_json(RECIPIENTS_FILE, [recipient.to_dict() for recipient in recipients])


class RecipientExistsError(ValueError):
    pass


class RecipientNotFoundError(ValueError):
    pass


def add_recipient(username: str, user_id: str | None = None) -> Recipient:
    recipient = Recipient.create(username, user_id)
    if not recipient.username:
        raise ValueError("Username cannot be empty.")

    recipients = load_recipients()
    if any(item.username.casefold() == recipient.username.casefold() for item in recipients):
        raise RecipientExistsError(f"@{recipient.username} already exists.")

    recipients.append(recipient)
    save_recipients(recipients)
    return recipient


def remove_recipient(username: str) -> Recipient:
    normalized = username.strip().removeprefix("@")
    recipients = load_recipients()
    for index, recipient in enumerate(recipients):
        if recipient.username.casefold() == normalized.casefold():
            removed = recipients.pop(index)
            save_recipients(recipients)
            return removed
    raise RecipientNotFoundError(f"Could not find @{normalized}.")


def list_recipients() -> list[Recipient]:
    return load_recipients()


def get_recipient(username: str) -> Recipient | None:
    normalized = username.strip().removeprefix("@").casefold()
    for recipient in load_recipients():
        if recipient.username.casefold() == normalized:
            return recipient
    return None


def set_recipient_message(username: str, message: str | None) -> Recipient:
    normalized = username.strip().removeprefix("@").casefold()
    recipients = load_recipients()
    for recipient in recipients:
        if recipient.username.casefold() == normalized:
            recipient.message = message.strip() if message else None
            save_recipients(recipients)
            return recipient
    raise RecipientNotFoundError(f"Could not find @{username}.")


def mark_as_sent(username: str, timestamp: str | None = None) -> Recipient:
    normalized = username.strip().removeprefix("@").casefold()
    recipients = load_recipients()
    for recipient in recipients:
        if recipient.username.casefold() == normalized:
            recipient.last_sent_date = timestamp or get_now_iso()
            save_recipients(recipients)
            return recipient
    raise RecipientNotFoundError(f"Could not find @{username}.")


def update_recipient_user_id(username: str, user_id: str) -> Recipient:
    normalized = username.strip().removeprefix("@").casefold()
    recipients = load_recipients()
    for recipient in recipients:
        if recipient.username.casefold() == normalized:
            recipient.user_id = user_id.strip()
            save_recipients(recipients)
            return recipient
    raise RecipientNotFoundError(f"Could not find @{username}.")

