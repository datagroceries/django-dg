# Pages and folders (G-62), a page's slug as the end of its address only (G-64): 0002 to 0005 of the
# evening they were made, squashed. Where those ran, this counts as run (`replaces`).

from django.db import migrations, models


def folders(apps, schema_editor):
    """The pages that have pages under them are folders."""
    Page = apps.get_model('dg_wiki', 'Page')
    Page.objects.filter(children__isnull=False).update(folder=True)


class Migration(migrations.Migration):
    replaces = [
        ('dg_wiki', '0002_page_or_folder'),
        ('dg_wiki', '0003_path_holds_the_slug'),
        ('dg_wiki', '0004_top_text'),
        ('dg_wiki', '0005_no_top_text'),
    ]

    dependencies = [
        ('dg_wiki', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpage',
            name='folder',
            field=models.BooleanField(
                default=False, help_text='A folder of pages, its text their index.', verbose_name='folder'
            ),
        ),
        migrations.AddField(
            model_name='page',
            name='folder',
            field=models.BooleanField(
                default=False, help_text='A folder of pages, its text their index.', verbose_name='folder'
            ),
        ),
        migrations.RunPython(folders, migrations.RunPython.noop),
        migrations.RemoveField(model_name='historicalpage', name='slug'),
        migrations.RemoveField(model_name='page', name='slug'),
    ]
