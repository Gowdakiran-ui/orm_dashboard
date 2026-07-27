import boto3
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class S3Client:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY
        )
        self.bucket = settings.S3_BUCKET_NAME
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            logger.info(f"Bucket {self.bucket} does not exist. Creating it.")
            self.s3.create_bucket(Bucket=self.bucket)

    def upload_raw_payload(self, object_name: str, data: str) -> str:
        """Uploads raw string/json data to S3 and returns the path/URI."""
        try:
            self.s3.put_object(Bucket=self.bucket, Key=object_name, Body=data)
            return f"s3://{self.bucket}/{object_name}"
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise

s3_client = S3Client()
