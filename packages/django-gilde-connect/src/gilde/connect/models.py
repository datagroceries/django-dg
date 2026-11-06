import datetime
import hashlib
import secrets
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from gilde.connect import conf  # noqa: F401 - the OAuth settings, before anything reads them
from gilde.core import areas


class ApiToken(models.Model):
    """A personal key with which a program, such as an AI agent, acts as its user in the Gilde apps.

    For scripts, CI and agents that cannot sign in with OAuth. It belongs to a real account and does what
    that user may do, so nobody needs an agent account or a password. Only a hash of the key is stored:
    the key itself is shown once, when the token is made. A token stops working when it expires, is
    revoked, goes unused for INACTIVE_AFTER, or its user is deactivated. It opens the areas
    (gilde.core.areas) ticked when it was made, while its user may use them (gilde.core.authentication).
    """

    # Days a token lives, chosen when it is made; 0 lives until revoked. Machine integrations run for
    # years, and a token that expires on a fixed date breaks them unannounced, so that is the default.
    LIFETIMES: ClassVar = {0: _('Until revoked'), 30: _('30 days'), 90: _('90 days'), 365: _('A year')}
    # Whatever its lifetime, a token unused this long stops: a forgotten or leaked one cleans itself up,
    # and one in use never does.
    INACTIVE_AFTER = datetime.timedelta(days=90)
    # Every key starts with it, so a leaked one is recognised, and a token of another kind is told apart.
    PREFIX = 'gilde_'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gilde_api_tokens')
    name = models.CharField(max_length=60, help_text=_('What uses it, e.g. "Claude Code on my laptop".'))
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, help_text=_('The areas the token opens.'))
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text=_('Empty: until revoked.'))
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = _('API token')

    def __str__(self):
        return f'{self.user} - {self.name}'

    @staticmethod
    def hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name: str, scopes: list[str], days: int) -> tuple['ApiToken', str]:
        """Make a token living `days` (0: until revoked) and return it with its key, which is not stored
        and cannot be shown again."""
        key = cls.PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            name=name,
            scopes=scopes,
            key_hash=cls.hash(key),
            expires_at=timezone.now() + datetime.timedelta(days=days) if days else None,
        )
        return token, key

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_inactive(self) -> bool:
        """Unused for INACTIVE_AFTER, counting from when it was made if it never was."""
        return (self.last_used_at or self.created_at) <= timezone.now() - self.INACTIVE_AFTER

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and not self.is_expired and not self.is_inactive and self.user.is_active

    @property
    def scope(self) -> str:
        """The areas it opens, space-separated, as an OAuth token has them (gilde.core.authentication.opens)."""
        return ' '.join(self.scopes)

    def get_scopes_display(self) -> str:
        return ', '.join(areas.AREAS[scope].label for scope in self.scopes if scope in areas.AREAS)
