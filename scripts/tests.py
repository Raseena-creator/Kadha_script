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
