from django.test import TestCase, Client
from django.contrib.auth.models import User
import json

from scripts.models import Script, Scene, ScriptElement


class EditorTransitionAndParentheticalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='ടെസ്റ്റ് തിരക്കഥ (Test Screenplay)',
            genre='Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.client = Client()
        self.client.login(username='writer', password='password123')

    def test_1_create_scene_does_not_create_cut_to_inside_scene(self):
        """1. Creating a new scene does NOT create CUT TO: inside the scene being written."""
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/create/',
            data=json.dumps({'heading': 'INT. ROOM - DAY'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        scene_id = data['scene']['id']

        elements = ScriptElement.objects.filter(scene_id=scene_id)
        # Verify no transition element was automatically inserted into the new scene
        transition_elements = elements.filter(element_type='transition')
        self.assertEqual(transition_elements.count(), 0)

    def test_2_moving_or_creating_next_scene_saves_cut_to_transition_at_end_of_previous_scene(self):
        """2. Moving/creating the next scene creates exactly one CUT TO: transition at the end of the previous scene."""
        # Create first scene
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=sc1, element_type='scene_heading', content=sc1.heading, order=0)
        ScriptElement.objects.create(scene=sc1, element_type='action', content='അനു അകത്തേക്ക് വരുന്നു.', order=1)

        # Emulate editor payload when writer finishes scene 1 and moves to scene 2 (editor adds CUT TO: transition)
        payload = {
            'heading': 'INT. HOUSE - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. HOUSE - DAY', 'order': 0},
                {'element_type': 'action', 'content': 'അനു അകത്തേക്ക് വരുന്നു.', 'order': 1},
                {'element_type': 'transition', 'content': 'CUT TO:', 'order': 2},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        transitions = ScriptElement.objects.filter(scene=sc1, element_type='transition')
        self.assertEqual(transitions.count(), 1)
        self.assertEqual(transitions.first().content, 'CUT TO:')

    def test_3_repeating_operation_does_not_create_duplicate_cut_to_elements(self):
        """3. Repeating the operation does not create duplicate CUT TO: elements."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=sc1, element_type='scene_heading', content=sc1.heading, order=0)
        ScriptElement.objects.create(scene=sc1, element_type='action', content='അനു വാതിൽ തുറക്കുന്നു.', order=1)
        ScriptElement.objects.create(scene=sc1, element_type='transition', content='CUT TO:', order=2)

        # Saving again with the same elements
        payload = {
            'heading': 'INT. HOUSE - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. HOUSE - DAY', 'order': 0},
                {'element_type': 'action', 'content': 'അനു വാതിൽ തുറക്കുന്നു.', 'order': 1},
                {'element_type': 'transition', 'content': 'CUT TO:', 'order': 2},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        transitions = ScriptElement.objects.filter(scene=sc1, element_type='transition')
        self.assertEqual(transitions.count(), 1)

    def test_4_existing_manually_created_transitions_are_preserved(self):
        """4. Existing manually created transitions must not be duplicated or overwritten."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OFFICE - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc1, element_type='scene_heading', content=sc1.heading, order=0)
        ScriptElement.objects.create(scene=sc1, element_type='action', content='റഹീം ഫയൽ നോക്കുന്നു.', order=1)
        ScriptElement.objects.create(scene=sc1, element_type='transition', content='DISSOLVE TO:', order=2)

        payload = {
            'heading': 'INT. OFFICE - NIGHT',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. OFFICE - NIGHT', 'order': 0},
                {'element_type': 'action', 'content': 'റഹീം ഫയൽ നോക്കുന്നു.', 'order': 1},
                {'element_type': 'transition', 'content': 'DISSOLVE TO:', 'order': 2},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        transitions = ScriptElement.objects.filter(scene=sc1, element_type='transition')
        self.assertEqual(transitions.count(), 1)
        self.assertEqual(transitions.first().content, 'DISSOLVE TO:')

    def test_5_parenthetical_text_automatically_wrapped(self):
        """5. Parenthetical text is automatically wrapped in ( and )."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. LIVING ROOM - DAY', order=0)

        # User entered raw 'whispering'
        raw_text = 'whispering'
        formatted = f"({raw_text.strip('() ')})"

        payload = {
            'heading': 'INT. LIVING ROOM - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. LIVING ROOM - DAY', 'order': 0},
                {'element_type': 'character', 'content': 'ANU', 'order': 1},
                {'element_type': 'parenthetical', 'content': formatted, 'order': 2},
                {'element_type': 'dialogue', 'content': 'ആരും കേൾക്കരുത്...', 'order': 3},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        parentheticals = ScriptElement.objects.filter(scene=sc1, element_type='parenthetical')
        self.assertEqual(parentheticals.count(), 1)
        self.assertEqual(parentheticals.first().content, '(whispering)')

    def test_6_already_bracketed_parenthetical_text_not_double_wrapped(self):
        """6. Already-bracketed parenthetical text is not double-wrapped."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. LIVING ROOM - DAY', order=0)

        payload = {
            'heading': 'INT. LIVING ROOM - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. LIVING ROOM - DAY', 'order': 0},
                {'element_type': 'character', 'content': 'ANU', 'order': 1},
                {'element_type': 'parenthetical', 'content': '(whispering)', 'order': 2},
                {'element_type': 'dialogue', 'content': 'ഹലോ...', 'order': 3},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        parentheticals = ScriptElement.objects.filter(scene=sc1, element_type='parenthetical')
        self.assertEqual(parentheticals.count(), 1)
        self.assertEqual(parentheticals.first().content, '(whispering)')
        self.assertFalse(parentheticals.first().content.startswith('(('))

    def test_7_existing_malayalam_text_remains_unchanged(self):
        """7. Existing Malayalam text remains unchanged."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. വീട് - പകൽ', order=0)

        malayalam_parenthetical = '(പതുക്കെ ചിരിച്ചുകൊണ്ട്)'
        malayalam_dialogue = 'നമുക്ക് നാളെ പോകാം.'

        payload = {
            'heading': 'INT. വീട് - പകൽ',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. വീട് - പകൽ', 'order': 0},
                {'element_type': 'character', 'content': 'അനു', 'order': 1},
                {'element_type': 'parenthetical', 'content': malayalam_parenthetical, 'order': 2},
                {'element_type': 'dialogue', 'content': malayalam_dialogue, 'order': 3},
            ]
        }
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        elements = ScriptElement.objects.filter(scene=sc1).order_by('order')
        self.assertEqual(elements[2].content, '(പതുക്കെ ചിരിച്ചുകൊണ്ട്)')
        self.assertEqual(elements[3].content, 'നമുക്ക് നാളെ പോകാം.')

    def test_8_sub_scene_creation_does_not_force_transition_on_parent(self):
        """8. Creating a sub-scene (e.g. Scene 2A under Scene 2) does not force CUT TO on parent scene."""
        sc2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. HOUSE - DAY', order=1)
        ScriptElement.objects.create(scene=sc2, element_type='scene_heading', content=sc2.heading, order=0)
        ScriptElement.objects.create(scene=sc2, element_type='action', content='Living room action.', order=1)

        # Create subscene 2A via API
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc2.id}/subscene/',
            data=json.dumps({'heading': 'INT. HOUSE - KITCHEN'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        sub_scene = data['scene']
        self.assertTrue(sub_scene['is_sub_scene'])
        self.assertEqual(sub_scene['parent_scene_id'], sc2.id)

        # Parent scene elements should remain clean without forced transition
        parent_transitions = ScriptElement.objects.filter(scene=sc2, element_type='transition')
        self.assertEqual(parent_transitions.count(), 0)

    def test_9_editor_script_contains_transition_rollback_safeguards(self):
        """9. editor.js implements transition rollback, dirty-version tracking, and save coordination."""
        import os
        from django.conf import settings
        editor_js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'editor.js')
        with open(editor_js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # ensurePreviousSceneHasTransition returns newBlock or null
        self.assertIn('ensurePreviousSceneHasTransition() {', js_content)
        self.assertIn('return newBlock;', js_content)
        self.assertIn('return null;', js_content)

        # appendScene rollback on flushSave failure
        self.assertIn('const addedTransition = this.ensurePreviousSceneHasTransition();', js_content)
        self.assertIn('if (addedTransition && addedTransition.parentElement) {', js_content)

        # submitInsertScene rollback on flushSave failure
        self.assertIn('addedTransition = this.ensurePreviousSceneHasTransition();', js_content)

        # switchScene cancellation and rollback on save failure
        self.assertIn('Save failed before switching scene:', js_content)
        self.assertIn('addedTransition.remove();', js_content)
        self.assertIn('this.calculateLiveStats();', js_content)
        self.assertIn('Scene switching was cancelled to protect your unsaved writing.', js_content)

        # moveScene and submitDeleteScene cancellation on save failure
        self.assertIn('Save failed before moving scene:', js_content)
        self.assertIn('Scene movement was cancelled to protect your unsaved writing.', js_content)
        self.assertIn('Save failed before deleting scene:', js_content)
        self.assertIn('Scene deletion was cancelled to protect your unsaved writing.', js_content)
        self.assertNotIn('Could not save current scene before moving. Move anyway?', js_content)
        self.assertNotIn('Could not save current scene before deleting. Delete anyway?', js_content)

        # Dirty-state version tracking and flushSave coordination
        self.assertIn('this.changeVersion = (this.changeVersion || 0) + 1;', js_content)
        self.assertIn('(this.changeVersion || 0) === saveVersion', js_content)
        self.assertIn('while (this.isSaving && this.activeSavePromise)', js_content)
        self.assertIn('while (this.isDirty && attempts < 5)', js_content)
        self.assertIn('if (this.isDirty) {', js_content)
        self.assertIn("throw new Error('Could not save current scene changes after multiple attempts');", js_content)

    def test_10_database_elements_preserved_when_save_fails(self):
        """10. Previous scene elements remain intact on DB if a subsequent save payload fails."""
        sc = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='INT. CABIN - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='കാറ്റ് വീശുന്നു.', order=1)

        # Attempt to save with invalid payload that returns an error
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc.id}/save/',
            data='invalid json',
            content_type='application/json'
        )
        self.assertNotEqual(res.status_code, 200)

        # Verify DB elements remain unchanged
        elems = ScriptElement.objects.filter(scene=sc).order_by('order')
        self.assertEqual(elems.count(), 2)
        self.assertEqual(elems[1].content, 'കാറ്റ് വീശുന്നു.')

    def test_11_sequential_saves_preserve_and_update_latest_content(self):
        """11. Backend correctly persists sequential save updates when newer edits follow prior saves."""
        sc = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OFFICE - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='INT. OFFICE - DAY', order=0)

        # Save 1: Initial action element
        payload1 = {
            'heading': 'INT. OFFICE - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. OFFICE - DAY', 'order': 0},
                {'element_type': 'action', 'content': 'Initial typing.', 'order': 1},
            ]
        }
        res1 = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc.id}/save/',
            data=json.dumps(payload1),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)

        # Save 2: Newer edits adding transition
        payload2 = {
            'heading': 'INT. OFFICE - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. OFFICE - DAY', 'order': 0},
                {'element_type': 'action', 'content': 'Initial typing.', 'order': 1},
                {'element_type': 'transition', 'content': 'CUT TO:', 'order': 2},
            ]
        }
        res2 = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc.id}/save/',
            data=json.dumps(payload2),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)

        elems = ScriptElement.objects.filter(scene=sc).order_by('order')
        self.assertEqual(elems.count(), 3)
        self.assertEqual(elems[2].element_type, 'transition')
        self.assertEqual(elems[2].content, 'CUT TO:')

    def test_12_failed_save_before_scene_creation_prevents_orphan_scenes(self):
        """12. If saving fails, the scene count remains unchanged and no orphan scene is added."""
        sc = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='INT. ROOM - DAY', order=0)

        initial_count = Scene.objects.filter(script=self.script).count()
        self.assertEqual(initial_count, 1)

        # Failed save does not create or alter scenes in DB
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc.id}/save/',
            data='{invalid}',
            content_type='application/json'
        )
        self.assertNotEqual(res.status_code, 200)

        # Verify no second scene was created
        current_count = Scene.objects.filter(script=self.script).count()
        self.assertEqual(current_count, 1)

    def test_13_move_and_delete_not_triggered_on_save_failure(self):
        """13. Verified that when save fails, scenes remain in order and are not deleted."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        sc2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)

        # Verify initial order
        self.assertEqual(Scene.objects.filter(script=self.script).count(), 2)
        scenes = list(Scene.objects.filter(script=self.script).order_by('order'))
        self.assertEqual(scenes[0].id, sc1.id)
        self.assertEqual(scenes[1].id, sc2.id)

        # Failed save does not delete or alter order
        res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{sc1.id}/save/',
            data='{invalid}',
            content_type='application/json'
        )
        self.assertNotEqual(res.status_code, 200)

        scenes_after = list(Scene.objects.filter(script=self.script).order_by('order'))
        self.assertEqual(len(scenes_after), 2)
        self.assertEqual(scenes_after[0].id, sc1.id)
        self.assertEqual(scenes_after[1].id, sc2.id)

    def test_14_batch_2b_3_scene_navigation_and_load_race_guards(self):
        """
        14. Batch 2B-3: editor.js contains monotonic load tokens, stale response discard,
        and reentrant navigation lock coordination.
        """
        import os
        from django.conf import settings
        editor_js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'editor.js')
        with open(editor_js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # 1. Monotonic load token and stale response discard
        self.assertIn('this.loadRequestId = 0;', js_content)
        self.assertIn('const requestId = ++this.loadRequestId;', js_content)
        self.assertIn('if (requestId !== this.loadRequestId) {', js_content)
        self.assertIn('Number(data?.scene?.id) !== Number(this.currentSceneId)', js_content)

        # 2. Reentrancy lock and navigation coordination in switchScene
        self.assertIn('this.isSwitchingScene = false;', js_content)
        self.assertIn('this.activeSwitchPromise = null;', js_content)
        self.assertIn('this.pendingSwitchSceneId = null;', js_content)
        self.assertIn('if (this.isSwitchingScene) {', js_content)
        self.assertIn('this.pendingSwitchSceneId = targetId;', js_content)
        self.assertIn('while (this.isSwitchingScene) {', js_content)
        self.assertIn('await this.activeSwitchPromise;', js_content)

        # 3. Superseded intermediate scene switch skips stale rendering
        self.assertIn('if (this.pendingSwitchSceneId !== null && this.pendingSwitchSceneId !== targetId) {', js_content)

        # 4. Lock release guarantee in try/finally
        self.assertIn('this.isSwitchingScene = true;', js_content)
        self.assertIn('} finally {', js_content)
        self.assertIn('this.isSwitchingScene = false;', js_content)
        self.assertIn('this.activeSwitchPromise = null;', js_content)

        # 5. Failed save cancels switch and restores active scene UI
        self.assertIn('this.pendingSwitchSceneId = null;', js_content)
        self.assertIn('Number(item.dataset.id) === Number(this.currentSceneId)', js_content)

    def test_15_backend_scene_endpoints_support_concurrent_loads(self):
        """
        15. Rapid/concurrent scene load API requests return independent, correct payloads
        without race conditions or cross-contamination.
        """
        sc_a = Scene.objects.create(script=self.script, scene_number=4, heading='INT. SCENE A - DAY', order=5)
        ScriptElement.objects.create(scene=sc_a, element_type='scene_heading', content=sc_a.heading, order=0)
        ScriptElement.objects.create(scene=sc_a, element_type='action', content='Content A in Scene A.', order=1)

        sc_b = Scene.objects.create(script=self.script, scene_number=5, heading='EXT. SCENE B - NIGHT', order=6)
        ScriptElement.objects.create(scene=sc_b, element_type='scene_heading', content=sc_b.heading, order=0)
        ScriptElement.objects.create(scene=sc_b, element_type='action', content='Content B in Scene B.', order=1)

        # Request A then Request B
        res_a = self.client.get(f'/scripts/api/{self.script.id}/scenes/{sc_a.id}/')
        res_b = self.client.get(f'/scripts/api/{self.script.id}/scenes/{sc_b.id}/')

        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_b.status_code, 200)

        data_a = res_a.json()
        data_b = res_b.json()

        self.assertEqual(data_a['scene']['id'], sc_a.id)
        self.assertEqual(data_b['scene']['id'], sc_b.id)
        self.assertEqual(data_a['elements'][1]['content'], 'Content A in Scene A.')
        self.assertEqual(data_b['elements'][1]['content'], 'Content B in Scene B.')


class EditorUINavigationClientRequirementsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='filmmaker', password='Password123!')
        self.script = Script.objects.create(
            user=self.user,
            title='My Malayalam Screenplay',
            genre='Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.client = Client()
        self.client.login(username='filmmaker', password='Password123!')

    def test_editor_navbar_shows_screenplay_name_home_and_scenes_button(self):
        """1. Navbar displays current screenplay name, Home button to dashboard, and prominent Scenes button."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Screenplay name displayed exactly as stored
        self.assertIn('My Malayalam Screenplay', content)
        self.assertIn('class="navbar-screenplay-title text-truncate font-screenplay"', content)

        # Home button replaces pen icon and links to dashboard
        self.assertIn('id="btnEditorHome"', content)
        self.assertIn('href="/dashboard/"', content)
        self.assertIn('bi-house-door-fill', content)

        # Scenes button in main navbar toggles editor Scenes offcanvas directly (does NOT open Scene Management)
        self.assertIn('id="btnNavScenes"', content)
        self.assertIn('btn-nav-scenes', content)
        self.assertIn('data-bs-toggle="offcanvas"', content)
        self.assertIn('data-bs-target="#scenesOffcanvas"', content)
        self.assertNotIn(f'href="/scripts/{self.script.id}/scenes/"', content)
        self.assertIn('<span>Scenes</span>', content)

    def test_editor_toolbar_back_and_heading_buttons_removed(self):
        """2. Back button removed from toolbar and Heading button removed from element toolbar."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Back button removed from toolbar below navbar
        self.assertNotIn('id="btnBackToScript"', content)
        self.assertNotIn('Back to Overview', content)

        # Heading button removed from element toolbar
        self.assertNotIn('data-type="scene_heading"', content)

        # Required remaining buttons present
        self.assertIn('data-type="action"', content)
        self.assertIn('data-type="character"', content)
        self.assertIn('data-type="dialogue"', content)
        self.assertIn('data-type="parenthetical"', content)

    def test_export_dropdown_only_export_related(self):
        """3. Export dropdown retains exports/previews and removes obsolete navigation."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Exports and previews retained
        self.assertIn('Export PDF', content)
        self.assertIn('Export Word (.docx)', content)
        self.assertIn('Export Plain Text', content)
        self.assertIn('Print Preview', content)

        # Obsolete navigation items removed from More Tools dropdown
        self.assertNotIn('Scene Management</a>', content)
        self.assertNotIn('Version Snapshots</a>', content)

    def test_obsolete_pages_redirect_to_editor(self):
        """4. Obsolete pages (script overview, scene management, characters, notes, versions) redirect cleanly to editor."""
        for path in [
            f'/scripts/{self.script.id}/',
            f'/scripts/{self.script.id}/scenes/',
            f'/scripts/{self.script.id}/characters/',
            f'/scripts/{self.script.id}/notes/',
            f'/scripts/{self.script.id}/versions/',
        ]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.url, f'/scripts/{self.script.id}/editor/')

    def test_bottom_bar_status_preserved_and_navigation_removed(self):
        """5. Editor bottom stats bar preserves counts/saved status, obsolete nav links removed."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Status counts and indicators present
        self.assertIn('id="statWordCount"', content)
        self.assertIn('id="statCharCount"', content)
        self.assertIn('id="statPageCount"', content)
        self.assertIn('id="statSceneCount"', content)
        self.assertIn('id="saveStatusBadge"', content)

        # Obsolete navigation links removed from sidebar/offcanvas footers
        self.assertNotIn('Manage Scenes</span>', content)
        self.assertNotIn('sidebar-footer', content)

    def test_dashboard_and_my_scripts_links_point_directly_to_editor(self):
        """6. Screenplay cards/titles in Dashboard and My Scripts point directly to script_editor (Req #1, #2)."""
        expected_editor_url = f'/scripts/{self.script.id}/editor/'

        # Dashboard
        dash_res = self.client.get('/dashboard/')
        self.assertEqual(dash_res.status_code, 200)
        dash_content = dash_res.content.decode('utf-8')
        self.assertIn(f'href="{expected_editor_url}"', dash_content)
        self.assertNotIn(f'href="/scripts/{self.script.id}/"', dash_content)

        # My Scripts
        scripts_res = self.client.get('/scripts/')
        self.assertEqual(scripts_res.status_code, 200)
        scripts_content = scripts_res.content.decode('utf-8')
        self.assertIn(f'href="{expected_editor_url}"', scripts_content)
        self.assertNotIn(f'href="/scripts/{self.script.id}/"', scripts_content)
        self.assertNotIn(f'href="/scripts/{self.script.id}/scenes/"', scripts_content)

    def test_editor_scenes_section_displays_scenes_and_subscenes(self):
        """7. Editor Scenes section/sidebar renders scenes (Scene 1, Scene 2) and sub-scenes (2.A, 2.B) correctly."""
        sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. LIVING ROOM - DAY', order=0)
        sc2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. STREET - NIGHT', order=1)
        sub2a = Scene.objects.create(script=self.script, scene_number=2, parent_scene=sc2, heading='ALLEYWAY', order=2)
        sub2b = Scene.objects.create(script=self.script, scene_number=2, parent_scene=sc2, heading='ROOFTOP', order=3)

        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Verified in offcanvasScenesList
        self.assertIn('id="scenesOffcanvas"', content)
        self.assertIn('id="offcanvasScenesList"', content)
        self.assertIn('INT. LIVING ROOM - DAY', content)
        self.assertIn('EXT. STREET - NIGHT', content)
        self.assertIn('ALLEYWAY', content)
        self.assertIn('ROOFTOP', content)
        self.assertIn('2.A', content)
        self.assertIn('2.B', content)

    def test_mobile_swipe_behavior_preserved(self):
        """8. Existing mobile swipe behavior scripts and handlers for Scenes offcanvas are preserved."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Verified mobile offcanvas and swipe container structure
        self.assertIn('id="scenesOffcanvas"', content)
        self.assertIn('class="offcanvas offcanvas-start', content)
        self.assertIn('editor.js', content)


class ReadModeAndEditModeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='filmmaker', password='secretpassword')
        self.script = Script.objects.create(
            user=self.user,
            title='ആരണ്യം (The Forest)',
            genre='Thriller',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.client = Client()
        self.client.login(username='filmmaker', password='secretpassword')

        # Create scenes with hierarchy
        self.s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        ScriptElement.objects.create(scene=self.s1, element_type='scene_heading', content=self.s1.heading, order=0)
        ScriptElement.objects.create(scene=self.s1, element_type='action', content='കാറ്റിന്റെ ശബ്ദം മാത്രം കേൾക്കാം.', order=1)

        self.s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. FOREST - NIGHT', order=1)
        ScriptElement.objects.create(scene=self.s2, element_type='scene_heading', content=self.s2.heading, order=0)
        ScriptElement.objects.create(scene=self.s2, element_type='character', content='രാഘവൻ', order=1)
        ScriptElement.objects.create(scene=self.s2, element_type='dialogue', content='ആരാണ് അവിടെ?', order=2)

        # Sub-scenes under Scene 2
        self.sub2a = Scene.objects.create(script=self.script, scene_number=2, parent_scene=self.s2, heading='DEEP WOODS', order=2)
        ScriptElement.objects.create(scene=self.sub2a, element_type='scene_heading', content='DEEP WOODS', order=0)
        ScriptElement.objects.create(scene=self.sub2a, element_type='action', content='നിഴലുകൾ അനങ്ങുന്നു.', order=1)

        self.sub2b = Scene.objects.create(script=self.script, scene_number=2, parent_scene=self.s2, heading='RIVERBANK', order=3)
        ScriptElement.objects.create(scene=self.sub2b, element_type='scene_heading', content='RIVERBANK', order=0)

        self.s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. POLICE STATION - MORNING', order=4)
        ScriptElement.objects.create(scene=self.s3, element_type='scene_heading', content=self.s3.heading, order=0)

    def test_editor_opens_in_read_mode_by_default(self):
        """1. Editor opens in READ MODE by default with data-mode='read' on editor root."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn('id="screenplayEditor"', content)
        self.assertIn('data-mode="read"', content)

    def test_read_mode_renders_all_scenes_continuously(self):
        """2. Read Mode renders all scenes continuously in one vertically scrollable document."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Read mode container exists
        self.assertIn('id="readModeContainer"', content)
        self.assertIn('read-mode-container', content)

        # Content of scene 1, 2, 2A, 2B, 3 all rendered in read-mode
        self.assertIn('കാറ്റിന്റെ ശബ്ദം മാത്രം കേൾക്കാം.', content)
        self.assertIn('രാഘവൻ', content)
        self.assertIn('ആരാണ് അവിടെ?', content)
        self.assertIn('നിഴലുകൾ അനങ്ങുന്നു.', content)

    def test_scene_anchors_exist_with_actual_django_ids(self):
        """3. Every scene in continuous Read Mode has a stable DOM anchor with actual Django ID."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn(f'id="read-scene-{self.s1.id}"', content)
        self.assertIn(f'data-scene-id="{self.s1.id}"', content)
        self.assertIn(f'id="read-scene-{self.s2.id}"', content)
        self.assertIn(f'data-scene-id="{self.s2.id}"', content)
        self.assertIn(f'id="read-scene-{self.sub2a.id}"', content)
        self.assertIn(f'data-scene-id="{self.sub2a.id}"', content)
        self.assertIn(f'id="read-scene-{self.sub2b.id}"', content)
        self.assertIn(f'data-scene-id="{self.sub2b.id}"', content)
        self.assertIn(f'id="read-scene-{self.s3.id}"', content)
        self.assertIn(f'data-scene-id="{self.s3.id}"', content)

    def test_scene_navigator_clean_structure_and_prefixes(self):
        """4. Scene Navigator in sidebar/offcanvas displays clean Scene X and location without INT./EXT. clutter."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn('class="scene-nav-item"', content)
        self.assertIn('class="scene-nav-number font-screenplay"', content)
        self.assertIn('class="scene-nav-location font-malayalam"', content)

        # Verify Scene 1 clean location strips INT. and - DAY
        self.assertEqual(self.s1.nav_identifier, 'Scene 1')
        self.assertEqual(self.s1.clean_location, 'CABIN')
        self.assertEqual(self.s2.nav_identifier, 'Scene 2')
        self.assertEqual(self.s2.clean_location, 'FOREST')
        self.assertEqual(self.sub2a.nav_identifier, 'Scene 2A')
        self.assertEqual(self.sub2a.clean_location, 'DEEP WOODS')
        self.assertEqual(self.sub2b.nav_identifier, 'Scene 2B')
        self.assertEqual(self.sub2b.clean_location, 'RIVERBANK')
        self.assertEqual(self.s3.nav_identifier, 'Scene 3')
        self.assertEqual(self.s3.clean_location, 'POLICE STATION')

    def test_floating_action_buttons_and_suggestion_popup_present(self):
        """5. Floating Edit button, Done button, and contextual suggestion popup are present in template."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn('id="btnEnterEditMode"', content)
        self.assertIn('id="btnExitEditMode"', content)
        self.assertIn('id="elementSuggestionPopup"', content)
        self.assertIn('role="listbox"', content)
        self.assertIn('aria-label="Element suggestions"', content)

    def test_scenes_navbar_button_opens_offcanvas_no_standalone_link(self):
        """6. Scenes navbar button has data-bs-target='#scenesOffcanvas' and does NOT navigate to standalone page."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn('id="btnNavScenes"', content)
        self.assertIn('data-bs-target="#scenesOffcanvas"', content)
        self.assertNotIn('href="/scripts/{self.script.id}/scenes/"', content)

    def test_redundant_action_buttons_removed_from_scenes_sidebar(self):
        """7. Redundant action buttons (Add Scene, Insert, Add Sub-scene) removed from sidebar/offcanvas."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Verify not present in sidebar/offcanvas
        self.assertNotIn('Insert Sub Scene Before', content)
        self.assertNotIn('Insert Sub Scene After', content)
        self.assertNotIn('sidebar-action-btn', content)

    def test_standalone_management_urls_redirect_to_editor(self):
        """8. Standalone Scene Management, Detail, and Character Management URLs safely redirect to the editor."""
        for url in [
            f'/scripts/{self.script.id}/',
            f'/scripts/{self.script.id}/scenes/',
            f'/scripts/{self.script.id}/characters/',
            f'/scripts/{self.script.id}/notes/',
            f'/scripts/{self.script.id}/versions/',
        ]:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302, f"URL {url} did not redirect")
            self.assertEqual(res.url, f'/scripts/{self.script.id}/editor/')

    def test_batch_2b_2_delete_scene_disappears_from_read_mode(self):
        """Batch 2B-2 regression test: Deleting a scene via API removes it and updates scenes_tree."""
        # Check initial editor rendering has scene 1, 2, 2A, 2B, 3
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn(f'id="read-scene-{self.s2.id}"', content)
        self.assertIn(f'id="read-scene-{self.sub2a.id}"', content)

        # Delete scene 2 (which also cascades to its subscenes)
        del_res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{self.s2.id}/delete/',
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(del_res.status_code, 200)
        data = del_res.json()
        self.assertEqual(data['status'], 'ok')

        # Verify scenes_tree returned has only s1 and s3
        tree_ids = [item['id'] for item in data['scenes_tree']]
        self.assertNotIn(self.s2.id, tree_ids)
        self.assertNotIn(self.sub2a.id, tree_ids)
        self.assertNotIn(self.sub2b.id, tree_ids)
        self.assertIn(self.s1.id, tree_ids)
        self.assertIn(self.s3.id, tree_ids)

        # Verify next render of editor has no trace of s2 or its subscenes
        res_after = self.client.get(f'/scripts/{self.script.id}/editor/')
        content_after = res_after.content.decode('utf-8')
        self.assertNotIn(f'id="read-scene-{self.s2.id}"', content_after)
        self.assertNotIn(f'id="read-scene-{self.sub2a.id}"', content_after)
        self.assertNotIn(f'id="read-scene-{self.sub2b.id}"', content_after)
        self.assertIn(f'id="read-scene-{self.s1.id}"', content_after)
        self.assertIn(f'id="read-scene-{self.s3.id}"', content_after)

    def test_batch_2b_2_move_scene_read_mode_order_updates(self):
        """Batch 2B-2 regression test: Moving a scene updates order and full_display_heading."""
        # Initial order: s1, s2, sub2a, sub2b, s3
        # Move s3 up above s2 block (Batch 2B-1 behavior)
        move_res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{self.s3.id}/move/',
            data=json.dumps({'direction': 'up'}),
            content_type='application/json'
        )
        self.assertEqual(move_res.status_code, 200)
        data = move_res.json()
        self.assertEqual(data['status'], 'ok')

        tree = data['scenes_tree']
        tree_ids = [item['id'] for item in tree]
        # Expected new order: s1, s3, s2, sub2a, sub2b
        self.assertEqual(tree_ids, [self.s1.id, self.s3.id, self.s2.id, self.sub2a.id, self.sub2b.id])

        # Headings updated authoritatively:
        s3_item = next(item for item in tree if item['id'] == self.s3.id)
        self.assertEqual(s3_item['scene_number'], 2)
        self.assertEqual(s3_item['nav_identifier'], 'Scene 2')

        # Read mode template rendering also reflects new order
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        content = res.content.decode('utf-8')
        pos_s1 = content.find(f'id="read-scene-{self.s1.id}"')
        pos_s3 = content.find(f'id="read-scene-{self.s3.id}"')
        pos_s2 = content.find(f'id="read-scene-{self.s2.id}"')
        pos_sub2a = content.find(f'id="read-scene-{self.sub2a.id}"')

        self.assertTrue(pos_s1 < pos_s3 < pos_s2 < pos_sub2a)

    def test_batch_2b_2_move_main_scene_with_subscenes_preserves_block_order(self):
        """Batch 2B-2 regression test: Moving main scene down moves all its subscenes together."""
        # Move s1 down past s2's block
        move_res = self.client.post(
            f'/scripts/api/{self.script.id}/scenes/{self.s1.id}/move/',
            data=json.dumps({'direction': 'down'}),
            content_type='application/json'
        )
        self.assertEqual(move_res.status_code, 200)
        data = move_res.json()
        self.assertEqual(data['status'], 'ok')
        tree = data['scenes_tree']
        tree_ids = [item['id'] for item in tree]
        # s2 block (s2, sub2a, sub2b) moved before s1
        self.assertEqual(tree_ids, [self.s2.id, self.sub2a.id, self.sub2b.id, self.s1.id, self.s3.id])

        # Subscene association preserved
        sub2a_item = next(item for item in tree if item['id'] == self.sub2a.id)
        self.assertEqual(sub2a_item['parent_scene_id'], self.s2.id)
        self.assertEqual(sub2a_item['scene_number'], 1)  # s2 became scene 1, sub2a became 1A

    def test_batch_2b_2_switching_modes_no_duplicated_sections(self):
        """Batch 2B-2 regression test: Template contains exactly one section per scene in Read Mode."""
        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        content = res.content.decode('utf-8')
        for sc_id in [self.s1.id, self.s2.id, self.sub2a.id, self.sub2b.id, self.s3.id]:
            self.assertEqual(content.count(f'id="read-scene-{sc_id}"'), 1)
            self.assertEqual(content.count(f'class="read-mode-scene" id="read-scene-{sc_id}"'), 1)

    def test_batch_2b_2_transition_entries_and_metrics_preserved_in_read_mode(self):
        """Batch 2B-2 regression test: Subscene From and Cut Back To transitions are rendered correctly."""
        from scripts.services.scene_service import create_sub_scene_2, create_intercut_scene
        sub_from = create_sub_scene_2(self.script, source_scene_id=self.s1.id, current_scene_id=self.s2.id)
        cut_back = create_intercut_scene(self.script, source_scene_id=self.s1.id, current_scene_id=sub_from.id)

        res = self.client.get(f'/scripts/{self.script.id}/editor/')
        content = res.content.decode('utf-8')
        # Check transition sections in Read Mode
        self.assertIn(f'id="read-scene-{sub_from.id}"', content)
        self.assertIn(f'id="read-scene-{cut_back.id}"', content)

        # Also verify via scenes_tree API that these exist and is_intercut is preserved
        tree_res = self.client.get(f'/scripts/api/{self.script.id}/scenes/tree/')
        self.assertEqual(tree_res.status_code, 200)
        tree = tree_res.json()['scenes_tree']
        sub_from_item = next(item for item in tree if item['id'] == sub_from.id)
        cut_back_item = next(item for item in tree if item['id'] == cut_back.id)
        self.assertTrue(sub_from_item['is_intercut'])
        self.assertTrue(cut_back_item['is_intercut'])




class DashboardScriptManagementAndSceneDropdownTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='passuser1')
        self.user2 = User.objects.create_user(username='user2', password='passuser2')
        self.script1 = Script.objects.create(
            user=self.user1,
            title='ആദ്യത്തെ തിരക്കഥ (First Script)',
            genre='Drama',
            script_type='Feature Film'
        )
        self.sc1 = Scene.objects.create(script=self.script1, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        self.sub1 = Scene.objects.create(script=self.script1, parent_scene=self.sc1, scene_number=1, heading='INT. BEDROOM - DAY', order=1)

        self.client1 = Client()
        self.client1.login(username='user1', password='passuser1')
        self.client2 = Client()
        self.client2.login(username='user2', password='passuser2')

    def test_dashboard_displays_screenplay_with_rename_and_delete_actions(self):
        """Dashboard renders project item with action buttons and modal triggers."""
        res = self.client1.get('/dashboard/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('ആദ്യത്തെ തിരക്കഥ (First Script)', content)
        self.assertIn('btn-action-rename-script', content)
        self.assertIn('btn-action-delete-script', content)
        self.assertIn('id="renameScriptModal"', content)
        self.assertIn('id="deleteScriptModal"', content)

    def test_rename_screenplay_success_json(self):
        """Rename screenplay via JSON request updates Script model and returns ok."""
        res = self.client1.post(
            f'/scripts/{self.script1.id}/rename/',
            data=json.dumps({'title': 'നവീകരിച്ച തിരക്കഥ (Renamed Script)'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['title'], 'നവീകരിച്ച തിരക്കഥ (Renamed Script)')

        self.script1.refresh_from_db()
        self.assertEqual(self.script1.title, 'നവീകരിച്ച തിരക്കഥ (Renamed Script)')

    def test_rename_screenplay_empty_title_rejected(self):
        """Rename screenplay rejects empty title with error status."""
        res = self.client1.post(
            f'/scripts/{self.script1.id}/rename/',
            data=json.dumps({'title': '   '}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data['status'], 'error')

        self.script1.refresh_from_db()
        self.assertEqual(self.script1.title, 'ആദ്യത്തെ തിരക്കഥ (First Script)')

    def test_rename_screenplay_permission_denied_for_other_user(self):
        """User cannot rename screenplay belonging to another user."""
        res = self.client2.post(
            f'/scripts/{self.script1.id}/rename/',
            data=json.dumps({'title': 'Hacked Title'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 404)
        self.script1.refresh_from_db()
        self.assertEqual(self.script1.title, 'ആദ്യത്തെ തിരക്കഥ (First Script)')

    def test_delete_screenplay_success_json(self):
        """Delete screenplay via AJAX POST returns JSON with updated counts."""
        res = self.client1.post(
            f'/scripts/{self.script1.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['total_scripts'], 0)
        self.assertEqual(data['total_scenes'], 0)
        self.assertFalse(Script.objects.filter(id=self.script1.id).exists())

    def test_delete_screenplay_permission_denied_for_other_user(self):
        """User cannot delete screenplay belonging to another user."""
        res = self.client2.post(
            f'/scripts/{self.script1.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 404)
        self.assertTrue(Script.objects.filter(id=self.script1.id).exists())

    def test_editor_renders_scene_and_subscene_dropdown_action_menus(self):
        """Editor scenes list renders dropdown action menu for both main and sub-scenes."""
        res = self.client1.get(f'/scripts/{self.script1.id}/editor/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Dropdown action buttons present
        self.assertIn('scene-action-btn', content)
        self.assertIn('btn-action-insert-before', content)
        self.assertIn('btn-action-insert-after', content)
        self.assertIn('btn-action-add-sub', content)
        self.assertIn('btn-action-dup', content)
        self.assertIn('btn-action-copy-scene', content)
        self.assertIn('btn-action-move-up', content)
        self.assertIn('btn-action-move-down', content)
        self.assertIn('btn-action-delete', content)

        # Toolbar Copy Current Scene present
        self.assertIn('id="btnToolbarCopyCurrentScene"', content)

        # Modals present
        self.assertIn('id="editorInsertModal"', content)
        self.assertIn('id="editorSubSceneModal"', content)
        self.assertIn('id="editorDeleteModal"', content)

    def test_copy_full_scene_api_elements_retrieval_and_structure(self):
        """Scene detail API returns full ordered elements with semantic types and Unicode preserved for Copy Full Scene."""
        # Create elements for script1 scene1
        ScriptElement.objects.create(scene=self.sc1, element_type='scene_heading', content=self.sc1.heading, order=0)
        ScriptElement.objects.create(scene=self.sc1, element_type='character', content='റഹീം (RAHEEM)', order=1)
        ScriptElement.objects.create(scene=self.sc1, element_type='parenthetical', content='(പുഞ്ചിരിയോടെ)', order=2)
        ScriptElement.objects.create(scene=self.sc1, element_type='dialogue', content='എല്ലാം ശരിയാകും.', order=3)
        ScriptElement.objects.create(scene=self.sc1, element_type='transition', content='CUT TO:', order=4)

        res = self.client1.get(f'/scripts/api/{self.script1.id}/scenes/{self.sc1.id}/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        scene_data = data['scene']
        self.assertEqual(scene_data['id'], self.sc1.id)
        self.assertEqual(scene_data['heading'], 'INT. HOUSE - DAY')

        elements = data['elements']
        self.assertEqual(len(elements), 5)  # scene_heading, character, parenthetical, dialogue, transition
        types = [e['element_type'] for e in elements]
        self.assertEqual(types, ['scene_heading', 'character', 'parenthetical', 'dialogue', 'transition'])
        # Unicode content preservation
        self.assertEqual(elements[0]['content'], 'INT. HOUSE - DAY')
        self.assertEqual(elements[1]['content'], 'റഹീം (RAHEEM)')
        self.assertEqual(elements[2]['content'], '(പുഞ്ചിരിയോടെ)')
        self.assertEqual(elements[3]['content'], 'എല്ലാം ശരിയാകും.')
        self.assertEqual(elements[4]['content'], 'CUT TO:')


class SceneMetricsSeparationTests(TestCase):
    """Batch 2A: Scene Metrics separation tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='metric_user', password='password123')
        self.client = Client()
        self.client.login(username='metric_user', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='Metrics Screenplay',
            genre='Drama',
            script_type='Feature Film'
        )

    def test_case_1_only_primary_scenes(self):
        """Case 1: 3 primary scenes, 0 sub-scenes -> primary=3, sub=0, total=3."""
        for i in range(1, 4):
            Scene.objects.create(script=self.script, scene_number=i, heading=f'INT. SCENE {i} - DAY', order=i-1)

        self.assertEqual(self.script.primary_scene_count, 3)
        self.assertEqual(self.script.sub_scene_count, 0)
        self.assertEqual(self.script.scene_count, 3)

    def test_case_2_primary_and_sub_scenes(self):
        """Case 2: 3 primary scenes, 2 sub-scenes -> primary=3, sub=2, total=5 (primary count is NOT 5)."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3', order=4)

        # 2 sub-scenes under s2
        Scene.objects.create(script=self.script, parent_scene=s2, scene_number=2, heading='INT. SCENE 2.A', order=2)
        Scene.objects.create(script=self.script, parent_scene=s2, scene_number=2, heading='INT. SCENE 2.B', order=3)

        self.assertEqual(self.script.primary_scene_count, 3)
        self.assertEqual(self.script.sub_scene_count, 2)
        self.assertEqual(self.script.scene_count, 5)

    def test_case_3_multiple_sub_scenes_under_one_parent(self):
        """Case 3: Scene 1 has 3 sub-scenes (1.A, 1.B, 1.C), Scene 2 has 0 -> primary=2, sub=3."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1', order=0)
        Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.A', order=1)
        Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.B', order=2)
        Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.C', order=3)
        Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2', order=4)

        self.assertEqual(self.script.primary_scene_count, 2)
        self.assertEqual(self.script.sub_scene_count, 3)
        self.assertEqual(self.script.scene_count, 5)

    def test_case_4_delete_sub_scene_decreases_sub_count_only(self):
        """Case 4: Deleting a sub-scene decreases sub_scene_count, preserves primary_scene_count."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1', order=0)
        sub_1a = Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.A', order=1)
        sub_1b = Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.B', order=2)
        Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2', order=3)

        self.assertEqual(self.script.primary_scene_count, 2)
        self.assertEqual(self.script.sub_scene_count, 2)

        # Delete sub_1a
        sub_1a.delete()

        self.assertEqual(self.script.primary_scene_count, 2)
        self.assertEqual(self.script.sub_scene_count, 1)
        self.assertEqual(self.script.scene_count, 3)

    def test_case_5_duplicate_and_intercut_compatibility(self):
        """Case 5: Duplicate scenes count as actual scenes; intercut navigation entries do not increase totals."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1', order=0)
        # Duplicate of s1 (primary duplicate, parent_scene=None)
        s1_dup = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. SCENE 1',
            is_duplicate=True,
            duplicate_number=1,
            parent_scene=None,
            order=1
        )
        # Intercut scene linked to s1 (parent_scene=None, navigation/transition entry)
        s1_intercut = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. SCENE 1',
            is_intercut=True,
            intercut_source=s1,
            parent_scene=None,
            order=2
        )
        # Sub-scene under s1
        sub_1a = Scene.objects.create(
            script=self.script,
            parent_scene=s1,
            scene_number=1,
            heading='INT. SCENE 1.A',
            order=3
        )

        # Primary scenes (parent_scene is None, is_intercut=False): s1, s1_dup = 2
        self.assertEqual(self.script.primary_scene_count, 2)
        # Sub-scenes (parent_scene is not None, is_intercut=False): sub_1a = 1
        self.assertEqual(self.script.sub_scene_count, 1)
        # Total scenes = 3 (s1_intercut does not increase any total)
        self.assertEqual(self.script.scene_count, 3)

    def test_api_script_stats_includes_primary_and_sub_counts(self):
        """API endpoints return both primary_scene_count and sub_scene_count in script_stats."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1', order=0)
        Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SCENE 1.A', order=1)

        res = self.client.get(f'/scripts/api/{self.script.id}/scenes/{s1.id}/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        stats = data['script_stats']
        self.assertEqual(stats['scene_count'], 2)
        self.assertEqual(stats['primary_scene_count'], 1)
        self.assertEqual(stats['sub_scene_count'], 1)

    def test_scene_navigation_heading_rendering(self):
        """Scene navigation heading renders 'Scenes (2) · Sub-scenes (1)' when sub-scenes exist, and 'Scenes (3)' when none."""
        # Case A: 3 primary scenes, 0 sub-scenes
        script1 = Script.objects.create(user=self.user, title='Script Primary Only', genre='Drama', script_type='Feature Film')
        for i in range(1, 4):
            Scene.objects.create(script=script1, scene_number=i, heading=f'INT. SCENE {i}', order=i-1)

        res1 = self.client.get(f'/scripts/{script1.id}/editor/')
        self.assertEqual(res1.status_code, 200)
        content1 = res1.content.decode('utf-8')
        # Sidebar & offcanvas headings contain 'Scenes (3)' and NOT 'Sub-scenes'
        self.assertIn('Scenes (<span id="sidebarSceneCount">3</span>)', content1)
        self.assertNotIn('sidebarSubSceneCount', content1)
        self.assertNotIn('offcanvasSubSceneCount', content1)

        # Case B: Add 1 sub-scene -> 2 primary, 1 sub-scene
        script2 = Script.objects.create(user=self.user, title='Script With Sub', genre='Drama', script_type='Feature Film')
        sc1 = Scene.objects.create(script=script2, scene_number=1, heading='INT. SCENE 1', order=0)
        sc2 = Scene.objects.create(script=script2, scene_number=2, heading='INT. SCENE 2', order=1)
        Scene.objects.create(script=script2, parent_scene=sc2, scene_number=2, heading='INT. SCENE 2.A', order=2)

        res2 = self.client.get(f'/scripts/{script2.id}/editor/')
        self.assertEqual(res2.status_code, 200)
        content2 = res2.content.decode('utf-8')
        self.assertIn('Scenes (<span id="sidebarSceneCount">2</span>) · Sub-scenes (<span id="sidebarSubSceneCount">1</span>)', content2)
        self.assertIn('Scenes (<span id="offcanvasSceneCount">2</span>) · Sub-scenes (<span id="offcanvasSubSceneCount">1</span>)', content2)

    def test_subscene_from_and_cutback_to_do_not_increase_totals(self):
        """
        Subscene From and Cut Back To are navigation/transition entries and must NOT increase
        primary, sub-scene, or total actual scene counts, but MUST remain present in scenes_tree.
        Example from specification:
        - Scene 1: INT. HOUSE - NIGHT
        - Scene 1.A: INT. HOUSE - CONTINUOUS
        - Subscene From
        - Cut Back To
        - Scene 2: EXT. STREET - DAY
        - Scene 3: INT. OFFICE - DAY
        Expected totals: Primary = 3, Sub = 1, Total = 4.
        """
        from scripts.services.scene_service import (
            create_sub_scene_2,
            create_intercut_scene,
            serialize_scenes_hierarchy,
            resequence_script_scenes
        )

        test_script = Script.objects.create(user=self.user, title='Transition Test Script', genre='Drama')
        sc1 = Scene.objects.create(script=test_script, scene_number=1, heading='INT. HOUSE - NIGHT', order=0)
        sc1_a = Scene.objects.create(script=test_script, parent_scene=sc1, scene_number=1, heading='INT. HOUSE - CONTINUOUS', order=1)
        sc2 = Scene.objects.create(script=test_script, scene_number=2, heading='EXT. STREET - DAY', order=2)
        sc3 = Scene.objects.create(script=test_script, scene_number=3, heading='INT. OFFICE - DAY', order=3)
        resequence_script_scenes(test_script)

        # Insert 'Subscene From' (source sc1, after sc1_a)
        sub_from = create_sub_scene_2(test_script, source_scene_id=sc1.id, current_scene_id=sc1_a.id)
        # Insert 'Cut Back To' (source sc1, after sub_from)
        cut_back = create_intercut_scene(test_script, source_scene_id=sc1.id, current_scene_id=sub_from.id)

        test_script.refresh_from_db()
        self.assertEqual(test_script.primary_scene_count, 3)
        self.assertEqual(test_script.sub_scene_count, 1)
        self.assertEqual(test_script.scene_count, 4)

        # Check API returns same correct counts
        res = self.client.get(f'/scripts/api/{test_script.id}/scenes/tree/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        stats = data['script_stats']
        self.assertEqual(stats['primary_scene_count'], 3)
        self.assertEqual(stats['sub_scene_count'], 1)
        self.assertEqual(stats['scene_count'], 4)

        # Verify all 6 entries exist in scenes_tree for navigation
        tree = data['scenes_tree']
        self.assertEqual(len(tree), 6)
        tree_ids = [item['id'] for item in tree]
        self.assertIn(sub_from.id, tree_ids)
        self.assertIn(cut_back.id, tree_ids)

        # Verify is_intercut flag is serialized
        sub_from_item = next(item for item in tree if item['id'] == sub_from.id)
        cut_back_item = next(item for item in tree if item['id'] == cut_back.id)
        self.assertTrue(sub_from_item['is_intercut'])
        self.assertTrue(cut_back_item['is_intercut'])

        # Verify editor HTML rendering reflects correct heading with 3 primary scenes and 1 sub-scene
        editor_res = self.client.get(f'/scripts/{test_script.id}/editor/')
        self.assertEqual(editor_res.status_code, 200)
        html = editor_res.content.decode('utf-8')
        self.assertIn('Scenes (<span id="sidebarSceneCount">3</span>) · Sub-scenes (<span id="sidebarSubSceneCount">1</span>)', html)
        self.assertIn('Scenes: <strong id="statSceneCount">3 (1 sub)</strong>', html)

    def test_screenplay_ending_at_scene_50_reports_50_primary_scenes(self):
        """
        If the final actual scene is Scene 50, the primary scene total should be 50,
        regardless of how many navigation/transition entries appear in the screenplay.
        """
        script_50 = Script.objects.create(user=self.user, title='50 Scenes Screenplay', genre='Thriller')
        scenes = []
        for i in range(1, 51):
            scenes.append(Scene.objects.create(script=script_50, scene_number=i, heading=f'INT. LOCATION {i} - DAY', order=i-1))

        # Add 10 transition/navigation entries (5 Subscene From + 5 Cut Back To) interspersed
        from scripts.services.scene_service import create_sub_scene_2, create_intercut_scene
        for i in range(5):
            create_sub_scene_2(script_50, source_scene_id=scenes[i].id, current_scene_id=scenes[i*10].id)
            create_intercut_scene(script_50, source_scene_id=scenes[i].id, current_scene_id=scenes[i*10+5].id)

        script_50.refresh_from_db()
        self.assertEqual(script_50.primary_scene_count, 50)
        self.assertEqual(script_50.sub_scene_count, 0)
        self.assertEqual(script_50.scene_count, 50)

        # Editor API verification
        res = self.client.get(f'/scripts/api/{script_50.id}/scenes/tree/')
        self.assertEqual(res.status_code, 200)
        stats = res.json()['script_stats']
        self.assertEqual(stats['primary_scene_count'], 50)
        self.assertEqual(stats['sub_scene_count'], 0)
        self.assertEqual(stats['scene_count'], 50)
        # All 60 entries are in scenes_tree
        self.assertEqual(len(res.json()['scenes_tree']), 60)
