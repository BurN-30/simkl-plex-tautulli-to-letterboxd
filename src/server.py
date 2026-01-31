"""Web server entry point."""

import logging
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config

# Setup logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the web server."""
    # Validate config
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease check your .env file")
        return 1

    # Ensure directories exist
    Config.ensure_directories()
    Path("data").mkdir(exist_ok=True)

    logger.info("=" * 50)
    logger.info("Letterboxd Sync - Web Interface")
    logger.info("=" * 50)
    logger.info(f"Starting server on http://localhost:{Config.WEB_PORT}")
    logger.info(f"Sync interval: {Config.SYNC_INTERVAL} minutes")
    logger.info("=" * 50)

    # Run server
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=Config.WEB_PORT,
        reload=False,
        log_level=Config.LOG_LEVEL.lower(),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
