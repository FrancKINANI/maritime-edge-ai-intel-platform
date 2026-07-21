"""
Secrets validation module for Maritime Intelligence Platform.

This module provides utilities to validate that required environment variables
and secrets are present before starting services. This prevents runtime errors
due to missing configuration.

NOTE: Validation functions do NOT call sys.exit() to allow test imports.
Services should call validate_service_secrets() explicitly at startup
(preferably in a lifespan handler), NOT at module level.
"""

import os
import warnings


class SecretsValidationError(Exception):
    """Raised when required secrets are missing or invalid."""

    pass


def validate_secrets(
    required_vars: list[str], optional_vars: list[str] | None = None, error_on_missing: bool = True
) -> dict[str, str]:
    """
    Validate that required environment variables are present and non-empty.

    Args:
        required_vars: List of required environment variable names
        optional_vars: List of optional environment variable names (warn if missing)
        error_on_missing: If True, raise exception on missing required vars; if False, just warn

    Returns:
        Dictionary of validated environment variables

    Raises:
        SecretsValidationError: If required variables are missing and error_on_missing=True
    """
    if optional_vars is None:
        optional_vars = []

    missing_required = []
    missing_optional = []
    env_values = {}

    # Placeholder values that indicate unconfigured secrets
    _placeholders = {
        "changeme@example.com",
        "CHANGE_THIS_PASSWORD",
        "CHANGE_THIS_TOKEN",
        "CHANGE_THIS_CLIENT_ID",
        "CHANGE_THIS_CLIENT_SECRET",
    }

    # Check required variables
    for var in required_vars:
        value = os.environ.get(var)
        if not value or (value.strip() in _placeholders):
            missing_required.append(var)
        else:
            env_values[var] = value

    # Check optional variables
    for var in optional_vars:
        value = os.environ.get(var)
        if not value:
            missing_optional.append(var)
        else:
            env_values[var] = value

    # Report missing required variables
    if missing_required:
        error_msg = f"Missing required environment variables: {', '.join(missing_required)}"
        if error_on_missing:
            raise SecretsValidationError(error_msg)
        else:
            warnings.warn(f"WARNING: {error_msg}", stacklevel=2)

    # Report missing optional variables
    if missing_optional:
        warnings.warn(
            f"WARNING: Missing optional environment variables: {', '.join(missing_optional)}",
            stacklevel=2,
        )

    return env_values


def validate_service_secrets(service_name: str) -> dict[str, str]:
    """
    Validate secrets for a specific service.

    Args:
        service_name: Name of the service (e.g., 'data_ingestor', 'detector')

    Returns:
        Dictionary of validated environment variables

    Raises:
        SecretsValidationError: If required variables are missing
    """
    # Common required variables for all services
    common_required = ["REDIS_URL"]

    # Service-specific required variables
    service_requirements = {
        "data_ingestor": ["CDSE_USERNAME", "CDSE_PASSWORD"],
        "detector": [],
        "sentinel_preprocessor": [],
        "satellite_monitor": [],
        "aggregator": ["GFW_API_TOKEN"],
        "ground_dashboard": [],
    }

    # Service-specific optional variables
    service_optional = {
        "data_ingestor": ["SENTINEL_HUB_CLIENT_ID", "SENTINEL_HUB_CLIENT_SECRET"],
        "detector": [],
        "sentinel_preprocessor": [],
        "satellite_monitor": ["SENTINEL_HUB_CLIENT_ID", "SENTINEL_HUB_CLIENT_SECRET"],
        "aggregator": [],
        "ground_dashboard": [],
    }

    required = common_required + service_requirements.get(service_name, [])
    optional = service_optional.get(service_name, [])

    print(f"Validating secrets for service: {service_name}")
    return validate_secrets(required, optional)


def validate_database_url() -> str:
    """
    Validate DATABASE_URL environment variable.

    Returns:
        Valid DATABASE_URL value

    Raises:
        SecretsValidationError: If DATABASE_URL is missing or invalid
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SecretsValidationError("DATABASE_URL environment variable is required")

    # Basic validation of database URL format
    if not db_url.startswith(("sqlite:///", "postgresql://", "mysql://", "mongodb://")):
        raise SecretsValidationError(f"Invalid DATABASE_URL format: {db_url}")

    return db_url


def validate_redis_url() -> str:
    """
    Validate REDIS_URL environment variable.

    Returns:
        Valid REDIS_URL value

    Raises:
        SecretsValidationError: If REDIS_URL is missing or invalid
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise SecretsValidationError("REDIS_URL environment variable is required")

    # Basic validation of Redis URL format
    if not redis_url.startswith("redis://"):
        raise SecretsValidationError(f"Invalid REDIS_URL format: {redis_url}")

    return redis_url


if __name__ == "__main__":
    # Test the validator
    try:
        secrets = validate_secrets(["REDIS_URL"], ["OPTIONAL_VAR"])
        print("Secrets validation passed")
        print(f"Validated {len(secrets)} secret entries")
    except SecretsValidationError as e:
        print(f"Secrets validation failed: {e}")
        exit(1)
