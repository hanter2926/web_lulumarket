class AdPlacement(models.Model):

    name = models.CharField(max_length=100)

    location = models.CharField(
        max_length=100
    )

    is_active = models.BooleanField(
        default=True
    )

    code = models.TextField(
        blank=True
    )