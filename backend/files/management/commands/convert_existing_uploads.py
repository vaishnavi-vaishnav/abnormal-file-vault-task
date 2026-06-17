from django.core.management.base import BaseCommand

from files.utils import convert_legacy_file_uploads


class Command(BaseCommand):
    help = "Convert legacy file upload records into StoredFile-backed records."

    def handle(self, *args, **options):
        result = convert_legacy_file_uploads()
        status = result.get('status')

        if status == 'no_table':
            self.stdout.write(self.style.WARNING(result.get('message')))
            return

        if status == 'missing_column':
            self.stdout.write(self.style.ERROR(result.get('message')))
            return

        if status == 'no_legacy_columns':
            self.stdout.write(self.style.SUCCESS(result.get('message')))
            return

        converted = result.get('converted', 0)
        self.stdout.write(self.style.SUCCESS(f'Converted {converted} legacy upload(s) into StoredFile references.'))
        errors = result.get('errors', [])
        if errors:
            self.stdout.write(self.style.WARNING('Some rows could not be converted:'))
            for row_id, message in errors:
                self.stdout.write(f' - id={row_id}: {message}')
