import hashlib
import os

from django.conf import settings
from django.core.files import File as DjangoFile
from django.db import connection, models, transaction

from .models import StoredFile


LEGACY_TABLE_NAME = 'files_file'


def compute_sha256(path):
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def convert_legacy_file_uploads():
    """Convert legacy file uploads from a legacy files_file table.

    This helper inspects the current database and converts rows that still
    rely on legacy file metadata into StoredFile-backed records.
    """
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names()
        if LEGACY_TABLE_NAME not in tables:
            return {
                'status': 'no_table',
                'message': f'Legacy table {LEGACY_TABLE_NAME} not found.',
                'converted': 0,
            }

        cursor.execute("PRAGMA table_info('%s')" % LEGACY_TABLE_NAME)
        columns = [row[1] for row in cursor.fetchall()]

        if 'stored_file_id' not in columns:
            return {
                'status': 'missing_column',
                'message': 'The legacy table does not contain stored_file_id. Run schema migrations first.',
                'converted': 0,
            }

        if 'file' not in columns:
            return {
                'status': 'no_legacy_columns',
                'message': 'No legacy file column found in table. Nothing to convert.',
                'converted': 0,
            }

        cursor.execute(
            f"SELECT id, original_filename, file, file_type, size, stored_file_id FROM {LEGACY_TABLE_NAME}"
        )
        rows = cursor.fetchall()

    converted = 0
    errors = []

    with transaction.atomic():
        for row in rows:
            row_id, original_filename, file_path, file_type, size, stored_file_id = row
            if stored_file_id is not None:
                continue
            if not file_path:
                errors.append((row_id, 'Missing legacy file path'))
                continue

            if os.path.isabs(file_path):
                absolute_path = file_path
            else:
                absolute_path = os.path.join(settings.MEDIA_ROOT, file_path)

            if not os.path.exists(absolute_path):
                errors.append((row_id, f'File not found: {absolute_path}'))
                continue

            file_hash = compute_sha256(absolute_path)
            defaults = {
                'file_type': file_type or '',
                'size': size or os.path.getsize(absolute_path),
            }
            with open(absolute_path, 'rb') as opened_file:
                defaults['file'] = DjangoFile(opened_file, name=os.path.basename(absolute_path))
                stored, created = StoredFile.objects.get_or_create(
                    file_hash=file_hash,
                    defaults=defaults,
                )

            if not created:
                stored.ref_count = models.F('ref_count') + 1
                stored.save()
                stored.refresh_from_db()

            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {LEGACY_TABLE_NAME} SET stored_file_id = ? WHERE id = ?",
                    [str(stored.id), str(row_id)],
                )
            converted += 1

    return {
        'status': 'converted',
        'converted': converted,
        'errors': errors,
    }
