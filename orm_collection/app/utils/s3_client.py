import boto3
from app.core.config import settings

def get_s3_client():
    if not settings.ENABLE_S3_STORAGE:
        return None
    return boto3.client(
        's3',
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY
    )

def upload_payload(content_hash: str, payload: str) -> str:
    """
    Uploads a raw payload to S3/MinIO and returns the URI.
    If S3 is disabled or offline, returns None immediately.
    """
    if not settings.ENABLE_S3_STORAGE:
        return None
    try:
        client = get_s3_client()
        if not client:
            return None
        bucket = settings.S3_BUCKET_NAME
        key = f"payloads/{content_hash}.json"
        
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            try:
                client.create_bucket(Bucket=bucket)
            except Exception:
                pass
                
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload.encode('utf-8'),
            ContentType='application/json'
        )
        return f"s3://{bucket}/{key}"
    except Exception as e:
        # Gracefully handle S3 connection errors or unavailability
        import structlog
        structlog.get_logger().warning("s3_upload_failed_offline", error=str(e), content_hash=content_hash)
        return None
