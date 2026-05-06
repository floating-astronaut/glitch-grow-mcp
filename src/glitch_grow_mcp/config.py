from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    host: str = Field("127.0.0.1", alias="GGM_HOST")
    port: int = Field(3106, alias="GGM_PORT")

    ads_agent_base_url: str = Field("http://127.0.0.1:3110", alias="ADS_AGENT_BASE_URL")
    # Shared-secret bearer the ads-agent expects on /agent/run (admin-gated endpoint).
    ads_agent_run_token: str | None = Field(None, alias="AGENT_RUN_TOKEN")
    meta_ads_mcp_url: str = Field("http://127.0.0.1:3103", alias="META_ADS_MCP_URL")
    amazon_ads_mcp_url: str = Field("http://127.0.0.1:3105", alias="AMAZON_ADS_MCP_URL")

    social_agent_repo: Path = Field(
        Path("/home/support/glitch-social-media-agent"), alias="SOCIAL_AGENT_REPO"
    )
    ads_agent_repo: Path = Field(
        Path("/home/support/glitch-grow-ads-agent"), alias="ADS_AGENT_REPO"
    )
    shopify_hub_repo: Path = Field(
        Path("/home/support/multi-store-theme-manager"), alias="SHOPIFY_HUB_REPO"
    )

    data_dir: Path = Field(
        Path("/home/support/glitch-grow-mcp/data"), alias="GGM_DATA_DIR"
    )
    tenants_dir: Path = Field(
        Path("/home/support/glitch-grow-mcp/tenants"), alias="GGM_TENANTS_DIR"
    )

    log_level: str = Field("INFO", alias="GGM_LOG_LEVEL")

    @property
    def tokens_db_path(self) -> Path:
        return self.data_dir / "tokens.sqlite"

    @property
    def audit_db_path(self) -> Path:
        return self.data_dir / "audit.sqlite"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.data_dir.mkdir(parents=True, exist_ok=True)
        _settings.tenants_dir.mkdir(parents=True, exist_ok=True)
    return _settings
