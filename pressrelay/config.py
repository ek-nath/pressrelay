from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path

class FeedConfig(BaseModel):
    url: str # Using str because some RSS URLs can have complex query params that HttpUrl might be strict about
    name: Optional[str] = None
    interval_seconds: int = Field(default=300, ge=60)

class AppConfig(BaseModel):
    database_url: str = Field(default="sqlite+aiosqlite:///data/pressrelay_v2.db")
    storage_path: Path = Field(default=Path("data/storage"))
    feeds: List[FeedConfig] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRESSRELAY_", case_sensitive=False)
    
    config_path: Path = Path("config.yml")
    
    def load_config(self) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()
        return AppConfig.from_yaml(self.config_path)

settings = Settings()
