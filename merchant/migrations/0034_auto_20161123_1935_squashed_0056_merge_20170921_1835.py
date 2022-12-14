# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-04 12:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.migrations.operations.special
import django.db.models.deletion
import location_field.models.plain
import merchant.models.merchant
import radaro_utils.models


# Functions from the following migrations need manual copying.
# Move them and any dependencies into this file, then update the
# RunPython operations to refer to the local versions:
# merchant.migrations.0040_auto_20170221_1934
# merchant.migrations.0046_auto_20170512_2239
import radaro_utils.files.utils


class Migration(migrations.Migration):

    replaces = [('merchant', '0034_auto_20161123_1935'), ('merchant', '0035_merchant_webhook_url'), ('merchant', '0036_merchant_enable_job_description'), ('merchant', '0037_auto_20170126_0048'), ('merchant', '0038_auto_20170206_2202'), ('merchant', '0039_merchant_webhook_verification_token'), ('merchant', '0040_auto_20170221_1934'), ('merchant', '0041_merchant_driver_jobs_ordering'), ('merchant', '0042_subbranding_store_url'), ('merchant', '0036_merchant_path_processing'), ('merchant', '0039_merge_20170216_2216'), ('merchant', '0042_merge'), ('merchant', '0043_merge'), ('merchant', '0044_auto_20170414_1640'), ('merchant', '0045_merchant_push_notifications_settings'), ('merchant', '0042_merchant_checklist'), ('merchant', '0046_merge_20170506_2348'), ('merchant', '0045_auto_20170429_1654'), ('merchant', '0046_auto_20170512_2301'), ('merchant', '0047_merge_20170523_1918'), ('merchant', '0048_auto_20170526_2019'), ('merchant', '0049_auto_20170605_2332'), ('merchant', '0050_hub_status'), ('merchant', '0049_auto_20170602_2229'), ('merchant', '0050_auto_20170609_0059'), ('merchant', '0051_merge_20170620_0059'), ('merchant', '0052_auto_20170628_1815'), ('merchant', '0053_auto_20170703_0407'), ('merchant', '0054_auto_20170707_1824'), ('merchant', '0055_merchant_use_way_back_status'), ('merchant', '0046_auto_20170512_2239'), ('merchant', '0052_merge_20170728_2156'), ('merchant', '0053_auto_20170809_1714'), ('merchant', '0054_auto_20170904_1527'), ('merchant', '0055_auto_20170906_1922'), ('merchant', '0056_merge_20170921_1835')]

    dependencies = [
        ('merchant_extension', '0001_initial'),
        ('merchant', '0001_squashed_0033_auto_20161117_2327'),
        ('notification', '0010_auto_20170331_2132'),
    ]

    operations = [
        migrations.RenameField(
            model_name='merchant',
            old_name='allow_confirmation',
            new_name='enable_delivery_confirmation',
        ),
        migrations.AddField(
            model_name='merchant',
            name='webhook_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='merchant',
            name='enable_job_description',
            field=models.BooleanField(default=False, help_text='This setting enables additional markdown descriptions for jobs.', verbose_name='Rich text job descriptions enabled'),
        ),
        migrations.CreateModel(
            name='SubBranding',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('logo', models.ImageField(null=True, upload_to=radaro_utils.files.utils.get_upload_path)),
            ],
            options={
                'ordering': ('title',),
                'verbose_name': 'Sub-branding Merchant',
                'verbose_name_plural': 'Sub-branding Merchants',
            },
            bases=(radaro_utils.models.ResizeImageMixin, models.Model),
        ),
        migrations.AddField(
            model_name='merchant',
            name='use_subbranding',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='subbranding',
            name='merchant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subbrandings', to='merchant.Merchant'),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='geofence_settings',
            field=models.IntegerField(choices=[(0, 'Complete ONLY on Driver Input'), (1, 'Complete upon ENTER or Driver Input'), (2, 'Complete upon EXIT or Driver Input')], default=0),
        ),
        migrations.AddField(
            model_name='merchant',
            name='webhook_verification_token',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='webhook_verification_token',
            field=models.CharField(default=merchant.models.merchant.generate_webhook_verification_token, max_length=255),
        ),
        migrations.AddField(
            model_name='merchant',
            name='driver_jobs_ordering',
            field=models.CharField(choices=[('time', 'By time'), ('distance', 'By distance')], default='distance', max_length=255, verbose_name='Ordering of jobs for drivers'),
        ),
        migrations.AddField(
            model_name='subbranding',
            name='store_url',
            field=models.URLField(default='http://www.example.com/', verbose_name='Custom ???URL??? redirect link'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='path_processing',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='MerchantGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('webhook_verification_token', models.CharField(default=merchant.models.merchant.generate_webhook_verification_token, max_length=255)),
                ('webhook_url', models.URLField()),
            ],
        ),
        migrations.AddField(
            model_name='merchant',
            name='merchant_group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='merchant.MerchantGroup'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='push_notifications_settings',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='notification.PushNotificationsSettings'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='checklist',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='merchant_extension.Checklist'),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='country',
            field=models.CharField(choices=[('BY', 'Belarus'), ('AU', 'Australia'), ('G', 'United Kingdom'), ('US', 'USA'), ('AE', 'United Arab Emirates'), ('SG', 'Singapore')], default='AU', max_length=20),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='country',
            field=models.CharField(choices=[('BY', 'Belarus'), ('AU', 'Australia'), ('G', 'United Kingdom'), ('US', 'USA'), ('AE', 'United Arab Emirates'), ('SG', 'Singapore'), ('NZ', 'New Zealand')], default='AU', max_length=20),
        ),
        migrations.CreateModel(
            name='Hub',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('phone', models.CharField(max_length=40, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='HubLocation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(blank=True, max_length=255)),
                ('location', location_field.models.plain.PlainLocationField(default=None, max_length=63)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('description', models.CharField(blank=True, max_length=150)),
            ],
            options={
                'ordering': ('created_at',),
            },
        ),
        migrations.AddField(
            model_name='hub',
            name='location',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='merchant.HubLocation'),
        ),
        migrations.AddField(
            model_name='hub',
            name='merchant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='merchant.Merchant'),
        ),
        migrations.AddField(
            model_name='hub',
            name='status',
            field=models.CharField(choices=[('open', 'open'), ('closed', 'closed')], default='open', max_length=64),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='country',
            field=models.CharField(choices=[('AD', 'Andorra'), ('AE', 'United Arab Emirates'), ('AF', 'Afghanistan'), ('AG', 'Antigua & Barbuda'), ('AI', 'Anguilla'), ('AL', 'Albania'), ('AM', 'Armenia'), ('AO', 'Angola'), ('AQ', 'Antarctica'), ('AR', 'Argentina'), ('AS', 'Samoa (American)'), ('AT', 'Austria'), ('AU', 'Australia'), ('AW', 'Aruba'), ('AX', '\xc3\x85land Islands'), ('AZ', 'Azerbaijan'), ('BA', 'Bosnia & Herzegovina'), ('B', 'Barbados'), ('BD', 'Bangladesh'), ('BE', 'Belgium'), ('BF', 'Burkina Faso'), ('BG', 'Bulgaria'), ('BH', 'Bahrain'), ('BI', 'Burundi'), ('BJ', 'Benin'), ('BL', 'St Barthelemy'), ('BM', 'Bermuda'), ('BN', 'Brunei'), ('BO', 'Bolivia'), ('BQ', 'Caribbean NL'), ('BR', 'Brazil'), ('BS', 'Bahamas'), ('BT', 'Bhutan'), ('BV', 'Bouvet Island'), ('BW', 'Botswana'), ('BY', 'Belarus'), ('BZ', 'Belize'), ('CA', 'Canada'), ('CC', 'Cocos (Keeling) Islands'), ('CD', 'Congo (Dem. Rep.)'), ('CF', 'Central African Rep.'), ('CG', 'Congo (Rep.)'), ('CH', 'Switzerland'), ('CI', "C\xc3\xb4te d'Ivoire"), ('CK', 'Cook Islands'), ('CL', 'Chile'), ('CM', 'Cameroon'), ('CN', 'China'), ('CO', 'Colombia'), ('CR', 'Costa Rica'), ('CU', 'Cuba'), ('CV', 'Cape Verde'), ('CW', 'Cura\xc3\xa7ao'), ('CX', 'Christmas Island'), ('CY', 'Cyprus'), ('CZ', 'Czech Republic'), ('DE', 'Germany'), ('DJ', 'Djibouti'), ('DK', 'Denmark'), ('DM', 'Dominica'), ('DO', 'Dominican Republic'), ('DZ', 'Algeria'), ('EC', 'Ecuador'), ('EE', 'Estonia'), ('EG', 'Egypt'), ('EH', 'Western Sahara'), ('ER', 'Eritrea'), ('ES', 'Spain'), ('ET', 'Ethiopia'), ('FI', 'Finland'), ('FJ', 'Fiji'), ('FK', 'Falkland Islands'), ('FM', 'Micronesia'), ('FO', 'Faroe Islands'), ('FR', 'France'), ('GA', 'Gabon'), ('G', 'United Kingdom'), ('GD', 'Grenada'), ('GE', 'Georgia'), ('GF', 'French Guiana'), ('GG', 'Guernsey'), ('GH', 'Ghana'), ('GI', 'Gibraltar'), ('GL', 'Greenland'), ('GM', 'Gambia'), ('GN', 'Guinea'), ('GP', 'Guadeloupe'), ('GQ', 'Equatorial Guinea'), ('GR', 'Greece'), ('GS', 'South Georgia & the South Sandwich Islands'), ('GT', 'Guatemala'), ('GU', 'Guam'), ('GW', 'Guinea-Bissau'), ('GY', 'Guyana'), ('HK', 'Hong Kong'), ('HM', 'Heard Island & McDonald Islands'), ('HN', 'Honduras'), ('HR', 'Croatia'), ('HT', 'Haiti'), ('HU', 'Hungary'), ('ID', 'Indonesia'), ('IE', 'Ireland'), ('IL', 'Israel'), ('IM', 'Isle of Man'), ('IN', 'India'), ('IO', 'British Indian Ocean Territory'), ('IQ', 'Iraq'), ('IR', 'Iran'), ('IS', 'Iceland'), ('IT', 'Italy'), ('JE', 'Jersey'), ('JM', 'Jamaica'), ('JO', 'Jordan'), ('JP', 'Japan'), ('KE', 'Kenya'), ('KG', 'Kyrgyzstan'), ('KH', 'Cambodia'), ('KI', 'Kiribati'), ('KM', 'Comoros'), ('KN', 'St Kitts & Nevis'), ('KP', 'Korea (North)'), ('KR', 'Korea (South)'), ('KW', 'Kuwait'), ('KY', 'Cayman Islands'), ('KZ', 'Kazakhstan'), ('LA', 'Laos'), ('L', 'Lebanon'), ('LC', 'St Lucia'), ('LI', 'Liechtenstein'), ('LK', 'Sri Lanka'), ('LR', 'Liberia'), ('LS', 'Lesotho'), ('LT', 'Lithuania'), ('LU', 'Luxembourg'), ('LV', 'Latvia'), ('LY', 'Libya'), ('MA', 'Morocco'), ('MC', 'Monaco'), ('MD', 'Moldova'), ('ME', 'Montenegro'), ('MF', 'St Martin (French)'), ('MG', 'Madagascar'), ('MH', 'Marshall Islands'), ('MK', 'Macedonia'), ('ML', 'Mali'), ('MM', 'Myanmar (Burma)'), ('MN', 'Mongolia'), ('MO', 'Macau'), ('MP', 'Northern Mariana Islands'), ('MQ', 'Martinique'), ('MR', 'Mauritania'), ('MS', 'Montserrat'), ('MT', 'Malta'), ('MU', 'Mauritius'), ('MV', 'Maldives'), ('MW', 'Malawi'), ('MX', 'Mexico'), ('MY', 'Malaysia'), ('MZ', 'Mozambique'), ('NA', 'Namibia'), ('NC', 'New Caledonia'), ('NE', 'Niger'), ('NF', 'Norfolk Island'), ('NG', 'Nigeria'), ('NI', 'Nicaragua'), ('NL', 'Netherlands'), ('NO', 'Norway'), ('NP', 'Nepal'), ('NR', 'Nauru'), ('NU', 'Niue'), ('NZ', 'New Zealand'), ('OM', 'Oman'), ('PA', 'Panama'), ('PE', 'Peru'), ('PF', 'French Polynesia'), ('PG', 'Papua New Guinea'), ('PH', 'Philippines'), ('PK', 'Pakistan'), ('PL', 'Poland'), ('PM', 'St Pierre & Miquelon'), ('PN', 'Pitcairn'), ('PR', 'Puerto Rico'), ('PS', 'Palestine'), ('PT', 'Portugal'), ('PW', 'Palau'), ('PY', 'Paraguay'), ('QA', 'Qatar'), ('RE', 'R\xc3\xa9union'), ('RO', 'Romania'), ('RS', 'Serbia'), ('RU', 'Russia'), ('RW', 'Rwanda'), ('SA', 'Saudi Arabia'), ('S', 'Solomon Islands'), ('SC', 'Seychelles'), ('SD', 'Sudan'), ('SE', 'Sweden'), ('SG', 'Singapore'), ('SH', 'St Helena'), ('SI', 'Slovenia'), ('SJ', 'Svalbard & Jan Mayen'), ('SK', 'Slovakia'), ('SL', 'Sierra Leone'), ('SM', 'San Marino'), ('SN', 'Senegal'), ('SO', 'Somalia'), ('SR', 'Suriname'), ('SS', 'South Sudan'), ('ST', 'Sao Tome & Principe'), ('SV', 'El Salvador'), ('SX', 'St Maarten (Dutch)'), ('SY', 'Syria'), ('SZ', 'Swaziland'), ('TC', 'Turks & Caicos Is'), ('TD', 'Chad'), ('TF', 'French Southern & Antarctic Lands'), ('TG', 'Togo'), ('TH', 'Thailand'), ('TJ', 'Tajikistan'), ('TK', 'Tokelau'), ('TL', 'East Timor'), ('TM', 'Turkmenistan'), ('TN', 'Tunisia'), ('TO', 'Tonga'), ('TR', 'Turkey'), ('TT', 'Trinidad & Tobago'), ('TV', 'Tuvalu'), ('TW', 'Taiwan'), ('TZ', 'Tanzania'), ('UA', 'Ukraine'), ('UG', 'Uganda'), ('UM', 'US minor outlying islands'), ('US', 'USA'), ('UY', 'Uruguay'), ('UZ', 'Uzbekistan'), ('VA', 'Vatican City'), ('VC', 'St Vincent'), ('VE', 'Venezuela'), ('VG', 'Virgin Islands (UK)'), ('VI', 'Virgin Islands (US)'), ('VN', 'Vietnam'), ('VU', 'Vanuatu'), ('WF', 'Wallis & Futuna'), ('WS', 'Samoa (western)'), ('YE', 'Yemen'), ('YT', 'Mayotte'), ('ZA', 'South Africa'), ('ZM', 'Zambia'), ('ZW', 'Zimbabwe')], default='AU', max_length=20),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='country',
            field=models.CharField(choices=[('AF', 'Afghanistan'), ('AX', '\xc3\x85land Islands'), ('AL', 'Albania'), ('DZ', 'Algeria'), ('AD', 'Andorra'), ('AO', 'Angola'), ('AI', 'Anguilla'), ('AQ', 'Antarctica'), ('AG', 'Antigua & Barbuda'), ('AR', 'Argentina'), ('AM', 'Armenia'), ('AW', 'Aruba'), ('AU', 'Australia'), ('AT', 'Austria'), ('AZ', 'Azerbaijan'), ('BS', 'Bahamas'), ('BH', 'Bahrain'), ('BD', 'Bangladesh'), ('B', 'Barbados'), ('BY', 'Belarus'), ('BE', 'Belgium'), ('BZ', 'Belize'), ('BJ', 'Benin'), ('BM', 'Bermuda'), ('BT', 'Bhutan'), ('BO', 'Bolivia'), ('BA', 'Bosnia & Herzegovina'), ('BW', 'Botswana'), ('BV', 'Bouvet Island'), ('BR', 'Brazil'), ('IO', 'British Indian Ocean Territory'), ('BN', 'Brunei'), ('BG', 'Bulgaria'), ('BF', 'Burkina Faso'), ('BI', 'Burundi'), ('KH', 'Cambodia'), ('CM', 'Cameroon'), ('CA', 'Canada'), ('CV', 'Cape Verde'), ('BQ', 'Caribbean NL'), ('KY', 'Cayman Islands'), ('CF', 'Central African Rep.'), ('TD', 'Chad'), ('CL', 'Chile'), ('CN', 'China'), ('CX', 'Christmas Island'), ('CC', 'Cocos (Keeling) Islands'), ('CO', 'Colombia'), ('KM', 'Comoros'), ('CD', 'Congo (Dem. Rep.)'), ('CG', 'Congo (Rep.)'), ('CK', 'Cook Islands'), ('CR', 'Costa Rica'), ('HR', 'Croatia'), ('CU', 'Cuba'), ('CW', 'Cura\xc3\xa7ao'), ('CY', 'Cyprus'), ('CZ', 'Czech Republic'), ('CI', "C\xc3\xb4te d'Ivoire"), ('DK', 'Denmark'), ('DJ', 'Djibouti'), ('DM', 'Dominica'), ('DO', 'Dominican Republic'), ('TL', 'East Timor'), ('EC', 'Ecuador'), ('EG', 'Egypt'), ('SV', 'El Salvador'), ('GQ', 'Equatorial Guinea'), ('ER', 'Eritrea'), ('EE', 'Estonia'), ('ET', 'Ethiopia'), ('FK', 'Falkland Islands'), ('FO', 'Faroe Islands'), ('FJ', 'Fiji'), ('FI', 'Finland'), ('FR', 'France'), ('GF', 'French Guiana'), ('PF', 'French Polynesia'), ('TF', 'French Southern & Antarctic Lands'), ('GA', 'Gabon'), ('GM', 'Gambia'), ('GE', 'Georgia'), ('DE', 'Germany'), ('GH', 'Ghana'), ('GI', 'Gibraltar'), ('GR', 'Greece'), ('GL', 'Greenland'), ('GD', 'Grenada'), ('GP', 'Guadeloupe'), ('GU', 'Guam'), ('GT', 'Guatemala'), ('GG', 'Guernsey'), ('GN', 'Guinea'), ('GW', 'Guinea-Bissau'), ('GY', 'Guyana'), ('HT', 'Haiti'), ('HM', 'Heard Island & McDonald Islands'), ('HN', 'Honduras'), ('HK', 'Hong Kong'), ('HU', 'Hungary'), ('IS', 'Iceland'), ('IN', 'India'), ('ID', 'Indonesia'), ('IR', 'Iran'), ('IQ', 'Iraq'), ('IE', 'Ireland'), ('IM', 'Isle of Man'), ('IL', 'Israel'), ('IT', 'Italy'), ('JM', 'Jamaica'), ('JP', 'Japan'), ('JE', 'Jersey'), ('JO', 'Jordan'), ('KZ', 'Kazakhstan'), ('KE', 'Kenya'), ('KI', 'Kiribati'), ('KP', 'Korea (North)'), ('KR', 'Korea (South)'), ('KW', 'Kuwait'), ('KG', 'Kyrgyzstan'), ('LA', 'Laos'), ('LV', 'Latvia'), ('L', 'Lebanon'), ('LS', 'Lesotho'), ('LR', 'Liberia'), ('LY', 'Libya'), ('LI', 'Liechtenstein'), ('LT', 'Lithuania'), ('LU', 'Luxembourg'), ('MO', 'Macau'), ('MK', 'Macedonia'), ('MG', 'Madagascar'), ('MW', 'Malawi'), ('MY', 'Malaysia'), ('MV', 'Maldives'), ('ML', 'Mali'), ('MT', 'Malta'), ('MH', 'Marshall Islands'), ('MQ', 'Martinique'), ('MR', 'Mauritania'), ('MU', 'Mauritius'), ('YT', 'Mayotte'), ('MX', 'Mexico'), ('FM', 'Micronesia'), ('MD', 'Moldova'), ('MC', 'Monaco'), ('MN', 'Mongolia'), ('ME', 'Montenegro'), ('MS', 'Montserrat'), ('MA', 'Morocco'), ('MZ', 'Mozambique'), ('MM', 'Myanmar (Burma)'), ('NA', 'Namibia'), ('NR', 'Nauru'), ('NP', 'Nepal'), ('NL', 'Netherlands'), ('NC', 'New Caledonia'), ('NZ', 'New Zealand'), ('NI', 'Nicaragua'), ('NE', 'Niger'), ('NG', 'Nigeria'), ('NU', 'Niue'), ('NF', 'Norfolk Island'), ('MP', 'Northern Mariana Islands'), ('NO', 'Norway'), ('OM', 'Oman'), ('PK', 'Pakistan'), ('PW', 'Palau'), ('PS', 'Palestine'), ('PA', 'Panama'), ('PG', 'Papua New Guinea'), ('PY', 'Paraguay'), ('PE', 'Peru'), ('PH', 'Philippines'), ('PN', 'Pitcairn'), ('PL', 'Poland'), ('PT', 'Portugal'), ('PR', 'Puerto Rico'), ('QA', 'Qatar'), ('RO', 'Romania'), ('RU', 'Russia'), ('RW', 'Rwanda'), ('RE', 'R\xc3\xa9union'), ('AS', 'Samoa (American)'), ('WS', 'Samoa (western)'), ('SM', 'San Marino'), ('ST', 'Sao Tome & Principe'), ('SA', 'Saudi Arabia'), ('SN', 'Senegal'), ('RS', 'Serbia'), ('SC', 'Seychelles'), ('SL', 'Sierra Leone'), ('SG', 'Singapore'), ('SK', 'Slovakia'), ('SI', 'Slovenia'), ('S', 'Solomon Islands'), ('SO', 'Somalia'), ('ZA', 'South Africa'), ('GS', 'South Georgia & the South Sandwich Islands'), ('SS', 'South Sudan'), ('ES', 'Spain'), ('LK', 'Sri Lanka'), ('BL', 'St Barthelemy'), ('SH', 'St Helena'), ('KN', 'St Kitts & Nevis'), ('LC', 'St Lucia'), ('SX', 'St Maarten (Dutch)'), ('MF', 'St Martin (French)'), ('PM', 'St Pierre & Miquelon'), ('VC', 'St Vincent'), ('SD', 'Sudan'), ('SR', 'Suriname'), ('SJ', 'Svalbard & Jan Mayen'), ('SZ', 'Swaziland'), ('SE', 'Sweden'), ('CH', 'Switzerland'), ('SY', 'Syria'), ('TW', 'Taiwan'), ('TJ', 'Tajikistan'), ('TZ', 'Tanzania'), ('TH', 'Thailand'), ('TG', 'Togo'), ('TK', 'Tokelau'), ('TO', 'Tonga'), ('TT', 'Trinidad & Tobago'), ('TN', 'Tunisia'), ('TR', 'Turkey'), ('TM', 'Turkmenistan'), ('TC', 'Turks & Caicos Is'), ('TV', 'Tuvalu'), ('UM', 'US minor outlying islands'), ('US', 'USA'), ('UG', 'Uganda'), ('UA', 'Ukraine'), ('AE', 'United Arab Emirates'), ('G', 'United Kingdom'), ('UY', 'Uruguay'), ('UZ', 'Uzbekistan'), ('VU', 'Vanuatu'), ('VA', 'Vatican City'), ('VE', 'Venezuela'), ('VN', 'Vietnam'), ('VG', 'Virgin Islands (UK)'), ('VI', 'Virgin Islands (US)'), ('WF', 'Wallis & Futuna'), ('EH', 'Western Sahara'), ('YE', 'Yemen'), ('ZM', 'Zambia'), ('ZW', 'Zimbabwe')], default='AU', max_length=20),
        ),
        migrations.AlterField(
            model_name='hub',
            name='phone',
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='hub',
            name='name',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AlterField(
            model_name='hub',
            name='phone',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='merchant',
            name='use_way_back_status',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='Label',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('color', models.CharField(choices=[('red', 'Red'), ('green', 'Green'), ('blue', 'Blue'), ('yellow', 'Yellow'), ('black', 'Black')], max_length=9)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AddField(
            model_name='merchant',
            name='enable_labels',
            field=models.BooleanField(default=False, verbose_name='Enable jobs labels'),
        ),
        migrations.AddField(
            model_name='label',
            name='merchant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant.Merchant'),
        ),
        migrations.AlterUniqueTogether(
            name='label',
            unique_together=set([('name', 'color', 'merchant')]),
        ),
        migrations.AlterField(
            model_name='label',
            name='color',
            field=models.CharField(choices=[('red', 'Red'), ('green', 'Green'), ('blue', 'Blue'), ('yellow', 'Yellow'), ('orange', 'Orange'), ('dark_blue', 'Dark Blue'), ('navy_blue', 'Navy Blue'), ('burgundy', 'Burgundy'), ('purple', 'Purple'), ('pink', 'Pink')], max_length=9),
        ),
        migrations.AlterUniqueTogether(
            name='label',
            unique_together=set([('color', 'merchant')]),
        ),
    ]
