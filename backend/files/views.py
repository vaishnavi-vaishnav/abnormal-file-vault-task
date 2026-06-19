from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.db import models
from django.db.models import F, Sum
from django.utils.dateparse import parse_date
from datetime import datetime, time, timezone as dt_timezone
import hashlib

from .models import File, StoredFile
from .serializers import FileSerializer, StoredFileSerializer
from django.db.models.functions import Lower

# 10 MB max upload size
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.select_related('stored_file').all()
    serializer_class = FileSerializer

    def get_queryset(self):
        qs = File.objects.select_related('stored_file').filter(is_deleted=False)

        # Search by original filename
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(original_filename__icontains=search)

        # Filter by file type (stored_file.file_type)
        file_type = self.request.query_params.get('file_type')
        if file_type:
            qs = qs.filter(stored_file__file_type__iexact=file_type)

        # Size range (bytes)
        size_min = self.request.query_params.get('size_min')
        size_max = self.request.query_params.get('size_max')
        if size_min:
            try:
                qs = qs.filter(stored_file__size__gte=int(size_min))
            except ValueError:
                pass
        if size_max:
            try:
                qs = qs.filter(stored_file__size__lte=int(size_max))
            except ValueError:
                pass

        # Upload date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            try:
                qs = qs.filter(uploaded_at__gte=date_from)
            except Exception:
                pass
        if date_to:
            parsed = parse_date(date_to)
            if parsed:
                end_of_day = datetime.combine(parsed, time.max, tzinfo=dt_timezone.utc)
                qs = qs.filter(uploaded_at__lte=end_of_day)

        # Sorting by upload date: `order=asc` or `order=desc` (default desc)
        order = self.request.query_params.get('order')
        if order and order.lower() == 'asc':
            qs = qs.order_by('uploaded_at')
        else:
            # default to newest first
            qs = qs.order_by('-uploaded_at')

        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce maximum file size
        if getattr(file_obj, 'size', 0) > MAX_UPLOAD_SIZE:
            return Response(
                {'error': f'File size exceeds maximum allowed of {MAX_UPLOAD_SIZE} bytes'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compute SHA256 hash streaming to avoid large memory use
        sha256 = hashlib.sha256()
        for chunk in file_obj.chunks():
            sha256.update(chunk)
        file_hash = sha256.hexdigest()

        # Check for existing stored file
        try:
            stored = StoredFile.objects.get(file_hash=file_hash)
            # Existing file: increment ref_count and create logical File pointing to it
            stored.ref_count = models.F('ref_count') + 1
            stored.save()
            # Refresh to get actual integer value
            stored.refresh_from_db()
            file_entry = File.objects.create(
                stored_file=stored,
                original_filename=file_obj.name,
            )
            serializer = self.get_serializer(file_entry)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except StoredFile.DoesNotExist:
            # New unique file: save StoredFile (must reset file pointer)
            # Django's InMemoryUploadedFile/TemporaryUploadedFile will be re-used; ensure pointer at 0
            try:
                file_obj.open()
            except Exception:
                pass
            # Create stored file record
            stored = StoredFile.objects.create(
                file=file_obj,
                file_hash=file_hash,
                file_type=file_obj.content_type or '',
                size=file_obj.size,
                ref_count=1,
            )
            file_entry = File.objects.create(
                stored_file=stored,
                original_filename=file_obj.name,
            )
            serializer = self.get_serializer(file_entry)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    # (get_queryset implemented above with filters and is_deleted exclusion)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Soft-delete a logical File (set is_deleted=True); decrement StoredFile.ref_count and remove the stored file when no refs remain."""
        instance = self.get_object()
        stored = instance.stored_file

        # Soft-delete logical entry
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])

        # Decrement ref_count atomically
        StoredFile.objects.filter(pk=stored.pk).update(ref_count=F('ref_count') - 1)
        stored.refresh_from_db()

        # If no more references, delete the physical file and the StoredFile record
        try:
            if stored.ref_count <= 0:
                try:
                    stored.file.delete(save=False)
                except Exception:
                    pass
                stored.delete()
        except StoredFile.DoesNotExist:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Return storage summary: logical vs actual and savings."""
        agg = StoredFile.objects.aggregate(
            total_actual=Sum('size'),
            total_logical=Sum(F('size') * F('ref_count')),
        )
        total_actual = agg['total_actual'] or 0
        total_logical = agg['total_logical'] or 0
        return Response({
            'total_actual_bytes': total_actual,
            'total_logical_bytes': total_logical,
            'savings_bytes': total_logical - total_actual,
        })

    @action(detail=False, methods=['get'])
    def file_types(self, request):
        """Return distinct file types available in StoredFile."""
        types_qs = (
            StoredFile.objects
            .exclude(file_type__isnull=True)
            .exclude(file_type='')
            .annotate(ft=Lower('file_type'))
            .values_list('ft', flat=True)
            .distinct()
            .order_by('ft')
        )
        return Response({'file_types': list(types_qs)})
