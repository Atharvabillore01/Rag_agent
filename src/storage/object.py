"""MinIO / S3-compatible object storage wrapper (§2.1)."""

import hashlib
import io
from functools import lru_cache

import boto3
from botocore.config import Config

from src.config import get_settings


class ObjectStore:
    """Thin wrapper around boto3 S3 client pointed at MinIO."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except self._client.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=self._bucket)
            else:
                # 403 Forbidden, 5xx, etc. — re-raise so startup fails loudly
                raise

    def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes and return the storage key."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def upload_fileobj(self, key: str, fileobj: io.IOBase, content_type: str = "application/octet-stream") -> str:
        self._client.upload_fileobj(
            fileobj,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def download(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def download_fileobj(self, key: str, fileobj: io.IOBase) -> None:
        self._client.download_fileobj(self._bucket, key, fileobj)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects under a prefix (used for document cleanup)."""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})

    def presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    # ── Direct-to-storage uploads (client → MinIO, bypassing the API) ──────────

    def presigned_upload_url(self, key: str, content_type: str = "application/octet-stream", expires_in: int = 3600) -> str:
        """Presigned PUT URL for a single-shot direct upload."""
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def create_multipart_upload(self, key: str, content_type: str = "application/octet-stream") -> str:
        resp = self._client.create_multipart_upload(Bucket=self._bucket, Key=key, ContentType=content_type)
        return resp["UploadId"]

    def presigned_upload_part_url(self, key: str, upload_id: str, part_number: int, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "upload_part",
            Params={"Bucket": self._bucket, "Key": key, "UploadId": upload_id, "PartNumber": part_number},
            ExpiresIn=expires_in,
        )

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[dict]) -> str:
        """parts: [{"PartNumber": int, "ETag": str}]. Returns the final object ETag."""
        norm = sorted(
            ({"PartNumber": int(p["PartNumber"]), "ETag": p["ETag"]} for p in parts),
            key=lambda p: p["PartNumber"],
        )
        resp = self._client.complete_multipart_upload(
            Bucket=self._bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": norm}
        )
        return (resp.get("ETag") or "").strip('"')

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        self._client.abort_multipart_upload(Bucket=self._bucket, Key=key, UploadId=upload_id)

    def head_object(self, key: str) -> dict:
        """Return {'size', 'etag', 'content_type'} — raises ClientError if absent."""
        resp = self._client.head_object(Bucket=self._bucket, Key=key)
        return {
            "size": resp["ContentLength"],
            "etag": (resp.get("ETag") or "").strip('"'),
            "content_type": resp.get("ContentType"),
        }

    def read_range(self, key: str, length: int) -> bytes:
        """Read the first `length` bytes of an object (for content sniffing)."""
        resp = self._client.get_object(Bucket=self._bucket, Key=key, Range=f"bytes=0-{max(0, length - 1)}")
        return resp["Body"].read()

    @staticmethod
    def document_key(tenant_id: str, document_id: str, filename: str) -> str:
        return f"raw/{tenant_id}/{document_id}/{filename}"

    @staticmethod
    def artifact_key(tenant_id: str, document_id: str, stage: str, version: int) -> str:
        return f"artifacts/{tenant_id}/{document_id}/v{version}/{stage}"


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    s = get_settings()
    store = ObjectStore(
        endpoint_url=s.s3_endpoint_url,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key,
        bucket=s.s3_bucket_name,
        region=s.s3_region,
    )
    return store
