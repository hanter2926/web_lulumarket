from django.db import migrations, models
import django.core.validators

class Migration(migrations.Migration):

    dependencies = [
        ('vip', '0003_sitesettings_category_description_category_icon_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Slider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=200)),
                ('subtitle', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='sliders/')),
                ('button_text', models.CharField(blank=True, max_length=80)),
                ('button_url', models.URLField(blank=True)),
                ('width', models.CharField(default='100%', max_length=10, validators=[django.core.validators.RegexValidator('^(auto|\\d+(px|%))$', 'Enter a valid size like "100%", "450px" or "auto"')])),
                ('height', models.CharField(default='450px', max_length=10, validators=[django.core.validators.RegexValidator('^(auto|\\d+(px|%))$', 'Enter a valid size like "100%", "450px" or "auto"')])),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('auto_slide_seconds', models.PositiveIntegerField(default=5, help_text='Seconds before auto-advancing to next slide')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['display_order', '-created_at'],
                'verbose_name': 'Slider',
                'verbose_name_plural': 'Sliders',
            },
        ),
    ]
