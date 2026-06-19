from django.db import models
import uuid
import os


def file_upload_path(instance, filename):
    """Generate file path for new file upload"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('uploads', filename)


class StoredFile(models.Model):
    """Actual stored unique file. Multiple logical uploads reference this."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to=file_upload_path)
    file_hash = models.CharField(max_length=128, unique=True, db_index=True)
    file_type = models.CharField(max_length=100)
    size = models.BigIntegerField()
    ref_count = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['file_type']),
            models.Index(fields=['size']),
        ]

    def __str__(self):
        return f"StoredFile {self.id} ({self.size} bytes)"


class File(models.Model):
    """Logical file upload entry that references a StoredFile."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stored_file = models.ForeignKey(StoredFile, on_delete=models.CASCADE, related_name='uploads')
    original_filename = models.CharField(max_length=255)
    is_deleted = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['original_filename']),
            models.Index(fields=['uploaded_at']),
            models.Index(fields=['is_deleted']),
        ]

    def __str__(self):
        return self.original_filename
