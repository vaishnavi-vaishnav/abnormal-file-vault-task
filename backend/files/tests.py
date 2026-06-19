import hashlib
import os
from datetime import datetime, timezone as dt_timezone

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import File, StoredFile

TEST_MEDIA_ROOT = '/tmp/abnormal_file_vault_test_media'


def make_upload(name: str, content: bytes, content_type: str = 'text/plain') -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FileVaultAPITests(APITestCase):
    """API tests for deduplication, reference counting, search/filter, and storage summary."""

    def setUp(self):
        self.upload_url = reverse('file-list')
        self.list_url = reverse('file-list')
        self.summary_url = reverse('file-summary')

    def _upload(self, name: str, content: bytes, content_type: str = 'text/plain'):
        return self.client.post(
            self.upload_url,
            {'file': make_upload(name, content, content_type)},
            format='multipart',
        )

    def test_unique_upload_creates_stored_file_with_ref_count_one(self):
        content = b'unique content alpha'
        response = self._upload('alpha.txt', content)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StoredFile.objects.count(), 1)
        self.assertEqual(File.objects.filter(is_deleted=False).count(), 1)

        stored = StoredFile.objects.get()
        self.assertEqual(stored.ref_count, 1)
        self.assertEqual(stored.size, len(content))
        self.assertEqual(stored.file_hash, hashlib.sha256(content).hexdigest())
        self.assertTrue(os.path.isfile(stored.file.path))

    def test_duplicate_upload_reuses_stored_file_and_increments_ref_count(self):
        content = b'shared duplicate content'
        r1 = self._upload('first.txt', content)
        r2 = self._upload('second.txt', content)

        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StoredFile.objects.count(), 1)

        stored = StoredFile.objects.get()
        self.assertEqual(stored.ref_count, 2)
        self.assertEqual(r1.data['stored_file']['id'], r2.data['stored_file']['id'])
        self.assertEqual(File.objects.filter(is_deleted=False).count(), 2)
        self.assertNotEqual(r1.data['id'], r2.data['id'])
        self.assertEqual(r1.data['original_filename'], 'first.txt')
        self.assertEqual(r2.data['original_filename'], 'second.txt')

    def test_deleting_one_reference_keeps_physical_file(self):
        content = b'delete ref count test payload'
        r1 = self._upload('keep.txt', content)
        r2 = self._upload('also.txt', content)
        file_id = r1.data['id']
        stored_id = r1.data['stored_file']['id']
        stored = StoredFile.objects.get(pk=stored_id)
        physical_path = stored.file.path
        self.assertTrue(os.path.isfile(physical_path))

        response = self.client.delete(reverse('file-detail', args=[file_id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(StoredFile.objects.filter(pk=stored_id).exists())
        self.assertEqual(StoredFile.objects.get(pk=stored_id).ref_count, 1)
        self.assertEqual(File.objects.filter(is_deleted=False).count(), 1)
        self.assertTrue(os.path.isfile(physical_path))

    def test_deleting_last_reference_removes_stored_file(self):
        content = b'only reference payload'
        r1 = self._upload('only.txt', content)
        file_id = r1.data['id']
        stored_id = r1.data['stored_file']['id']
        physical_path = StoredFile.objects.get(pk=stored_id).file.path
        self.assertTrue(os.path.isfile(physical_path))

        response = self.client.delete(reverse('file-detail', args=[file_id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StoredFile.objects.filter(pk=stored_id).exists())
        self.assertEqual(File.objects.filter(is_deleted=False).count(), 0)
        self.assertFalse(os.path.isfile(physical_path))

    def test_search_and_combined_filters_return_correct_results(self):
        self._upload('report_q1.pdf', b'pdf content', 'application/pdf')
        self._upload('notes.txt', b'text content', 'text/plain')
        self._upload('report_q2.pdf', b'pdf content', 'application/pdf')

        search_response = self.client.get(self.list_url, {'search': 'report'})
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        search_names = {f['original_filename'] for f in search_response.data}
        self.assertEqual(search_names, {'report_q1.pdf', 'report_q2.pdf'})

        type_response = self.client.get(self.list_url, {'file_type': 'text/plain'})
        self.assertEqual(type_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(type_response.data), 1)
        self.assertEqual(type_response.data[0]['original_filename'], 'notes.txt')

        combined_response = self.client.get(self.list_url, {
            'search': 'report',
            'file_type': 'application/pdf',
        })
        self.assertEqual(combined_response.status_code, status.HTTP_200_OK)
        combined_names = {f['original_filename'] for f in combined_response.data}
        self.assertEqual(combined_names, {'report_q1.pdf', 'report_q2.pdf'})

        File.objects.filter(original_filename='notes.txt').update(
            uploaded_at=datetime(2025, 1, 15, 12, 0, tzinfo=dt_timezone.utc),
        )
        File.objects.filter(original_filename__startswith='report').update(
            uploaded_at=datetime(2025, 2, 10, 12, 0, tzinfo=dt_timezone.utc),
        )
        date_response = self.client.get(self.list_url, {
            'date_from': '2025-02-01',
            'date_to': '2025-02-28',
            'size_min': '10',
            'size_max': '20',
        })
        self.assertEqual(date_response.status_code, status.HTTP_200_OK)
        date_names = {f['original_filename'] for f in date_response.data}
        self.assertEqual(date_names, {'report_q1.pdf', 'report_q2.pdf'})

    def test_summary_reports_correct_savings_after_dedup(self):
        content = b'summary test content'
        self._upload('one.txt', content)
        self._upload('two.txt', content)

        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        size = len(content)
        self.assertEqual(response.data['total_actual_bytes'], size)
        self.assertEqual(response.data['total_logical_bytes'], size * 2)
        self.assertEqual(response.data['savings_bytes'], size)
