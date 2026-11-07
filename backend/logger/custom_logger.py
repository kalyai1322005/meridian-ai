import os
import atexit
import logging
from datetime import datetime
import structlog

from config.settings import settings

def add_severity(logger, method_name, event_dict):
    """Copy the log level into a field called "severity".

    Many log tools read a "severity" field from JSON log lines to colour and filter them.
    Our own "level" field is kept too, so nothing that reads "level" breaks. (On AWS the
    container's output goes to CloudWatch Logs automatically.)
    """
    level = event_dict.get("level")
    if level:
        event_dict["severity"] = level.upper()
    return event_dict


class CustomLogger:
    def __init__(self, log_dir="logs"):
        # Ensure logs directory exists
        self.logs_dir = os.path.join(os.getcwd(), log_dir)
        os.makedirs(self.logs_dir, exist_ok=True)

        # Timestamped log file (for persistence)
        self._timestamp = datetime.now().strftime('%m_%d_%Y_%H_%M_%S')
        log_file = f"{self._timestamp}.log"
        self.log_file_path = os.path.join(self.logs_dir, log_file)

        self._s3_flushed = False

        # Register atexit to auto-flush logs to S3 on shutdown
        atexit.register(self.flush_to_s3)

    def get_logger(self, name=__file__):
        logger_name = os.path.basename(name)

        # Configure logging for console + file (both JSON)
        file_handler = logging.FileHandler(self.log_file_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON lines

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(message)s"))

        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",  # Structlog will handle JSON rendering
            handlers=[console_handler, file_handler]
        )

        # Configure structlog for JSON structured logging
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
                structlog.processors.add_log_level,
                add_severity,
                structlog.processors.format_exc_info,  # log.exception(...) -> readable traceback field
                structlog.processors.EventRenamer(to="event"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        return structlog.get_logger(logger_name)

    def flush_to_s3(self):
        """Cloud mode only: upload the current log file to S3. Safe to call multiple times."""
        if self._s3_flushed:
            return

        # Local mode: the log file in ./logs is enough, never touch AWS
        if not settings.is_cloud:
            return

        s3_bucket = settings.S3_BUCKET_NAME

        if not s3_bucket:
            print("[Logger] S3_BUCKET_NAME not set — skipping S3 log upload.")
            return

        if not os.path.exists(self.log_file_path):
            print("[Logger] Log file not found — skipping S3 log upload.")
            return

        try:
            import boto3  # only needed (and imported) in cloud mode

            key = f"logs/{self._timestamp}.log"
            boto3.client("s3", region_name=settings.AWS_REGION).upload_file(
                self.log_file_path, s3_bucket, key, ExtraArgs={"ContentType": "text/plain"}
            )

            self._s3_flushed = True
            print(f"[Logger] Logs uploaded to s3://{s3_bucket}/{key}")
        except Exception as e:
            # Use print here intentionally — the structlog logger may not be
            # available during shutdown, and we don't want to lose this error
            print(f"[Logger] Failed to upload logs to S3: {e}")
