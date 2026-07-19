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

class ContactMessage(models.Model):
    """Customer support inquiries."""
    name = models.CharField(max_length=150)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Message from {self.name} ({self.email})"
