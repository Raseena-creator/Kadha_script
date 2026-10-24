"""
Regression and unit tests for KadhaScript — Scene-Level Note Indicators.

Verifies:
1. Scene model properties:
   - Scene without notes has has_notes=False and note_count=0.
   - Empty or whitespace-only notes are ignored (has_notes=False, note_count=0).
   - One non-empty note gives has_notes=True and note_count=1.
   - Multiple non-empty notes give correct note_count.
   - Prefetched elements cache is used to avoid N+1 queries.
2. Scene serialization:
   - serialize_scenes_hierarchy(script) includes has_notes and note_count for each scene.
3. Template rendering (editor.html):
   - Desktop Scene Order list (#scenesList) renders note indicator badge with tooltip and aria-label.
   - Mobile Scene Order drawer (#offcanvasScenesList) renders note indicator badge.
   - Scenes without notes do not have the note indicator badge.
4. API save scene:
   - api_save_scene returns has_notes and note_count in response JSON.
"""

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import serialize_scenes_hierarchy


class SceneNoteIndicatorModelAndServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer_notes', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='Scene Note Test Script',
            language='Malayalam'
        )

    def test_scene_without_notes(self):
        scene = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. ROOM - DAY',
            order=0
        )
        ScriptElement.objects.create(scene=scene, element_type='action', content='Walking in.', order=0)
        ScriptElement.objects.create(scene=scene, element_type='dialogue', content='Hello.', order=1)

        self.assertFalse(scene.has_notes)
        self.assertEqual(scene.note_count, 0)

    def test_empty_and_whitespace_notes_are_ignored(self):
        scene = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='EXT. PARK - DAY',
            order=1
        )
        ScriptElement.objects.create(scene=scene, element_type='note', content='', order=0)
        ScriptElement.objects.create(scene=scene, element_type='note', content='   \n\t  ', order=1)

        self.assertFalse(scene.has_notes)
        self.assertEqual(scene.note_count, 0)

    def test_single_and_multiple_notes_counted_correctly(self):
        # Scene with 1 valid note
        scene_one = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='INT. OFFICE - DAY',
            order=2
        )
        ScriptElement.objects.create(scene=scene_one, element_type='note', content='Check lighting.', order=0)

        self.assertTrue(scene_one.has_notes)
        self.assertEqual(scene_one.note_count, 1)

        # Scene with multiple valid notes + 1 empty note
        scene_multi = Scene.objects.create(
            script=self.script,
            scene_number=4,
            heading='INT. HALL - NIGHT',
            order=3
        )
        ScriptElement.objects.create(scene=scene_multi, element_type='note', content='Director note 1', order=0)
        ScriptElement.objects.create(scene=scene_multi, element_type='action', content='Actor enters', order=1)
        ScriptElement.objects.create(scene=scene_multi, element_type='note', content='', order=2)
        ScriptElement.objects.create(scene=scene_multi, element_type='note', content='Director note 2 in മലയാളം', order=3)
        ScriptElement.objects.create(scene=scene_multi, element_type='note', content='  \t ', order=4)
        ScriptElement.objects.create(scene=scene_multi, element_type='note', content='Sound FX cue note', order=5)

        self.assertTrue(scene_multi.has_notes)
        self.assertEqual(scene_multi.note_count, 3)

    def test_prefetched_elements_avoids_extra_queries(self):
        scene = Scene.objects.create(
            script=self.script,
            scene_number=5,
            heading='INT. CAFE - DAY',
            order=4
        )
        ScriptElement.objects.create(scene=scene, element_type='note', content='Important camera angle', order=0)

        # Query with prefetch_related
        prefetched_scene = Scene.objects.filter(id=scene.id).prefetch_related('elements').first()

        # Both properties should evaluate without triggering SQL queries
        with self.assertNumQueries(0):
            has_notes = prefetched_scene.has_notes
            count = prefetched_scene.note_count

        self.assertTrue(has_notes)
        self.assertEqual(count, 1)

    def test_serialize_scenes_hierarchy_includes_note_data(self):
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        sc2 = Scene.objects.create(script=self.script, scene_number=2, heading='SCENE 2', order=1)
        ScriptElement.objects.create(scene=sc2, element_type='note', content='Note on scene 2', order=0)

        tree = serialize_scenes_hierarchy(self.script)
        self.assertEqual(len(tree), 2)

        tree_sc1 = next(item for item in tree if item['id'] == sc1.id)
        self.assertFalse(tree_sc1['has_notes'])
        self.assertEqual(tree_sc1['note_count'], 0)

        tree_sc2 = next(item for item in tree if item['id'] == sc2.id)
        self.assertTrue(tree_sc2['has_notes'])
        self.assertEqual(tree_sc2['note_count'], 1)

    def test_unprefetched_scene_note_properties_single_query(self):
        scene = Scene.objects.create(
            script=self.script,
            scene_number=6,
            heading='INT. DINER - NIGHT',
            order=5
        )
        ScriptElement.objects.create(scene=scene, element_type='note', content='Night exterior insert', order=0)

        # Fetch without prefetch
        unprefetched_scene = Scene.objects.get(id=scene.id)
        with self.assertNumQueries(1):
            has_notes = unprefetched_scene.has_notes
            count = unprefetched_scene.note_count

        self.assertTrue(has_notes)
        self.assertEqual(count, 1)


class SceneNoteIndicatorTemplateAndApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='screenwriter', password='password123')
        self.client.login(username='screenwriter', password='password123')

        self.script = Script.objects.create(
            user=self.user,
            title='Indicator Template Script',
            language='Malayalam'
        )
        self.sc_no_notes = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. HOUSE - DAY',
            order=0
        )
        self.sc_with_notes = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='EXT. STREET - NIGHT',
            order=1
        )
        ScriptElement.objects.create(
            scene=self.sc_with_notes,
            element_type='note',
            content='Rain machine required here.',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.sc_with_notes,
            element_type='note',
            content='കഥാപാത്രത്തിന്റെ ചിന്ത (Character internal thought)',
            order=1
        )

    def test_editor_template_renders_note_badges_correctly(self):
        import re
        url = reverse('script_editor', kwargs={'script_id': self.script.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')

        # Check badge for scene with 2 notes in both desktop and mobile lists
        self.assertIn('Scene has 2 notes', content)
        self.assertIn('bi-sticky-fill', content)

        note_badge_scene_ids = re.findall(r'class="scene-nav-note-badge"[^>]*data-scene-id="(\d+)"', content)
        self.assertEqual(note_badge_scene_ids, [str(self.sc_with_notes.id), str(self.sc_with_notes.id)])
        self.assertNotIn(str(self.sc_no_notes.id), note_badge_scene_ids)

    def test_api_save_scene_returns_note_status(self):
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': self.sc_no_notes.id})

        # Save an action and a note into sc_no_notes
        payload = {
            'heading': 'INT. HOUSE - DAY',
            'elements': [
                {'element_type': 'action', 'content': 'He picks up the phone.'},
                {'element_type': 'note', 'content': 'Ensure camera tracks closely.'}
            ]
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertTrue(data.get('has_notes'))
        self.assertEqual(data.get('note_count'), 1)

        # Now clear the note
        clear_payload = {
            'heading': 'INT. HOUSE - DAY',
            'elements': [
                {'element_type': 'action', 'content': 'He picks up the phone.'},
                {'element_type': 'note', 'content': '   '}
            ]
        }
        response = self.client.post(
            url,
            data=json.dumps(clear_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertFalse(data.get('has_notes'))
        self.assertEqual(data.get('note_count'), 0)

    def test_full_deletion_of_note_removes_badge_from_save_response(self):
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': self.sc_with_notes.id})

        # Scene currently has 2 notes. Save payload containing only action elements (omits notes entirely)
        delete_payload = {
            'heading': 'EXT. STREET - NIGHT',
            'elements': [
                {'element_type': 'action', 'content': 'The street is completely deserted.'}
            ]
        }
        response = self.client.post(
            url,
            data=json.dumps(delete_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertFalse(data.get('has_notes'))
        self.assertEqual(data.get('note_count'), 0)

    def test_sub_scene_with_note_receives_indicator(self):
        import re
        main_sc = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='INT. MANSION - DAY',
            order=2
        )
        sub_sc = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='INT. MANSION - BEDROOM',
            order=3,
            parent_scene=main_sc
        )
        ScriptElement.objects.create(
            scene=sub_sc,
            element_type='note',
            content='Sub-scene specific prop note',
            order=0
        )

        self.assertTrue(sub_sc.has_notes)
        self.assertEqual(sub_sc.note_count, 1)

        # Hierarchy serialization check
        tree = serialize_scenes_hierarchy(self.script)
        sub_tree_item = next(item for item in tree if item['id'] == sub_sc.id)
        self.assertTrue(sub_tree_item['has_notes'])
        self.assertEqual(sub_tree_item['note_count'], 1)

        # Template rendering check
        url = reverse('script_editor', kwargs={'script_id': self.script.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        sub_badges = re.findall(rf'class="scene-nav-note-badge"[^>]*data-scene-id="{sub_sc.id}"', content)
        self.assertEqual(len(sub_badges), 2)  # once in #scenesList and once in #offcanvasScenesList
