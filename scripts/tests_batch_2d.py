import io
from unittest.mock import MagicMock, patch
from datetime import date
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from scripts.models import (
    Script, Scene, ScriptElement, Character, ScriptNote, ScriptBackupLog
)
User = get_user_model()


class Batch2DGlobalSearchAndBackupIsolationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='search_writer',
            email='writer@example.com',
            password='password123'
        )
        self.other_user = User.objects.create_user(
            username='other_writer',
            email='other@example.com',
            password='password123'
        )
        self.client.force_login(self.user)

        # 1. Active Script 1 (Owner: self.user)
        self.active_script = Script.objects.create(
            user=self.user,
            title='ജീവന്റെ തുടിപ്പ് (Active Heartbeat)',
            description='An active thriller screenplay',
            author_name='ആക്ടീവ് എഴുത്തുകാരൻ',
            genre='Thriller',
            language='Malayalam'
        )
        # Active Scene 1 on Active Script
        self.active_scene = Scene.objects.create(
            script=self.active_script,
            scene_number=1,
            heading='INT. ACTIVE HOUSE - DAY',
            summary='സജീവമായ രംഗം',
            order=0,
            is_deleted=False
        )
        self.active_dialogue = ScriptElement.objects.create(
            scene=self.active_scene,
            element_type='dialogue',
            content='ഞാൻ ഇവിടെയുണ്ട് (I am here in active scene).',
            order=0
        )
        # Trashed Scene 2 on Active Script
        self.trashed_scene_on_active_script = Scene.objects.create(
            script=self.active_script,
            scene_number=2,
            heading='EXT. TRASHED GARDEN - NIGHT',
            summary='തള്ളപ്പെട്ട പൂന്തോട്ടം',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        self.element_in_trashed_scene = ScriptElement.objects.create(
            scene=self.trashed_scene_on_active_script,
            element_type='dialogue',
            content='രഹസ്യ സംഭാഷണം (Secret dialogue in trashed scene).',
            order=0
        )
        self.active_char = Character.objects.create(
            script=self.active_script,
            name='മോഹൻ (Active Mohan)',
            description='നായകൻ'
        )
        self.active_note = ScriptNote.objects.create(
            script=self.active_script,
            title='ആക്ടീവ് കുറിപ്പ് (Active Plot Note)',
            content='ക്ലൈമാക്സ് പ്ലോട്ട് ട്വിസ്റ്റ്'
        )

        # 2. Trashed Script 2 (Owner: self.user)
        self.trashed_script = Script.objects.create(
            user=self.user,
            title='മറന്നുപോയ കഥ (Trashed Forgotten Story)',
            description='A trashed horror screenplay',
            author_name='മറന്ന എഴുത്തുകാരൻ',
            genre='Horror',
            language='Malayalam',
            is_deleted=True,
            deleted_at=timezone.now()
        )
        # Active Scene on Trashed Script
        self.scene_on_trashed_script = Scene.objects.create(
            script=self.trashed_script,
            scene_number=1,
            heading='INT. TRASHED SCRIPT ROOM - NIGHT',
            summary='തള്ളപ്പെട്ട തിരക്കഥയിലെ മുറി',
            order=0,
            is_deleted=False
        )
        self.element_in_trashed_script = ScriptElement.objects.create(
            scene=self.scene_on_trashed_script,
            element_type='dialogue',
            content='തള്ളപ്പെട്ട തിരക്കഥാ സംഭാഷണം (Dialogue in trashed script).',
            order=0
        )
        self.char_on_trashed_script = Character.objects.create(
            script=self.trashed_script,
            name='പ്രേതം (Ghost in trashed script)',
            description='ബാധ'
        )
        self.note_on_trashed_script = ScriptNote.objects.create(
            script=self.trashed_script,
            title='തള്ളപ്പെട്ട കുറിപ്പ് (Trashed Script Note)',
            content='ഭയം'
        )

        # 3. Active Script 3 (Owner: self.other_user)
        self.other_script = Script.objects.create(
            user=self.other_user,
            title='അന്യന്റെ തിരക്കഥ (Other User Story)',
            description='Other user active script',
            author_name='അന്യൻ',
            genre='Drama',
            language='Malayalam'
        )
        self.other_scene = Scene.objects.create(
            script=self.other_script,
            scene_number=1,
            heading='INT. OTHER HOUSE - DAY',
            order=0,
            is_deleted=False
        )
        self.other_dialogue = ScriptElement.objects.create(
            scene=self.other_scene,
            element_type='dialogue',
            content='മറ്റൊരാളുടെ രഹസ്യം (Other user secret).',
            order=0
        )
        self.other_char = Character.objects.create(
            script=self.other_script,
            name='അന്യൻ കഥാപാത്രം',
            description='വേറെ ആൾ'
        )
        self.other_note = ScriptNote.objects.create(
            script=self.other_script,
            title='അന്യന്റെ കുറിപ്പ്',
            content='രഹസ്യ കുറിപ്പ്'
        )

    # =========================================================================
    # GLOBAL SEARCH ISOLATION TESTS
    # =========================================================================

    def test_search_active_scripts_appear(self):
        """Active script matches query and appears in results['scripts']."""
        response = self.client.get('/search/?q=തുടിപ്പ്')
        self.assertEqual(response.status_code, 200)
        matched_scripts = list(response.context['results']['scripts'])
        self.assertEqual(len(matched_scripts), 1)
        self.assertEqual(matched_scripts[0].id, self.active_script.id)

    def test_search_trashed_scripts_do_not_appear(self):
        """Trashed script does NOT appear in results['scripts']."""
        response = self.client.get('/search/?q=മറന്നുപോയ')
        self.assertEqual(response.status_code, 200)
        matched_scripts = list(response.context['results']['scripts'])
        self.assertEqual(len(matched_scripts), 0)

    def test_search_active_scenes_appear(self):
        """Active scene on active script appears in results['scenes']."""
        response = self.client.get('/search/?q=ACTIVE+HOUSE')
        self.assertEqual(response.status_code, 200)
        matched_scenes = list(response.context['results']['scenes'])
        self.assertEqual(len(matched_scenes), 1)
        self.assertEqual(matched_scenes[0].id, self.active_scene.id)

    def test_search_trashed_scenes_do_not_appear(self):
        """Trashed scene on active script does NOT appear in results['scenes']."""
        response = self.client.get('/search/?q=TRASHED+GARDEN')
        self.assertEqual(response.status_code, 200)
        matched_scenes = list(response.context['results']['scenes'])
        self.assertEqual(len(matched_scenes), 0)

    def test_search_scenes_belonging_to_trashed_scripts_do_not_appear(self):
        """Scene belonging to a trashed script does NOT appear in results['scenes']."""
        response = self.client.get('/search/?q=TRASHED+SCRIPT+ROOM')
        self.assertEqual(response.status_code, 200)
        matched_scenes = list(response.context['results']['scenes'])
        self.assertEqual(len(matched_scenes), 0)

    def test_search_elements_in_active_scene_appear(self):
        """Dialogue in an active scene of an active script appears in results['dialogues']."""
        response = self.client.get('/search/?q=ഞാൻ+ഇവിടെയുണ്ട്')
        self.assertEqual(response.status_code, 200)
        matched_elements = list(response.context['results']['dialogues'])
        self.assertEqual(len(matched_elements), 1)
        self.assertEqual(matched_elements[0].id, self.active_dialogue.id)

    def test_search_elements_in_trashed_scenes_do_not_appear(self):
        """Dialogue belonging to a trashed scene does NOT appear in results['dialogues']."""
        response = self.client.get('/search/?q=രഹസ്യ+സംഭാഷണം')
        self.assertEqual(response.status_code, 200)
        matched_elements = list(response.context['results']['dialogues'])
        self.assertEqual(len(matched_elements), 0)

    def test_search_elements_in_trashed_scripts_do_not_appear(self):
        """Dialogue belonging to a scene of a trashed script does NOT appear in results['dialogues']."""
        response = self.client.get('/search/?q=തള്ളപ്പെട്ട+തിരക്കഥാ+സംഭാഷണം')
        self.assertEqual(response.status_code, 200)
        matched_elements = list(response.context['results']['dialogues'])
        self.assertEqual(len(matched_elements), 0)

    def test_search_characters_in_trashed_scripts_do_not_appear(self):
        """Character belonging to a trashed script does NOT appear in results['characters']."""
        response = self.client.get('/search/?q=പ്രേതം')
        self.assertEqual(response.status_code, 200)
        matched_chars = list(response.context['results']['characters'])
        self.assertEqual(len(matched_chars), 0)

        # But active character matches
        response_active = self.client.get('/search/?q=മോഹൻ')
        self.assertEqual(response_active.status_code, 200)
        matched_active_chars = list(response_active.context['results']['characters'])
        self.assertEqual(len(matched_active_chars), 1)
        self.assertEqual(matched_active_chars[0].id, self.active_char.id)

    def test_search_notes_in_trashed_scripts_do_not_appear(self):
        """Script note belonging to a trashed script does NOT appear in results['notes']."""
        response = self.client.get('/search/?q=തള്ളപ്പെട്ട+കുറിപ്പ്')
        self.assertEqual(response.status_code, 200)
        matched_notes = list(response.context['results']['notes'])
        self.assertEqual(len(matched_notes), 0)

        # But active note matches
        response_active = self.client.get('/search/?q=ആക്ടീവ്+കുറിപ്പ്')
        self.assertEqual(response_active.status_code, 200)
        matched_active_notes = list(response_active.context['results']['notes'])
        self.assertEqual(len(matched_active_notes), 1)
        self.assertEqual(matched_active_notes[0].id, self.active_note.id)

    def test_search_cross_user_boundary_maintained(self):
        """Content owned by another user is never revealed to the logged-in user."""
        response = self.client.get('/search/?q=അന്യൻ')
        self.assertEqual(response.status_code, 200)
        res = response.context['results']
        self.assertEqual(len(res['scripts']), 0)
        self.assertEqual(len(res['scenes']), 0)
        self.assertEqual(len(res['dialogues']), 0)
        self.assertEqual(len(res['characters']), 0)
        self.assertEqual(len(res['notes']), 0)

    def test_search_malayalam_unicode_query(self):
        """Malayalam Unicode search cleanly matches active content across categories."""
        response = self.client.get('/search/?q=സജീവമായ')
        self.assertEqual(response.status_code, 200)
        matched_scenes = list(response.context['results']['scenes'])
        self.assertEqual(len(matched_scenes), 1)
        self.assertEqual(matched_scenes[0].id, self.active_scene.id)

    # =========================================================================
    # PDF EXPORT ISOLATION TESTS
    # =========================================================================

    def test_active_script_with_trashed_scenes_excludes_trashed_scenes_from_pdf(self):
        """Live PDF generator called on an active script excludes its trashed scenes."""
        from scripts.services.pdf_export import generate_screenplay_pdf
        pdf_bytes = generate_screenplay_pdf(self.active_script, include_notes=False)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 100)

        # Verify through active ordered_scenes that trashed scene is excluded
        ordered = self.active_script.get_ordered_scenes()
        ordered_ids = [s.id for s in ordered]
        self.assertIn(self.active_scene.id, ordered_ids)
        self.assertNotIn(self.trashed_scene_on_active_script.id, ordered_ids)
