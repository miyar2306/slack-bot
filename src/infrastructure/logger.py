import logging
import sys

def setup_logger(name=None, level=logging.INFO):
    """
    Configure and return a logger instance
    
    Args:
        name: Logger name (default: root logger)
        level: Logging level (default: INFO)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set level
    logger.setLevel(level)
    
    # Create handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
    
    return logger
