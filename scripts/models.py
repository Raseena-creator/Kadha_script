from django.db import models
from django.contrib.auth.models import User
import math

class Script(models.Model):
    GENRE_CHOICES = [
        ('Drama', 'Drama'),
        ('Romance', 'Romance'),
        ('Comedy', 'Comedy'),
        ('Thriller', 'Thriller'),
        ('Horror', 'Horror'),
        ('Mystery', 'Mystery'),
        ('Action', 'Action'),
        ('Family', 'Family'),
        ('Crime', 'Crime'),
        ('Other', 'Other'),
    ]

    SCRIPT_TYPE_CHOICES = [
        ('Short Film', 'Short Film'),
        ('Feature Film', 'Feature Film'),
        ('Web Series', 'Web Series'),
        ('YouTube', 'YouTube'),
        ('Drama', 'Drama'),
        ('Advertisement', 'Advertisement'),
        ('Other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scripts')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    genre = models.CharField(max_length=50, choices=GENRE_CHOICES, default='Drama')
    script_type = models.CharField(max_length=50, choices=SCRIPT_TYPE_CHOICES, default='Short Film')
    author_name = models.CharField(max_length=150, blank=True)
    language = models.CharField(max_length=50, default='Malayalam')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
        ]

    def __str__(self):
        return self.title

    @property
    def scene_count(self):
        return self.scenes.count()

    @property
    def word_count(self):
        total_words = 0
        for scene in self.scenes.all():
            for elem in scene.elements.all():
                if elem.content:
                    total_words += len(elem.content.split())
        return total_words

    @property
    def char_count(self):
        total_chars = 0
        for scene in self.scenes.all():
            for elem in scene.elements.all():
                if elem.content:
                    total_chars += len(elem.content)
        return total_chars

    @property
    def estimated_pages(self):
        wc = self.word_count
        if wc == 0:
            return 1 if self.scene_count > 0 else 0
        return max(1, math.ceil(wc / 220))

    def get_ordered_scenes(self):
        """
        Returns all scenes in logical screenplay reading order:
        Ordered by (order, id).
        """
        return list(self.scenes.all().prefetch_related('elements', 'parent_scene', 'sub_scenes__elements').order_by('order', 'id'))


