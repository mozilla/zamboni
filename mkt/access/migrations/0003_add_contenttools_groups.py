from django.db import migrations


def create_addon_groups(apps, schema_editor):
    Group = apps.get_model('access', 'Group')
    Group.objects.create(name='Content Tools: Add-on Submitters',
                         rules='ContentTools:Login,ContentTools:AddonSubmit')
    Group.objects.create(name='Content Tools: Add-on Reviewers',
                         rules='ContentTools:Login,ContentTools:AddonReview')


class Migration(migrations.Migration):
    dependencies = [
        ('access', '0001_initial'),
        ('access', '0002_auto_20150825_1715'),
        ('access', '0002_group_restricted'),
    ]
    operations = [
        migrations.RunPython(create_addon_groups),
    ]
