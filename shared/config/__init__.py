"""
Shared configuration module for Maritime Intelligence Platform.

This module provides configuration validation and utilities used across
all microservices.
"""

from .secrets_validator import (
    SecretsValidationError,
    validate_database_url,
    validate_redis_url,
    validate_secrets,
    validate_service_secrets,
)

__all__ = [
    "SecretsValidationError",
    "validate_secrets",
    "validate_service_secrets",
    "validate_database_url",
    "validate_redis_url",
]
