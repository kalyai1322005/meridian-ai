"""Test setup: fake config so tests run without AWS, a Gemini key or the internet."""
import os
import sys
import tempfile

# Make `import api`, `import rag`, ... work when pytest is run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Environment variables win over .env, so a developer's real .env never leaks into tests
os.environ["APP_MODE"] = "local"
os.environ["LOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="meridian-test-")
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["S3_BUCKET_NAME"] = ""
os.environ["S3_PREFIX"] = "uploads/"
os.environ["OPENSEARCH_URL"] = ""
os.environ["OPENSEARCH_INDEX"] = "meridian-docs"
