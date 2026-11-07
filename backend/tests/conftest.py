"""Test setup: fake config so the tests run without AWS, a Gemini key or the internet."""
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
# Empty on purpose: nothing may try to reach S3
os.environ["S3_BUCKET_NAME"] = ""
os.environ["S3_PREFIX"] = "uploads/"
os.environ["S3_VECTORS_BUCKET_NAME"] = ""
# Fake credentials so boto3 can build clients in tests; moto/fakes answer every call, never real AWS
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
