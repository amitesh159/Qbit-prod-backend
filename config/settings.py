"""
Qbit Backend Configuration Settings
Type-safe configuration management using Pydantic Settings
"""
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration settings loaded from environment variables.
    All settings are immutable and validated at startup.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ========================================================================
    # APPLICATION SETTINGS
    # ========================================================================
    app_name: str = Field(default="Qbit", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False, description="Debug mode")
    api_v1_prefix: str = Field(default="/api/v1", description="API version 1 prefix")
    
    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    reload: bool = Field(default=False, description="Auto-reload on code changes")
    
    # ========================================================================
    # DATABASE - MONGODB
    # ========================================================================
    mongodb_uri: str = Field(..., description="MongoDB connection URI")
    mongodb_db_name: str = Field(default="qbit_database", description="MongoDB database name")
    mongodb_min_pool_size: int = Field(default=10, description="Minimum connection pool size")
    mongodb_max_pool_size: int = Field(default=100, description="Maximum connection pool size")
    
    # ========================================================================
    # DATABASE - REDIS
    # ========================================================================
    redis_url: str = Field(..., description="Redis connection URL")
    redis_max_connections: int = Field(default=50, description="Maximum Redis connections")
    redis_socket_timeout: int = Field(default=5, description="Redis socket timeout in seconds")
    redis_socket_connect_timeout: int = Field(default=5, description="Redis socket connect timeout in seconds")
    
    # ========================================================================
    # AI/LLM PROVIDERS
    # ========================================================================
    # Groq Cloud (Central Hub)
    groq_api_keys: str = Field(..., description="Comma-separated Groq API keys for rotation")
    groq_model: str = Field(default="openai/gpt-oss-120b", description="Groq model identifier")
    groq_rpm_limit: int = Field(default=30, description="Groq requests per minute limit")
    
    # Cerebras Cloud (Full Stack Agent)
    cerebras_api_keys: str = Field(..., description="Comma-separated Cerebras API keys for rotation")
    cerebras_model: str = Field(default="qwen-3-32b", description="Cerebras model identifier")
    cerebras_rpm_limit: int = Field(default=60, description="Cerebras requests per minute limit")
    
    # ========================================================================
    # E2B SANDBOX
    # ========================================================================
    e2b_api_key: str = Field(..., description="E2B Code Interpreter API key")
    e2b_timeout: int = Field(default=300, description="E2B sandbox timeout in seconds")
    e2b_max_sandboxes: int = Field(default=10, description="Maximum concurrent sandboxes")
    e2b_template_id: str = Field(..., description="E2B sandbox template ID (required)")
    
    # ========================================================================
    # AUTHENTICATION & SECURITY
    # ========================================================================
    jwt_secret_key: str = Field(..., description="JWT secret key for token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_days: int = Field(default=7, description="JWT token expiration in days")
    
    bcrypt_rounds: int = Field(default=12, description="Bcrypt hashing rounds")
    
    # GitHub OAuth
    github_client_id: str = Field(..., description="GitHub OAuth client ID")
    github_client_secret: str = Field(..., description="GitHub OAuth client secret")
    github_callback_url: str = Field(..., description="GitHub OAuth callback URL")
    
    # ========================================================================
    # CELERY (BACKGROUND TASKS)
    # ========================================================================
    celery_broker_url: str | None = Field(default=None, description="Celery broker URL (Redis) - optional")
    celery_result_backend: str | None = Field(default=None, description="Celery result backend URL - optional")
    celery_task_serializer: str = Field(default="json", description="Task serialization format")
    celery_result_serializer: str = Field(default="json", description="Result serialization format")
    celery_timezone: str = Field(default="UTC", description="Celery timezone")
    celery_enable_utc: bool = Field(default=True, description="Enable UTC timezone")
    
    # ========================================================================
    # RATE LIMITING
    # ========================================================================
    rate_limit_code_generation: int = Field(default=10, description="Code generation requests per minute per user")
    rate_limit_api_calls: int = Field(default=60, description="API calls per minute per user")
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_global: int = Field(default=1000, description="Global requests per hour per IP")
    
    # ========================================================================
    # CREDITS SYSTEM
    # ========================================================================
    default_user_credits: int = Field(default=100, description="Default credits for new users")
    credit_simple_project: int = Field(default=10, description="Credits for simple projects")
    credit_moderate_project: int = Field(default=20, description="Credits for moderate projects")
    credit_complex_project: int = Field(default=30, description="Credits for complex projects")
    credit_web_search: int = Field(default=2, description="Credits per web search")
    
    # ========================================================================
    # CORS SETTINGS
    # ========================================================================
    cors_origins: str = Field(default="http://localhost:3000", description="Comma-separated allowed CORS origins")
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_allow_methods: str = Field(default="*", description="Allowed HTTP methods")
    cors_allow_headers: str = Field(default="*", description="Allowed HTTP headers")
    
    # ========================================================================
    # LOGGING
    # ========================================================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or console")
    
    # ========================================================================
    # MONITORING
    # ========================================================================
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics server port")
    
    # ========================================================================
    # CONTEXT MANAGEMENT
    # ========================================================================
    max_context_tokens: int = Field(default=30000, description="Maximum tokens for context retrieval")
    max_conversation_turns: int = Field(default=10, description="Maximum conversation turns to retrieve")
    max_files_in_context: int = Field(default=8, description="Maximum files to include in context")
    max_modules_in_context: int = Field(default=5, description="Maximum modules to include in context")
    
    # ========================================================================
    # SANDBOX DECISION
    # ========================================================================
    default_sandbox: str = Field(default="auto", description="Default sandbox: auto, e2b, sandpack")
    
    # ========================================================================
    # DEVELOPMENT OPTIONS
    # ========================================================================
    show_error_details: bool = Field(default=False, description="Show detailed error messages")
    enable_docs: bool = Field(default=True, description="Enable API documentation (/docs)")
    
    # ========================================================================
    # VALIDATORS
    # ========================================================================
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value"""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper
    
    @field_validator("default_sandbox")
    @classmethod
    def validate_default_sandbox(cls, v: str) -> str:
        """Validate default sandbox"""
        allowed = ["auto", "e2b", "sandpack"]
        if v not in allowed:
            raise ValueError(f"default_sandbox must be one of {allowed}")
        return v
    
    # ========================================================================
    # COMPUTED PROPERTIES
    # ========================================================================
    @property
    def groq_api_keys_list(self) -> List[str]:
        """Parse comma-separated Groq API keys into list"""
        return [key.strip() for key in self.groq_api_keys.split(",") if key.strip()]
    
    @property
    def cerebras_api_keys_list(self) -> List[str]:
        """Parse comma-separated Cerebras API keys into list"""
        return [key.strip() for key in self.cerebras_api_keys.split(",") if key.strip()]
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into list"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == "production"


# ============================================================================
# GLOBAL SETTINGS INSTANCE
# ============================================================================
settings = Settings()
