"""
The Void AI Orchestration System — Configuration
Version: 2.0.0 | ZQM Computing LLC

Pulls from environment variables / .env file.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Literal, List

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(r"C:\Void\ZQM-AI-Master\.env", override=True)


class Settings(BaseSettings):
    """All The Void configuration, sourced from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "The Void"
    # Canonical version is owned by app/core/version.py — import it so /api/status
    # and /api/version never drift apart.
    app_version: str = (lambda: __import__("app.core.version", fromlist=["__version__"]).__version__)()
    environment: Literal["development", "staging", "production"] = "development"
    app_debug: bool = Field(default=False, alias="APP_DEBUG")

    # ── ZQM_AI Identity ───────────────────────────────────────────────────────
    @field_validator("zqm_ai_id", mode="before")
    @classmethod
    def set_zqm_ai_id(cls, v):
        import socket
        host = socket.gethostname().lower()
        if host.endswith("-2") or host.endswith("-02") or "node-2" in host:
            return v or "ZQM-ZQM_AI-002"
        if host.endswith("-3") or host.endswith("-03") or "node-3" in host:
            return v or "ZQM-ZQM_AI-003"
        if host.endswith("-4") or host.endswith("-04") or "node-4" in host:
            return v or "ZQM-ZQM_AI-004"
        if host.endswith("-1") or host.endswith("-01") or "node-1" in host:
            return v or "ZQM-ZQM_AI-001"
        return v
    zqm_ai_id: str = Field(default="ZQM-ZQM_AI-004")

    @field_validator("zqm_ai_employee_id", mode="before")
    @classmethod
    def set_zqm_ai_employee_id(cls, v):
        if v and str(v).strip():
            return v
        import socket
        host = socket.gethostname().lower()
        if host.endswith("-2") or host.endswith("-02") or "node-2" in host:
            return "ZQM_AI-002"
        if host.endswith("-3") or host.endswith("-03") or "node-3" in host:
            return "ZQM_AI-003"
        if host.endswith("-4") or host.endswith("-04") or "node-4" in host:
            return "ZQM_AI-004"
        if host.endswith("-1") or host.endswith("-01") or "node-1" in host:
            return "ZQM_AI-001"
        return v

    zqm_ai_employee_id: str = Field(default="ZQM_AI-001")
    @field_validator("zqm_ai_primary_garden", mode="before")
    @classmethod
    def set_zqm_ai_primary_garden(cls, v):
        if v and str(v).strip():
            return v
        import socket
        host = socket.gethostname().lower()
        mapping = {
            "node-1": "Garden-1 (ZQM-Garden-01, 192.168.1.172)",
            "node-2": "Garden-3 (ZQM-GARDEN-03, 192.168.1.64)",
            "node-3": "Garden-2 (ZQM-GARDEN-02, 192.168.1.38)",
            "node-4": "Garden-0 (ZQM-Garden-00, 192.168.1.225)",
            "node-9": "Garden-4 (ZQM-GARDEN-04, 192.168.1.144)",
        }
        for key, garden in mapping.items():
            if host.endswith(key) or key in host:
                return garden
        return v

    # Primary garden node: N4 self-referential by default.
    # Real mesh is built at runtime from GARDEN_NODE_* env vars.
    zqm_ai_primary_garden: str = Field(default="Garden-0 (ZQM-Garden-00, 192.168.1.225)")

    # ── Network ───────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8808
    workers: int = 1

    # ── Security / JWT ────────────────────────────────────────────────────────
    secret_key: str = Field(
        default="insecure-default-rotate-before-deployment",
        description="JWT signing key — MUST be overridden in production with a strong random value",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite://./zqm_ai.db"
    database_echo: bool = False

    # ── Redis / VoidCache ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    cache_ttl_seconds: int = 3600
    void_cache_max_size: int = 512
    void_cache_strategy: Literal["LRU", "LFU", "FIFO"] = "LRU"

    # ── ZQM Garden ──────────────────────────────────────────────────────────────
    # Live Garden API cluster is the mesh Void nodes themselves.
    # Canonical host IPs:
    #   Garden-0 = COMB / zqm-void-pve    192.168.1.225  (primary/Queen)
    #   Garden-1 = ZQM-Garden-01          192.168.1.172  (backup/Queen 11)
    #   Garden-2 = ZQM-GARDEN-02          192.168.1.38   (worker)
    #   Garden-3 = ZQM-GARDEN-03          192.168.1.64   (worker)
    #   Garden-4 = ZQM-GARDEN-04          192.168.1.144  (worker)
    garden_endpoint: str = "http://192.168.1.225:8808/api/garden/coordinate"
    garden_node_0: str = "192.168.1.225"
    garden_node_1: str = "192.168.1.172"
    garden_node_2: str = "192.168.1.38"
    garden_node_3: str = "192.168.1.64"
    garden_node_4: str = "192.168.1.144"
    garden_node_0_port: int = 8808
    garden_node_1_port: int = 5000
    garden_node_2_port: int = 5000
    garden_node_3_port: int = 5000
    garden_node_4_port: int = 443
    garden_timeout: int = 15
    garden_retries: int = 3
    garden_api_ports: Dict[str, int] = {
        "garden-0": 8808,
        "garden-1": 5000,
        "garden-2": 5000,
        "garden-3": 5000,
        "garden-4": 443,
    }

    # ── ZQM FLATSPACE ──────────────────────────────────────────────────────────────
    flatspace_endpoint: str = "http://192.168.1.225:8808/api/flatspace/store"
    flatspace_pollen_store: str = "http://192.168.1.225:8808/api/flatspace/pollen"
    flatspace_bit_garden: str = "http://192.168.1.225:8808/api/flatspace/bitgarden"
    flatspace_wax_cell: str = "http://192.168.1.225:8808/api/flatspace/waxcell"

    # ── ZQM Observability ─────────────────────────────────────────────────────
    observability_endpoint: str = "http://127.0.0.1:8808/api/observability/metrics"
    observability_enabled: bool = True
    metrics_port: int = 9091

    # ── SearXNG Web Augmentation ───────────────────────────────────────────
    searxng_url: str = Field(
        default="http://127.0.0.1:8080",
        validation_alias=AliasChoices("searxng_url", "SEARXNG_URL", "SEARX_URL", "SEARX_HOST"),
    )
    searxng_max_results: int = Field(
        default=5,
        validation_alias=AliasChoices("searxng_max_results", "SEARXNG_MAX_RESULTS"),
    )

    # ── Meilisearch Search Layer ───────────────────────────────────────────
    meilisearch_url: str = Field(
        default="http://127.0.0.1:7701",
        validation_alias=AliasChoices("meilisearch_url", "MEILISEARCH_URL", "MEILISEARCH_HOST"),
    )
    meilisearch_master_key: str = Field(
        default="",
        validation_alias=AliasChoices("meilisearch_master_key", "MEILISEARCH_MASTER_KEY"),
    )
    meilisearch_default_index: str = Field(
        default="flatspace",
        validation_alias=AliasChoices("meilisearch_default_index", "MEILISEARCH_DEFAULT_INDEX"),
    )

    # ── Chroma Vector Store ───────────────────────────────────────────────────
    chroma_url: str = Field(
        default="http://127.0.0.1:8001",
        validation_alias=AliasChoices("chroma_url", "CHROMA_URL", "CHROMA_HOST"),
    )
    chroma_collection: str = Field(
        default="flatspace",
        validation_alias=AliasChoices("chroma_collection", "CHROMA_COLLECTION"),
    )
    chroma_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("chroma_enabled", "CHROMA_ENABLED"),
    )

    # ── ZQM Network ───────────────────────────────────────────────────────────
    network_endpoint: str = "http://192.168.1.228:8808/api/network"

    # ── ZQM Eden ─────────────────────────────────────────────────────────────
    eden_endpoint: str = "http://192.168.1.228:8443/api/auth"
    eden_enabled: bool = False

    # ── SSO / OIDC ─────────────────────────────────────────────────────────────
    sso_oidc_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_issuer", "SSO_OIDC_ISSUER"),
    )
    sso_oidc_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_client_id", "SSO_OIDC_CLIENT_ID"),
    )
    sso_oidc_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_client_secret", "SSO_OIDC_CLIENT_SECRET"),
    )
    sso_oidc_metadata_url: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_metadata_url", "SSO_OIDC_METADATA_URL"),
    )
    sso_oidc_default_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_default_redirect_uri", "SSO_OIDC_DEFAULT_REDIRECT_URI"),
    )
    sso_provider: str = Field(
        default="",
        validation_alias=AliasChoices("sso_provider", "SSO_PROVIDER"),
    )
    jwt_issuer: str = Field(
        default="zqm-void",
        validation_alias=AliasChoices("jwt_issuer", "JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        default="zqm-void",
        validation_alias=AliasChoices("jwt_audience", "JWT_AUDIENCE"),
    )
    refresh_token_ttl_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("refresh_token_ttl_minutes", "REFRESH_TOKEN_TTL_MINUTES"),
    )

    # ── SSO / OIDC ─────────────────────────────────────────────────────────────
    sso_oidc_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_issuer", "SSO_OIDC_ISSUER"),
    )
    sso_oidc_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_client_id", "SSO_OIDC_CLIENT_ID"),
    )
    sso_oidc_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_client_secret", "SSO_OIDC_CLIENT_SECRET"),
    )
    sso_oidc_metadata_url: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_metadata_url", "SSO_OIDC_METADATA_URL"),
    )
    sso_oidc_default_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("sso_oidc_default_redirect_uri", "SSO_OIDC_DEFAULT_REDIRECT_URI"),
    )
    sso_provider: str = Field(
        default="",
        validation_alias=AliasChoices("sso_provider", "SSO_PROVIDER"),
    )
    jwt_issuer: str = Field(
        default="zqm-void",
        validation_alias=AliasChoices("jwt_issuer", "JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        default="zqm-void",
        validation_alias=AliasChoices("jwt_audience", "JWT_AUDIENCE"),
    )
    refresh_token_ttl_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("refresh_token_ttl_minutes", "REFRESH_TOKEN_TTL_MINUTES"),
    )

    # ── GitHub Integration ────────────────────────────────────────────────
    # Target GitHub repository for webhook ingestion and agent actions.
    # Defaults wire to the ZQM-Computing account; override via env if needed.
    github_repo_owner: str = Field(default="zqm-computing")
    github_repo_name: str = Field(default="")
    github_webhook_secret: str = Field(default="")
    github_token: str = Field(default="")

    # ── ZQM Engine URLs ───────────────────────────────────────────────────────
    # Each engine has a canonical env var (e.g. GIT_ENGINE_URL) matching .env
    git_engine_url: str = Field(
        default="http://zqm-git-engine:8092",
        validation_alias=AliasChoices("git_engine_url", "GIT_ENGINE_URL"),
    )
    dns_engine_url: str = Field(
        default="http://zqm-dns-engine:8094",
        validation_alias=AliasChoices("dns_engine_url", "DNS_ENGINE_URL"),
    )
    containerization_engine_url: str = Field(
        default="http://zqm-support-engine:8091",
        validation_alias=AliasChoices(
            "containerization_engine_url", "CONTAINERIZATION_ENGINE_URL"
        ),
    )
    audit_engine_url: str = Field(
        default="http://zqm-audit-engine:8001",
        validation_alias=AliasChoices("audit_engine_url", "AUDIT_ENGINE_URL"),
    )
    # Internal API key shared across all ZQM engines.
    # Must be supplied via env (ZQM_INTERNAL_KEY); no insecure default.
    zqm_internal_key: str = Field(
        default="",
        validation_alias=AliasChoices("zqm_internal_key", "ZQM_INTERNAL_KEY"),
    )

    # ── AI Providers ──────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"

    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-3-5-sonnet-20241022"

    # Accepts OLLAMA_BASE_URL (canonical), OLLAMA_URL, or OLLAMA_HOST from .env
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices(
            "ollama_base_url", "OLLAMA_BASE_URL", "OLLAMA_URL", "OLLAMA_HOST"
        ),
    )
    # Accepts OLLAMA_DEFAULT_MODEL (canonical) or OLLAMA_MODEL from .env
    ollama_default_model: str = Field(
        default="qwen2.5:3b",
        validation_alias=AliasChoices("ollama_default_model", "OLLAMA_DEFAULT_MODEL", "OLLAMA_MODEL"),
    )
    # Optional Bearer token for upstream Ollama auth proxies (ollama_auth_proxy.py).
    ollama_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ollama_api_key", "OLLAMA_API_KEY"),
    )

    default_ai_provider: Literal["openai", "anthropic", "ollama", "local_deterministic"] = "ollama"

    # Self-hosted mandate: external providers (OpenAI/Anthropic) are opt-in ONLY.
    # The Void runs on local Ollama by default. External calls stay blocked
    # unless explicitly enabled via ZQM_ALLOW_EXTERNAL_PROVIDERS=true.
    allow_external_providers: bool = Field(
        default_factory=lambda: os.getenv("ZQM_ALLOW_EXTERNAL_PROVIDERS", "false").lower() == "true"
    )

    # ── Cognitive Processing ──────────────────────────────────────────────────
    default_cognitive_level: Literal["basic", "advanced", "neural", "autonomous"] = "autonomous"
    max_concurrent_tasks: int = 20
    task_timeout_seconds: int = 300

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_file: str = "logs/zqm_ai.log"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = "*"
    cors_allow_credentials: bool = True

    # ── Computed properties ───────────────────────────────────────────────────
    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def garden_nodes(self) -> List[str]:
        return [
            self.garden_node_0,
            self.garden_node_1,
            self.garden_node_2,
            self.garden_node_3,
            self.garden_node_4,
        ]

    @field_validator("secret_key")
    @classmethod
    def warn_default_secret(cls, v: str) -> str:
        env = os.getenv("ENVIRONMENT", "development")
        # Refuse to boot in production with a forgeable key. This catches the
        # insecure default AND any short/human-memorable key (e.g. the legacy
        # 9-char password) — both allow trivial JWT forgery across every endpoint.
        if env == "production":
            if v.startswith("changeme"):
                raise ValueError(
                    "SECRET_KEY is still the insecure default — override it via the "
                    "SECRET_KEY env var (e.g. `openssl rand -hex 32`) before deploying "
                    "to production. A known key allows JWT forgery."
                )
            if len(v) < 32:
                raise ValueError(
                    "SECRET_KEY is too short (<32 chars) for production — a short key "
                    "is forgeable. Set a strong random key via SECRET_KEY env var "
                    "(e.g. `openssl rand -hex 32`). Refusing to boot."
                )
        elif v.startswith("changeme"):
            import warnings
            warnings.warn(
                "SECRET_KEY is the insecure default — override it before any real use.",
                stacklevel=2,
            )
        return v


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere."""
    return Settings()


# Module-level convenience alias
settings: Settings = get_settings()
