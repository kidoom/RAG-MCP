"""Observability module for logging and tracing.

This module provides centralized logging configuration and utilities.
"""

import logging
import sys
from typing import Optional

_logger: Optional[logging.Logger] = None


def get_logger(name: str = "modular_rag_mcp") -> logging.Logger:
    """Get or create the main application logger.

    Args:
        name: Logger name (default: "modular_rag_mcp")

    Returns:
        Configured logger instance
    """
    global _logger

    if _logger is None:
        _logger = logging.getLogger(name)
        
        # Configure basic stderr output
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)

    return _logger


def set_log_level(level: str) -> None:
    """Set the log level for the main logger.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger = get_logger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