def _sub_scene_letter(idx: int) -> str:
    """Converts 0-indexed integer into A, B, ... Z, AA, AB."""
    result = ""
    while idx >= 0:
        result = chr(ord('A') + (idx % 26)) + result
        idx = (idx // 26) - 1
    return result


class Scene(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='scenes')
    parent_scene = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='sub_scenes'
    )
    scene_number = models.PositiveIntegerField(default=1)
    is_duplicate = models.BooleanField(default=False)
    duplicate_number = models.PositiveIntegerField(default=0)
    is_intercut = models.BooleanField(default=False)
    intercut_source = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='intercut_instances'
    )
    heading = models.CharField(max_length=255, default='INT. LOCATION - DAY')
    summary = models.TextField(blank=True)
    transition = models.CharField(max_length=100, default='CUT TO', blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'scene_number', 'id']
        indexes = [
            models.Index(fields=['script', 'order']),
            models.Index(fields=['parent_scene', 'order']),
        ]

    @property
    def is_sub_scene(self) -> bool:
        return self.parent_scene_id is not None

    @property
    def duplicate_suffix(self) -> str:
        if not self.is_duplicate:
            return ""
        if self.duplicate_number <= 1:
            return " (Duplicate)"
        return f" (Duplicate {self.duplicate_number})"

    @property
    def sub_letter(self) -> str:
        if not self.parent_scene:
            return ''
        siblings = list(self.parent_scene.sub_scenes.all().order_by('order', 'id'))
        letter_idx = 0
        assigned_letter = 'A'
        for s in siblings:
            if not s.is_duplicate:
                assigned_letter = _sub_scene_letter(letter_idx)
                letter_idx += 1
            if s.id == self.id:
                return assigned_letter
        return assigned_letter

    @property
    def clean_heading(self) -> str:
        """Strips any redundant 'Scene X :' or 'Scene X.A :' prefixes from stored heading content."""
        import re
        text = self.heading or ''
        cleaned = re.sub(r'^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+', '', text.strip(), flags=re.IGNORECASE)
        return cleaned.strip() or text.strip()

    @property
    def scene_identifier(self) -> str:
        """
        Exact format:
        Main scene: 'Scene 1', 'Scene 2', etc.
        Sub-scene: 'Scene 1.A', 'Scene 1.B', 'Scene 2.A', etc.
        Intercut main scene: 'Scene 2' (retains source scene number without duplicate suffix)
        """
        if self.is_sub_scene and self.parent_scene:
            base = f"Scene {self.parent_scene.scene_number}.{self.sub_letter}"
            suffix = self.duplicate_suffix or (self.parent_scene.duplicate_suffix if not self.is_duplicate else "")
            return f"{base}{suffix}"
        if self.is_intercut:
            return f"Scene {self.scene_number}"
        return f"Scene {self.scene_number}{self.duplicate_suffix}"

    @property
    def display_number(self) -> str:
        return self.scene_identifier

    @property
    def display_number_formatted(self) -> str:
        return self.scene_identifier

    @property
    def full_display_heading(self) -> str:
        """
        Exact combined format on ONE line:
        Main scene: 'Scene 1 : INT. HOUSE - DAY'
        Sub-scene: 'Scene 1.A : LIVING ROOM'
        """
        return f"{self.scene_identifier} : {self.clean_heading}"

    def __str__(self):
        return self.full_display_heading

    @property
    def word_count(self):
        words = len(self.heading.split())
        for elem in self.elements.all():
            if elem.content:
                words += len(elem.content.split())
        return words


class ScriptElement(models.Model):
    ELEMENT_TYPE_CHOICES = [
        ('scene_heading', 'Scene Heading'),
        ('action', 'Action'),
        ('character', 'Character'),
        ('dialogue', 'Dialogue'),
        ('parenthetical', 'Parenthetical'),
        ('transition', 'Transition'),
        ('shot', 'Shot'),
        ('note', 'Note'),
    ]

    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name='elements')
    element_type = models.CharField(max_length=30, choices=ELEMENT_TYPE_CHOICES, default='action')
    content = models.TextField(blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['scene', 'order']),
        ]

    def __str__(self):
        return f'[{self.element_type}] {self.content[:30]}'


class Character(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Non-Binary', 'Non-Binary'),
        ('Other', 'Other'),
        ('Not Specified', 'Not Specified'),
    ]

    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='characters')
    name = models.CharField(max_length=150)
    age = models.CharField(max_length=50, blank=True)
    gender = models.CharField(max_length=50, choices=GENDER_CHOICES, default='Not Specified')
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('script', 'name')

    def __str__(self):
        return self.name

    @property
    def dialogue_count(self):
        return ScriptElement.objects.filter(
            scene__script=self.script,
            element_type='character',
            content__iexact=self.name
        ).count()


class ScriptNote(models.Model):
    CATEGORY_CHOICES = [
        ('Plot Ideas', 'Plot Ideas'),
        ('Character Ideas', 'Character Ideas'),
        ('Research', 'Research'),
        ('Dialogue Ideas', 'Dialogue Ideas'),
        ('Things to Change', 'Things to Change'),
        ('General', 'General'),
    ]

    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='General')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.title} ({self.category})'


class ScriptVersion(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, default='Draft Snapshot')
    description = models.TextField(blank=True)
    snapshot_data = models.JSONField(help_text='Full JSON snapshot of scenes and elements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number', '-created_at']

    def __str__(self):
        return f'{self.script.title} — v{self.version_number}'


