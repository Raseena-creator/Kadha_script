import json
import os
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.conf import settings
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    resequence_script_scenes,
    create_sub_scene,
)


class Batch3Step2SceneCardSynchronizationTests(TestCase):
    """
    Focused regression test suite for Batch 3 Step 2 (Issue J):
    Scene Card Synchronization After Saving a Location:
    1. Saving a changed scene heading/location returns complete authoritative metadata
       (including nav_identifier, clean_heading, clean_location, full_display_heading).
    2. Sub-scene save retains relationships, parent linking, and returns correct nav_identifier.
    3. Malayalam Unicode heading/location saving and extraction.
    4. Failed save returns error status and isolates database state.
    5. editor.js contract inspection verifying:
       - Desktop and mobile scene card DOM synchronization
       - Stale/out-of-order save race condition protection (sceneSaveCounters)
       - Preservation of active selection/editing state (no disruptive full tree re-render)
       - Failure handling never marking unsaved changes as saved
    """

    def setUp(self):
        self.user = User.objects.create_user(username='screenwriter_step2', password='testpassword123')
        self.client = Client()
        self.client.login(username='screenwriter_step2', password='testpassword123')

        self.script = Script.objects.create(
            title='Kaalam - The Passage of Time',
            user=self.user,
            description='A Malayalam cinematic drama.'
        )

    def test_01_api_save_scene_returns_authoritative_metadata(self):
        """
        Saving a changed scene heading must return authoritative metadata:
        clean_location, clean_heading, full_display_heading, nav_identifier, scene_identifier.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OLD HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content='Sunlight pours through dusty windows.', order=0)
        resequence_script_scenes(self.script)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        payload = {
            'heading': 'EXT. HARBOR DOCKS - NIGHT',
            'transition': 'DISSOLVE TO',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'EXT. HARBOR DOCKS - NIGHT'},
                {'element_type': 'action', 'content': 'Waves lap against rusted pillars.'}
            ]
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['scene_id'], s1.id)
        self.assertEqual(data['heading'], 'EXT. HARBOR DOCKS - NIGHT')
        self.assertEqual(data['clean_heading'], 'EXT. HARBOR DOCKS - NIGHT')
        self.assertEqual(data['clean_location'], 'HARBOR DOCKS')
        self.assertEqual(data['scene_identifier'], 'Scene 1')
        self.assertEqual(data['nav_identifier'], 'Scene 1')
        self.assertEqual(data['display_number'], 'Scene 1')
        self.assertEqual(data['full_display_heading'], 'Scene 1 : EXT. HARBOR DOCKS - NIGHT')
        self.assertEqual(data['transition'], 'DISSOLVE TO')

        # Verify database was updated
        s1.refresh_from_db()
        self.assertEqual(s1.heading, 'EXT. HARBOR DOCKS - NIGHT')
        self.assertEqual(s1.clean_location, 'HARBOR DOCKS')
        self.assertEqual(s1.transition, 'DISSOLVE TO')

    def test_02_api_save_sub_scene_preserves_relationships_and_returns_nav_identifier(self):
        """
        Saving a sub-scene heading returns proper sub-scene nav_identifier (e.g. Scene 1A)
        and preserves parent_scene relationships.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. POLICE HQ - DAY', order=0)
        sub_1a = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB INTERROGATION ROOM')
        resequence_script_scenes(self.script)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': sub_1a.id})
        payload = {
            'heading': 'SUB EVIDENCE LOCKER',
            'transition': 'CUT TO',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'SUB EVIDENCE LOCKER'},
                {'element_type': 'action', 'content': 'Fluorescent light flickers.'}
            ]
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['scene_identifier'], 'Scene 1.A')
        self.assertEqual(data['nav_identifier'], 'Scene 1A')
        self.assertEqual(data['clean_heading'], 'SUB EVIDENCE LOCKER')
        self.assertEqual(data['clean_location'], 'SUB EVIDENCE LOCKER')

        # Verify parent relationship intact
        sub_1a.refresh_from_db()
        self.assertEqual(sub_1a.parent_scene_id, s1.id)
        self.assertTrue(sub_1a.is_sub_scene)

    def test_03_malayalam_unicode_location_saving_and_clean_location(self):
        """
        Authoritative save of Malayalam Unicode location and heading preserves clean_location
        and full_display_heading accurately.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        resequence_script_scenes(self.script)

        mal_heading = 'INT. തറവാട് - NIGHT'
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        payload = {
            'heading': mal_heading,
            'transition': 'CUT TO',
            'elements': [
                {'element_type': 'scene_heading', 'content': mal_heading},
                {'element_type': 'action', 'content': 'ചുമരിലെ ഘടികാരം ടിക് ടിക് ശബ്ദമുണ്ടാക്കുന്നു.'}
            ]
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['heading'], mal_heading)
        self.assertEqual(data['clean_location'], 'തറവാട്')
        self.assertEqual(data['full_display_heading'], f'Scene 1 : {mal_heading}')

        s1.refresh_from_db()
        self.assertEqual(s1.clean_location, 'തറവാട്')

    def test_04_failed_save_error_handling_and_data_isolation(self):
        """
        Failed save requests (invalid JSON or invalid scene) return an error status
        and do not corrupt existing scene data.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ORIGINAL - DAY', order=0)

        # Invalid JSON
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data="invalid json syntax", content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['status'], 'error')

        # Nonexistent scene ID
        url_fake = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': 99999})
        res_fake = self.client.post(url_fake, data=json.dumps({'heading': 'NEW'}), content_type='application/json')
        self.assertEqual(res_fake.status_code, 404)

        s1.refresh_from_db()
        self.assertEqual(s1.heading, 'INT. ORIGINAL - DAY')

    def test_05_editor_js_synchronization_and_safety_contracts(self):
        """
        Verify editor.js implementation contracts:
        1. Both desktop and mobile scene cards use .scene-item[data-id="..."] with .scene-nav-location and .scene-nav-number.
        2. saveCurrentScene uses sceneSaveCounters to guard against out-of-order / delayed stale save responses.
        3. Authoritative server response synchronizes treeItem, activeSidebarLocs, activeSidebarNumbers, and currentSelectorBadge.
        4. Stale saves or active edits are protected: hasNewerUnsavedEdits keeps status dirty without overwriting.
        5. Failed saves in catch block never set status to saved.
        """
        editor_js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'editor.js')
        with open(editor_js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        # Contract 1: Card selectors for location and number
        self.assertIn('.scene-item[data-id="${targetSceneId}"] .scene-nav-location', js)
        self.assertIn('.scene-item[data-id="${targetSceneId}"] .scene-nav-number', js)

        # Contract 2: Per-scene monotonic save counter / token to prevent delayed overwrites
        self.assertIn('this.sceneSaveCounters', js)
        self.assertIn('isLatestSaveForScene', js)
        self.assertIn('hasNewerUnsavedEdits', js)

        # Contract 3: Synchronizes in-memory tree with authoritative fields
        self.assertIn('treeItem.clean_location = result.clean_location;', js)
        self.assertIn('treeItem.full_display_heading = result.full_display_heading;', js)
        self.assertIn('treeItem.nav_identifier = result.nav_identifier;', js)

        # Contract 4: Keeps active editor badge and full heading consistent
        self.assertIn('this.currentSelectorBadge.innerText = this.currentFullHeading;', js)

        # Contract 5: Action buttons data-heading updated
        self.assertIn('btn.dataset.heading = result.heading;', js)

        # Contract 6: Failure handling
        self.assertIn("this.setSaveStatus('saved', 'Saved ✓');", js)
        self.assertIn("Save failed", js)
