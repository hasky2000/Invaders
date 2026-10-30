"""ゲーム起動時に、同じディレクトリの設定ファイルを読み込む。"""

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


SETTINGS_PATH = Path(__file__).resolve().parent / "settings.ini"


@dataclass(frozen=True)
class Settings:
    extra_enabled: bool = True


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """ファイルや項目がない場合は、従来どおりEXTRAを有効にする。"""
    config = ConfigParser()
    config.read(path, encoding="utf-8")
    return Settings(extra_enabled=config.getboolean("game", "extra_enabled", fallback=True))
