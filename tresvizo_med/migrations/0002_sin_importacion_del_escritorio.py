"""Med arranca sin datos del escritorio: se quitan las tablas de históricos y el SHA-256 de lotes de ZIP."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('med', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='HistoricoCita'),
        migrations.DeleteModel(name='HistoricoSeguimiento'),
        migrations.RemoveConstraint(model_name='loteimportacion', name='med_lote_zip_unico'),
        migrations.RemoveField(model_name='loteimportacion', name='sha256'),
        migrations.AlterField(model_name='loteimportacion', name='tipo',
                              field=models.CharField(choices=[('csv', 'Csv')], max_length=12)),
        migrations.AlterField(model_name='loteimportacion', name='estado',
                              field=models.CharField(choices=[('ensayo', 'Ensayo'), ('confirmado', 'Confirmado')], default='ensayo', max_length=12)),
    ]
