from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0002_alter_service_provider_service_id_orderitem"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="client_ip",
            new_name="customer_ip",
        ),
        migrations.RenameField(
            model_name="order",
            old_name="user_agent",
            new_name="customer_user_agent",
        ),
    ]
