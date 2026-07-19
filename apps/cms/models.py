"""CMS models for lightweight content management (G-6)."""

from django.db import models

class HomepageBanner(models.Model):
    """Promo banners for the homepage (FR-20)."""
    title = models.CharField(max_length=200)
    image_url = models.URLField()
    link_url = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ["order"]
        
    def __str__(self):
        return self.title
