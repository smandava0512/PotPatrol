"""Private storage adapters. Keys are server-generated, never user paths."""
from pathlib import Path


def safe_key(key):
    path = Path(key)
    if not key or path.is_absolute() or ":" in key or ".." in path.parts or "\\" in key:
        raise ValueError("Invalid storage key")
    return key


class LocalStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        path = (self.root / safe_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put_file(self, key, source, content_type):
        import shutil
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if Path(source).resolve() != target:
            shutil.copyfile(source, target)

    def exists(self, key):
        return self.path(key).is_file()

    def download_file(self, key, target):
        import shutil
        shutil.copyfile(self.path(key), target)

    def read_bytes(self, key):
        return self.path(key).read_bytes()

    def delete_prefix(self, prefix):
        import shutil
        directory = self.path(prefix)
        if directory.is_dir():
            shutil.rmtree(directory)
        if directory.exists():
            raise OSError("Storage prefix still exists")


class S3Store:
    def __init__(self, bucket, prefix="", client=None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if client is None:
            import boto3
            import os
            client = boto3.client("s3", endpoint_url=os.environ.get("POTPATROL_S3_ENDPOINT_URL") or os.environ.get("ROADWATCH_S3_ENDPOINT_URL") or None)
        self.client = client

    def key(self, key):
        return "/".join(part for part in (self.prefix, safe_key(key)) if part)

    def put_file(self, key, source, content_type):
        self.client.upload_file(str(source), self.bucket, self.key(key), ExtraArgs={"ContentType": content_type})

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=self.key(key))
            return True
        except Exception as exc:
            # Only a known not-found response is absence; never silently hide auth/network errors.
            if isinstance(exc, FileNotFoundError) or getattr(exc, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def download_file(self, key, target):
        self.client.download_file(self.bucket, self.key(key), str(target))

    def read_bytes(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=self.key(key))["Body"].read()

    def delete_prefix(self, prefix):
        # The trailing slash is essential: a drive UUID must not match a sibling.
        remote_prefix = self.key(prefix.rstrip("/") + "/")
        previous = None
        while True:
            page = self.client.list_object_versions(Bucket=self.bucket, Prefix=remote_prefix)
            versions = [
                {"Key": item["Key"], "VersionId": item["VersionId"]}
                for kind in ("Versions", "DeleteMarkers") for item in page.get(kind, [])
            ]
            if not versions:
                if page.get("IsTruncated"):
                    raise OSError("Incomplete storage listing")
                return
            if versions == previous:
                raise OSError("Storage deletion made no progress")
            previous = versions
            for start in range(0, len(versions), 1000):
                result = self.client.delete_objects(Bucket=self.bucket, Delete={
                    "Objects": versions[start:start + 1000], "Quiet": True})
                if result.get("Errors"):
                    raise OSError("Storage deletion failed")
            # Re-list, verifying both historical versions and delete markers are gone.
