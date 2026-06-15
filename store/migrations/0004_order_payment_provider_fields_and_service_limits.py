from django.db import migrations, models


def populate_external_payment_id(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    PaymentLog = apps.get_model("store", "PaymentLog")
    for order in Order.objects.filter(external_payment_id="").iterator():
        charge = (
            PaymentLog.objects.filter(order_id=order.pk, event_type="charge")
            .exclude(external_payment_id="")
            .order_by("-created_at")
            .first()
        )
        if charge:
            Order.objects.filter(pk=order.pk).update(
                external_payment_id=charge.external_payment_id
            )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0003_rename_order_customer_metadata"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="total_amount",
            new_name="amount_brl",
        ),
        migrations.RenameField(
            model_name="order",
            old_name="external_status",
            new_name="provider_status",
        ),
        migrations.AddField(
            model_name="order",
            name="external_payment_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=120,
                verbose_name="ID externo do pagamento",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="max_quantity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Limite opcional informado pela integração de entrega.",
                null=True,
                verbose_name="quantidade máxima",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="min_quantity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Limite opcional informado pela integração de entrega.",
                null=True,
                verbose_name="quantidade mínima",
            ),
        ),
        migrations.RunPython(populate_external_payment_id, migrations.RunPython.noop),
    ]
