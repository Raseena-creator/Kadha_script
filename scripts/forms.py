from django import forms
from .models import Script, Character, ScriptNote, ScriptVersion, Scene, ScriptTitlePage

class ScriptForm(forms.ModelForm):
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. നീലവെളിച്ചം / Neela Velicham', 'autofocus': True}),
        error_messages={'required': 'Please enter a screenplay title.'}
    )

    class Meta:
        model = Script
        fields = ['title', 'description', 'genre', 'script_type', 'author_name', 'language']
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Logline, synopsis, or concept overview...'}),
            'genre': forms.Select(attrs={'class': 'form-select'}),
            'script_type': forms.Select(attrs={'class': 'form-select'}),
            'author_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Screenwriter Name'}),
            'language': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Malayalam'}),
        }

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise forms.ValidationError('Script title cannot be blank or whitespace.')
        return title


class ScriptTitlePageForm(forms.ModelForm):
    contact_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. writer@kadhascript.com',
        })
    )

    class Meta:
        model = ScriptTitlePage
        fields = [
            'title', 'subtitle',
            'author_name', 'pen_name',
            'adaptation_credits',
            'draft_revision', 'draft_date',
            'copyright_registration',
            'contact_name', 'contact_email', 'contact_phone',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Leave blank to use screenplay title',
            }),
            'subtitle': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. An Original Screenplay / A Psychological Thriller',
            }),
            'author_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. P. Padmarajan / Screenwriter Name',
            }),
            'pen_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Padmarajan (overrides author name on cover)',
            }),
            'adaptation_credits': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g. Based on the short story by Vaikom Muhammad Basheer\nStory by Jane Doe',
            }),
            'draft_revision': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. First Draft / Revision 2 / Shooting Draft / Blue Polish',
            }),
            'draft_date': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. October 2026 or 2026-10-02',
            }),
            'copyright_registration': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g. FEFKA Reg. No. 12345/2026 or © 2026 Author Name. All Rights Reserved.',
            }),
            'contact_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Screenwriter / Production House / Agent Name',
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. writer@kadhascript.com',
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. +91 98765 43210',
            }),
        }
        help_texts = {
            'title': 'Optional title override. Leave blank to display the main script title.',
            'subtitle': 'Optional subtitle or format specification.',
            'author_name': 'Author / Screenwriter name on title page.',
            'pen_name': 'Optional. If specified, this pen name replaces the author name on the cover page.',
            'adaptation_credits': 'Optional. Enter adaptation source, story-by, or additional writing credits.',
            'draft_revision': 'Optional. Specify draft version (e.g. First Draft, Revision 2, Polish).',
            'draft_date': 'Optional. Draft completion or submission date.',
            'copyright_registration': 'Optional. Enter registration number, copyright notice, or legal text (e.g. FEFKA / WGA registration, copyright statement).',
            'contact_name': 'Optional. Name of contact person, agent, or company.',
            'contact_email': 'Optional. Email address for inquiries.',
            'contact_phone': 'Optional. Phone number for inquiries.',
        }


class CharacterForm(forms.ModelForm):
    class Meta:
        model = Character
        fields = ['name', 'age', 'gender', 'description', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Character Name (e.g. ANU or അനു)', 'required': True}),
            'age': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 28, Mid 40s'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Physical description, role in story...'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Backstory, dialogue traits, quirks...'}),
        }

class ScriptNoteForm(forms.ModelForm):
    class Meta:
        model = ScriptNote
        fields = ['title', 'category', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Note Title (e.g. Climax Twist Idea)'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Write your thoughts, research, dialogue ideas...'}),
        }

class ScriptVersionForm(forms.ModelForm):
    class Meta:
        model = ScriptVersion
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. First Draft, Interval Rework, Climax Polished'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Brief summary of changes in this version...'}),
        }

class SceneForm(forms.ModelForm):
    class Meta:
        model = Scene
        fields = ['scene_number', 'heading', 'summary']
        widgets = {
            'scene_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'heading': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. INT. HOUSE - NIGHT'}),
            'summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional scene beat / goal / summary...'}),
        }