class ScriptTitlePage(models.Model):
    """
    Dedicated production metadata and title page configuration for a screenplay.
    Maintains 1:1 ownership with Script.
    """
    script = models.OneToOneField(
        Script,
        on_delete=models.CASCADE,
        related_name='title_page'
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom title on title/cover page if different from screenplay title."
    )
    subtitle = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional subtitle, tagline, or genre specification."
    )
    author_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Primary author/screenwriter name."
    )
    pen_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Optional pen name or pseudonym."
    )
    adaptation_credits = models.TextField(
        blank=True,
        help_text="Optional adaptation, story by, or source material credits."
    )
    copyright_registration = models.TextField(
        blank=True,
        help_text="Optional registration or copyright notice (free text, e.g. FEFKA / WGA registration, copyright statement)."
    )
    draft_revision = models.CharField(
        max_length=100,
        blank=True,
        help_text="Draft revision label (e.g. First Draft, Revision 2, Shooting Draft)."
    )
    draft_date = models.CharField(
        max_length=100,
        blank=True,
        help_text="Draft date (e.g. October 2026 or 2026-10-02)."
    )
    contact_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Contact person name (screenwriter, agent, or representative)."
    )
    contact_email = models.EmailField(
        max_length=254,
        blank=True,
        help_text="Contact email address."
    )
    contact_phone = models.CharField(
        max_length=50,
        blank=True,
        help_text="Contact phone number."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Script Title Page'
        verbose_name_plural = 'Script Title Pages'

    def __str__(self):
        return f'Title Page — {self.script.title}'

    def get_effective_title(self) -> str:
        """Returns custom title if specified, else falls back to script title."""
        if self.title and self.title.strip():
            return self.title.strip()
        return self.script.title

    def get_effective_author(self) -> str:
        """Returns pen name if specified, else author name, else script author/username."""
        if self.pen_name and self.pen_name.strip():
            return self.pen_name.strip()
        if self.author_name and self.author_name.strip():
            return self.author_name.strip()
        if self.script.author_name and self.script.author_name.strip():
            return self.script.author_name.strip()
        if hasattr(self.script.user, 'profile') and self.script.user.profile.pen_name:
            return self.script.user.profile.pen_name
        return self.script.user.get_full_name() or self.script.user.username


class ScriptBackupLog(models.Model):
    """
    Audit and duplicate-protection record for automated daily screenplay backups.
    Tracks success, failures, recipient info, generated file metadata, and timestamps.
    """
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('SKIPPED', 'Skipped'),
    ]

    BACKUP_TYPE_CHOICES = [
        ('EMAIL', 'Email Backup'),
        ('GDRIVE', 'Google Drive Backup'),
    ]

    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='backup_logs'
    )
    backup_date = models.DateField(
        help_text="The calendar date of this daily backup."
    )
    backup_type = models.CharField(
        max_length=20,
        choices=BACKUP_TYPE_CHOICES,
        default='EMAIL'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SUCCESS'
    )
    recipient_email = models.CharField(
        max_length=254,
        blank=True,
        help_text="Destination email address for EMAIL backup."
    )
    filename = models.CharField(
        max_length=255,
        blank=True,
        help_text="Filename of the generated PDF backup."
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        help_text="Size of the generated PDF in bytes."
    )
    error_message = models.TextField(
        blank=True,
        default='',
        help_text="Error message if the backup failed."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-backup_date', '-created_at']
        verbose_name = 'Script Backup Log'
        verbose_name_plural = 'Script Backup Logs'
        indexes = [
            models.Index(fields=['backup_date', 'status']),
            models.Index(fields=['script', 'backup_date', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['script', 'backup_date', 'backup_type'],
                condition=models.Q(status='SUCCESS'),
                name='unique_successful_daily_backup_per_script'
            )
        ]

    def __str__(self):
        return f"{self.backup_type} Backup: {self.script.title} on {self.backup_date} [{self.status}]"



