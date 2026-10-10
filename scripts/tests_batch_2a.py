from django.test import TestCase
from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils import timezone
from scripts.models import Script, Scene, ScriptElement, Character
from scripts.views import get_user_script as views_get_user_script
from scripts.api_views import get_user_script as api_get_user_script

User = get_user_model()


class Batch2AModelAndHelperTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='writer_primary',
            email='primary@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='writer_other',
            email='other@example.com',
            password='password123'
        )
        self.script = Script.objects.create(
            user=self.user1,
            title='Active Master Screenplay',
            language='Malayalam'
        )

        # Main Scene 1 (Active)
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. HOUSE - DAY',
            order=0,
            is_deleted=False
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='scene_heading',
            content='INT. HOUSE - DAY',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='സൂര്യൻ ഉദിക്കുന്നു',  # 2 words
            order=1
        )

        # Sub-Scene 1A (Active)
        self.scene1a = Scene.objects.create(
            script=self.script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. HOUSE - BEDROOM - DAY',
            order=1,
            is_deleted=False
        )
        ScriptElement.objects.create(
            scene=self.scene1a,
            element_type='action',
            content='രാഹുൽ ഉറക്കമുണരുന്നു',  # 2 words
            order=0
        )

        # Main Scene 2 (Trashed)
        self.scene2_trashed = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='EXT. STREET - DAY',
            order=2,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        ScriptElement.objects.create(
            scene=self.scene2_trashed,
            element_type='action',
            content='ഈ ഭാഗം ഒഴിവാക്കി കളഞ്ഞു',  # 4 words in trashed scene
            order=0
        )

        # Trashed Sub-Scene 1B under active Scene 1
        self.scene1b_trashed = Scene.objects.create(
            script=self.script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. HOUSE - KITCHEN - DAY',
            order=3,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        ScriptElement.objects.create(
            scene=self.scene1b_trashed,
            element_type='action',
            content='ചായ ഉണ്ടാക്കുന്നു അനാവശ്യം',  # 3 words
            order=0
        )

        # Main Scene 3 (Active Intercut)
        self.scene3_intercut = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. HOUSE - DAY',
            order=4,
            is_intercut=True,
            intercut_source=self.scene1,
            is_deleted=False
        )

        # Character with dialogue in both active and trashed scenes
        self.character = Character.objects.create(
            script=self.script,
            name='രാഹുൽ'
        )
        # Active dialogue
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='character',
            content='രാഹുൽ',
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='dialogue',
            content='സുപ്രഭാതം!',
            order=3
        )
        # Trashed dialogue in trashed scene
        ScriptElement.objects.create(
            scene=self.scene2_trashed,
            element_type='character',
            content='രാഹുൽ',
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene2_trashed,
            element_type='dialogue',
            content='ഇത് പഴയ ഡയലോഗ് ആണ്',
            order=2
        )

    def test_get_ordered_scenes_excludes_trashed_scenes_and_subscenes(self):
        """1 & 2: get_ordered_scenes() must exclude trashed scenes and trashed sub-scenes."""
        ordered = self.script.get_ordered_scenes()
        ordered_ids = [s.id for s in ordered]

        self.assertIn(self.scene1.id, ordered_ids)
        self.assertIn(self.scene1a.id, ordered_ids)
        self.assertIn(self.scene3_intercut.id, ordered_ids)
        self.assertNotIn(self.scene2_trashed.id, ordered_ids)
        self.assertNotIn(self.scene1b_trashed.id, ordered_ids)

        # Inspect prefetched sub-scenes of Scene 1
        scene1_retrieved = next(s for s in ordered if s.id == self.scene1.id)
        sub_scene_ids = [sub.id for sub in scene1_retrieved.sub_scenes.all()]
        self.assertIn(self.scene1a.id, sub_scene_ids)
        self.assertNotIn(self.scene1b_trashed.id, sub_scene_ids)

    def test_scene_counts_exclude_trashed_scenes(self):
        """3: Scene and sub-scene counts exclude trashed scenes while preserving intercut semantics."""
        # scene_count (non-intercut, active): scene1 + scene1a = 2 (scene3 is intercut, scene2 & 1b are trashed)
        self.assertEqual(self.script.scene_count, 2)
        # primary_scene_count (parent_scene is None, is_intercut=False, active): scene1 = 1
        self.assertEqual(self.script.primary_scene_count, 1)
        # sub_scene_count (parent_scene is not None, is_intercut=False, active): scene1a = 1
        self.assertEqual(self.script.sub_scene_count, 1)

    def test_word_and_char_counts_exclude_trashed_content(self):
        """4: Word and character counts exclude content from trashed scenes."""
        # Active scenes:
        # scene1: "INT. HOUSE - DAY" (heading, but elem has content "INT. HOUSE - DAY", action "സൂര്യൻ ഉദിക്കുന്നു", character "രാഹുൽ", dialogue "സുപ്രഭാതം!")
        # scene1a: action "രാഹുൽ ഉറക്കമുണരുന്നു"
        # scene3_intercut: no elements
        # Total words from trashed scenes (4 + 3 + 1 + 5 = 13 words) must NOT be counted.
        expected_active_words = (
            len("INT. HOUSE - DAY".split()) +
            len("സൂര്യൻ ഉദിക്കുന്നു".split()) +
            len("രാഹുൽ".split()) +
            len("സുപ്രഭാതം!".split()) +
            len("രാഹുൽ ഉറക്കമുണരുന്നു".split())
        )
        self.assertEqual(self.script.word_count, expected_active_words)
        self.assertGreater(self.script.char_count, 0)
        self.assertGreater(self.script.estimated_pages, 0)

    def test_character_dialogue_count_excludes_trashed_scenes(self):
        """5: Character dialogue count excludes dialogue in trashed scenes."""
        # Rahul has 1 dialogue in active Scene 1 and 1 dialogue in trashed Scene 2
        self.assertEqual(self.character.dialogue_count, 1)

    def test_views_get_user_script_behavior(self):
        """6, 7, 8: views.get_user_script rejects trashed scripts by default, respects allow_deleted, and prevents cross-user access."""
        # Trashed script owned by user1
        trashed_script = Script.objects.create(
            user=self.user1,
            title='Trashed Script',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # 6: Default rejects trashed script
        with self.assertRaises(Http404):
            views_get_user_script(self.user1, trashed_script.id)

        # 7: allow_deleted=True permits access to trashed script owned by user
        retrieved = views_get_user_script(self.user1, trashed_script.id, allow_deleted=True)
        self.assertEqual(retrieved.id, trashed_script.id)

        # Active script retrieved normally
        active_retrieved = views_get_user_script(self.user1, self.script.id)
        self.assertEqual(active_retrieved.id, self.script.id)

        # 8: Cross-user access denied under both flags
        with self.assertRaises(Http404):
            views_get_user_script(self.user2, self.script.id)
        with self.assertRaises(Http404):
            views_get_user_script(self.user2, trashed_script.id, allow_deleted=True)

    def test_api_views_get_user_script_behavior(self):
        """8 & 9: api_views.get_user_script rejects trashed scripts by default and prevents cross-user access."""
        trashed_script = Script.objects.create(
            user=self.user1,
            title='Trashed Script API',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # Rejects trashed script by default
        with self.assertRaises(Http404):
            api_get_user_script(self.user1, trashed_script.id)

        # allow_deleted=True works for owner
        retrieved = api_get_user_script(self.user1, trashed_script.id, allow_deleted=True)
        self.assertEqual(retrieved.id, trashed_script.id)

        # Cross-user access denied under both flags
        with self.assertRaises(Http404):
            api_get_user_script(self.user2, self.script.id)
        with self.assertRaises(Http404):
            api_get_user_script(self.user2, trashed_script.id, allow_deleted=True)
