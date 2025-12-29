import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

def get_config(key, default=None):
    """Get configuration value from environment variables."""
    return os.getenv(key, default)

def setup_logger(name):
    """Get a logger instance."""
    return logging.getLogger(name)
