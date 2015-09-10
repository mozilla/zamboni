from django.db import migrations


def create_addon_groups(apps, schema_editor):
    Group = apps.get_model('Access', 'Group')
    Group.objects.create(name='Content Tools: Add-on Submitters',
                         rules='ContentTools:Login,ContentTools:AddonSubmit')
    Group.objects.create(name='Content Tools: Add-on Reviewers',
                         rules='ContentTools:Login,ContentTools:AddonReview')


class Migration(migrations.Migration):
    dependencies = []
    operations = [
        migrations.RunPython(create_addon_groups),
    ]
