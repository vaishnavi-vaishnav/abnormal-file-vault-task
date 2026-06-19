from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction, IntegrityError
from django.db.models import F, Sum
from django.db.models.functions import Lower
from django.utils.dateparse import parse_date
from datetime import datetime, time, timezone as dt_timezone
import hashlib

from .models import File, StoredFile
from .serializers import FileSerializer

# 10 MB max upload size
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.select_related('stored_file').all()
    serializer_class = FileSerializer

    def get_queryset(self):
        """List active files; all query-param filters combine with AND logic."""
        qs = File.objects.select_related('stored_file').filter(is_deleted=False)
        params = self.request.query_params

        search = params.get('search')
        if search:
            qs = qs.filter(original_filename__icontains=search)

        file_type = params.get('file_type')
        if file_type:
            qs = qs.filter(stored_file__file_type=file_type)

        size_min = params.get('size_min')
        if size_min is not None:
            try:
                qs = qs.filter(stored_file__size__gte=int(size_min))
            except (TypeError, ValueError):
                pass

        size_max = params.get('size_max')
        if size_max is not None:
            try:
                qs = qs.filter(stored_file__size__lte=int(size_max))
            except (TypeError, ValueError):
                pass

        date_from = params.get('date_from')
        if date_from:
            parsed = parse_date(date_from)
            if parsed:
                start_of_day = datetime.combine(parsed, time.min, tzinfo=dt_timezone.utc)
                qs = qs.filter(uploaded_at__gte=start_of_day)

        date_to = params.get('date_to')
        if date_to:
            parsed = parse_date(date_to)
            if parsed:
                end_of_day = datetime.combine(parsed, time.max, tzinfo=dt_timezone.utc)
                qs = qs.filter(uploaded_at__lte=end_of_day)

        order = params.get('order', 'desc')
        if order.lower() == 'asc':
            return qs.order_by('uploaded_at')
        return qs.order_by('-uploaded_at')

    def _compute_sha256(self, file_obj):
        """Stream file in chunks to compute SHA-256 without loading entire file into memory."""
        sha256 = hashlib.sha256()
        for chunk in file_obj.chunks():
            sha256.update(chunk)
        return sha256.hexdigest()

    def _create_logical_file(self, stored, original_filename):
        file_entry = File.objects.create(
            stored_file=stored,
            original_filename=original_filename,
        )
        serializer = self.get_serializer(file_entry)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _link_duplicate(self, stored, original_filename):
        StoredFile.objects.filter(pk=stored.pk).update(ref_count=F('ref_count') + 1)
        stored.refresh_from_db()
        return self._create_logical_file(stored, original_filename)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if getattr(file_obj, 'size', 0) > MAX_UPLOAD_SIZE:
            return Response(
                {'error': f'File size exceeds maximum allowed of {MAX_UPLOAD_SIZE} bytes'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_hash = self._compute_sha256(file_obj)

        stored = StoredFile.objects.filter(file_hash=file_hash).first()
        if stored:
            return self._link_duplicate(stored, file_obj.name)

        file_obj.seek(0)
        try:
            with transaction.atomic():
                stored = StoredFile.objects.create(
                    file=file_obj,
                    file_hash=file_hash,
                    file_type=file_obj.content_type or '',
                    size=file_obj.size,
                    ref_count=1,
                )
        except IntegrityError:
            # Concurrent upload of the same new content; link to the winner's StoredFile.
            stored = StoredFile.objects.get(file_hash=file_hash)
            return self._link_duplicate(stored, file_obj.name)

        return self._create_logical_file(stored, file_obj.name)

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
