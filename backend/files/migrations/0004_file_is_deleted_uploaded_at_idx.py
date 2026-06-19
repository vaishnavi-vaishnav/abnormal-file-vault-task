from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0003_add_search_indexes'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='file',
            index=models.Index(
                fields=['is_deleted', 'uploaded_at'],
                name='files_file_is_dele_upload_idx',
            ),
        ),
    ]
