from django.db import models

class FuelStop(models.Model):
    opis_id = models.IntegerField(help_text="OPIS Truckstop ID", db_index=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=10, db_index=True)
    rack_id = models.IntegerField(null=True, blank=True)
    retail_price = models.DecimalField(
        max_digits=8, decimal_places=4, db_index=True, help_text="Retail price per gallon in USD"
    )
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["state", "city"]),
        ]
        ordering = ["retail_price"]

    def __str__(self):
        return f"{self.truckstop_name} ({self.city}, {self.state}) - ${self.retail_price}/gal"
