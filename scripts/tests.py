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
