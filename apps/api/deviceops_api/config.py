"""Environment-based configuration with local-development defaults."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _integer_environment_value(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    mqtt_host: str
    mqtt_port: int
    mqtt_client_id: str
    cors_origins: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "DEVICEOPS_DATABASE_URL",
                "postgresql+psycopg://deviceops:deviceops-local@127.0.0.1:5432/deviceops",
            ),
            mqtt_host=os.getenv("DEVICEOPS_MQTT_HOST", "localhost"),
            mqtt_port=_integer_environment_value("DEVICEOPS_MQTT_PORT", 1883),
            mqtt_client_id=os.getenv("DEVICEOPS_MQTT_CLIENT_ID", "deviceops-api"),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "DEVICEOPS_CORS_ORIGINS",
                    "http://localhost:3000,http://127.0.0.1:3000",
                ).split(",")
                if origin.strip()
            ),
        )


settings = Settings.from_environment()
