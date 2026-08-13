from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    GROQ_API_KEY: SecretStr
    QUERYFORCE_API_KEY: SecretStr
    ANALYTICS_DB_PATH: str = "data/analytics.db"
    TELEMETRY_DB_PATH: str = "data/telemetry.db"
    CHROMA_DIR: str = "data/chroma_persist"
    MAX_RETRIES: int = 2
    LLM_SQL_MODEL: str = "llama-3.3-70b-versatile"
    LLM_SYNTH_MODEL: str = "llama-3.1-8b-instant"

    RAG_CONFIDENCE_THRESHOLD: float = 0.15
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    AWS_REGION: str = "us-east-1"
    DYNAMODB_SESSION_TABLE: str = "queryforce_sessions"
    TELEMETRY_DSN: str = ""
    USE_OPENSEARCH: bool = False
    OPENSEARCH_URL: str = ""
    HYDE_CONFIDENCE_THRESHOLD: float = 0.4
    S3_DOCUMENTS_BUCKET: str = ""
    MAX_UPLOAD_SIZE_MB: int = 10

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), 
        env_file_encoding="utf-8"
    )
    
    def fetch_aws_secrets(self):
        if self.AWS_REGION:
            try:
                import boto3
                import json
                client = boto3.client('secretsmanager', region_name=self.AWS_REGION)
                
                if self.GROQ_API_KEY.get_secret_value() == "default":
                    response = client.get_secret_value(SecretId='queryforce/groq_api_key')
                    self.GROQ_API_KEY = SecretStr(response['SecretString'])
                    
                if not self.TELEMETRY_DSN:
                    response = client.get_secret_value(SecretId='queryforce/db_password')
                    self.TELEMETRY_DSN = response['SecretString']
            except Exception as e:
                print(f"Failed to fetch secrets from AWS: {e}")

settings = Settings()
settings.fetch_aws_secrets()
