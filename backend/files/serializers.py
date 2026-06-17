from rest_framework import serializers
from .models import File, StoredFile


class StoredFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoredFile
        fields = ['id', 'file', 'file_hash', 'file_type', 'size', 'ref_count', 'created_at']
        read_only_fields = ['id', 'file_hash', 'ref_count', 'created_at']


class FileSerializer(serializers.ModelSerializer):
    stored_file = StoredFileSerializer(read_only=True)
    file = serializers.SerializerMethodField()
    file_type = serializers.CharField(source='stored_file.file_type', read_only=True)
    size = serializers.IntegerField(source='stored_file.size', read_only=True)

    class Meta:
        model = File
        fields = ['id', 'file', 'stored_file', 'original_filename', 'file_type', 'size', 'uploaded_at', 'is_deleted']
        read_only_fields = ['id', 'uploaded_at', 'is_deleted']

    def get_file(self, obj):
        """Return an absolute URL to the stored file so frontend can download it."""
        stored = getattr(obj, 'stored_file', None)
        if not stored or not stored.file:
            return ''
        request = self.context.get('request') if hasattr(self, 'context') else None
        try:
            url = stored.file.url
        except Exception:
            # fallback to file path/name
            url = str(stored.file)
        if request:
            return request.build_absolute_uri(url)
        return url