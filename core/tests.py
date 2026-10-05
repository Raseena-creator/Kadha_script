from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from scripts.models import Script, Scene, ScriptElement

class DashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='dashboard_user', password='password123')
        
        # Script 1 with 3 scenes
        self.script1 = Script.objects.create(
            user=self.user,
            title='Kochi Maharaja',
            genre='Drama',
            script_type='Feature Film'
        )
        for i in range(1, 4):
            Scene.objects.create(script=self.script1, scene_number=i, heading=f'INT. SCENE {i} - DAY', order=i)

        # Script 2 with 1 scene
        self.script2 = Script.objects.create(
            user=self.user,
            title='Aaranyam',
            genre='Thriller',
            script_type='Short Film'
        )
        Scene.objects.create(script=self.script2, scene_number=1, heading='EXT. FOREST - NIGHT', order=1)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_view_content(self):
        self.client.login(username='dashboard_user', password='password123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        # Context metrics
        self.assertEqual(response.context['total_scripts'], 2)
        self.assertEqual(response.context['total_scenes'], 4)

        content = response.content.decode('utf-8')

        # Top Action
        self.assertIn('New Screenplay', content)

        # Metrics
        self.assertIn('Total Projects', content)
        self.assertIn('Total SCENES', content)

        # Script items
        self.assertIn('Kochi Maharaja', content)
        self.assertIn('3 SCENES', content)
        self.assertIn('Aaranyam', content)
        self.assertIn('1 SCENE', content)
        self.assertNotIn('1 SCENES', content)

        # Direct navigation to editor
        editor_url_1 = reverse('script_editor', args=[self.script1.id])
        editor_url_2 = reverse('script_editor', args=[self.script2.id])
        self.assertIn(f'href="{editor_url_1}"', content)
        self.assertIn(f'href="{editor_url_2}"', content)

        # Ensure NO dashboard "Heading" button
        self.assertNotIn('btn-heading', content)
        self.assertNotIn('>Heading</button>', content)
        self.assertNotIn('>Heading</a>', content)
