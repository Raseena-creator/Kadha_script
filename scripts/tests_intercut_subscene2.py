import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    create_sub_scene_2,
    create_intercut_scene,
    resequence_script_scenes
)

User = get_user_model()


class IntercutAndSubScene2Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='writer_test',
            email='writer@example.com',
            password='testpassword123'
        )
        self.client = Client()
        self.client.login(username='writer_test', password='testpassword123')
        self.script = Script.objects.create(
            user=self.user,
            title='Intercut Test Screenplay'
        )

        # Create scenes 1 to 5
        self.scene1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        self.scene2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        self.scene3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. OFFICE - DAY', order=2)
        self.scene4 = Scene.objects.create(script=self.script, scene_number=4, heading='EXT. BEACH - DUSK', order=3)
        self.scene5 = Scene.objects.create(script=self.script, scene_number=5, heading='INT. HOTEL - NIGHT', order=4)
        resequence_script_scenes(self.script)

    def test_sub_scene_2_creation_and_numbering(self):
        """
        Selecting Scene 2 while at Scene 5 creates Scene 2.A immediately after Scene 5.
        Scene 2 remains untouched at its original position.
        """
        sub_2a = create_sub_scene_2(self.script, source_scene_id=self.scene2.id, current_scene_id=self.scene5.id)
        
        self.scene2.refresh_from_db()
        self.scene5.refresh_from_db()
        sub_2a.refresh_from_db()

        self.assertEqual(sub_2a.parent_scene_id, self.scene2.id)
        self.assertTrue(sub_2a.is_sub_scene)
        self.assertTrue(sub_2a.is_intercut)
        self.assertEqual(sub_2a.display_number, 'Scene 2.A')
        self.assertEqual(sub_2a.heading, 'EXT. ROAD - NIGHT')
        self.assertEqual(sub_2a.clean_heading, 'EXT. ROAD - NIGHT')
        self.assertEqual(sub_2a.full_display_heading, 'Scene 2.A : EXT. ROAD - NIGHT')

        # Original Scene 2 unchanged
        self.assertEqual(self.scene2.display_number, 'Scene 2')
        self.assertEqual(self.scene2.order, 1)

        # Scene 5 precedes sub_2a in reading order
        ordered = self.script.get_ordered_scenes()
        ordered_ids = [s.id for s in ordered]
        self.assertEqual(ordered_ids, [self.scene1.id, self.scene2.id, self.scene3.id, self.scene4.id, self.scene5.id, sub_2a.id])

        # Create another Sub-Scene 2 for Scene 2 -> Scene 2.B
        sub_2b = create_sub_scene_2(self.script, source_scene_id=self.scene2.id, current_scene_id=sub_2a.id)
        sub_2b.refresh_from_db()
        self.assertEqual(sub_2b.display_number, 'Scene 2.B')

    def test_intercut_scene_creation(self):
        """
        Selecting Scene 2 while at Scene 5 creates an Intercut Scene 2 instance after Scene 5.
        It displays as 'Scene 2', retains heading/time/location, and does NOT become Scene 6 or Scene 2.A.
        """
        intercut_sc2 = create_intercut_scene(self.script, source_scene_id=self.scene2.id, current_scene_id=self.scene5.id)
        
        self.scene2.refresh_from_db()
        self.scene5.refresh_from_db()
        intercut_sc2.refresh_from_db()

        self.assertTrue(intercut_sc2.is_intercut)
        self.assertFalse(intercut_sc2.is_sub_scene)
        self.assertEqual(intercut_sc2.scene_number, 2)
        self.assertEqual(intercut_sc2.display_number, 'Scene 2')
        self.assertEqual(intercut_sc2.heading, 'EXT. ROAD - NIGHT')
        self.assertEqual(intercut_sc2.full_display_heading, 'Scene 2 : EXT. ROAD - NIGHT')

        # Ordered check: Scene 1, Scene 2, Scene 3, Scene 4, Scene 5, Scene 2 (intercut instance)
        ordered = self.script.get_ordered_scenes()
        self.assertEqual([s.display_number for s in ordered], ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 4', 'Scene 5', 'Scene 2'])

    def test_malayalam_heading_intercut(self):
        """
        Intercut and Sub-Scene 2 retain Malayalam headings and locations.
        """
        mal_scene = Scene.objects.create(script=self.script, scene_number=6, heading='INT. വീട് - NIGHT', order=5)
        resequence_script_scenes(self.script)

        intercut_mal = create_intercut_scene(self.script, source_scene_id=mal_scene.id, current_scene_id=self.scene5.id)
        self.assertEqual(intercut_mal.display_number, 'Scene 6')
        self.assertEqual(intercut_mal.clean_heading, 'INT. വീട് - NIGHT')
        self.assertEqual(intercut_mal.full_display_heading, 'Scene 6 : INT. വീട് - NIGHT')

    def test_api_subscene_2_and_intercut_endpoints(self):
        """
        Test POST /scripts/api/<script_id>/scenes/subscene-2/ and /scripts/api/<script_id>/scenes/intercut/
        """
        res1 = self.client.post(
            reverse('api_create_sub_scene_2', args=[self.script.id]),
            data=json.dumps({
                'source_scene_id': self.scene2.id,
                'current_scene_id': self.scene5.id
            }),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1['status'], 'ok')
        self.assertEqual(data1['scene']['scene_identifier'], 'Scene 2.A')

        res2 = self.client.post(
            reverse('api_create_intercut', args=[self.script.id]),
            data=json.dumps({
                'source_scene_id': self.scene1.id,
                'current_scene_id': self.scene5.id
            }),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2['status'], 'ok')
        self.assertEqual(data2['scene']['scene_identifier'], 'Scene 1')
