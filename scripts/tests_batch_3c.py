import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from scripts.models import (
    Script, Scene, ScriptElement, Character, ScriptNote, ScriptVersion, ScriptTitlePage
)

User = get_user_model()


class Batch3CProjectTrashTests(TestCase):
    """
    Batch 3C Test Suite: Project Trash Listing and Navigation.
    Verifies that:
    1. Unauthenticated requests to /scripts/trash/ redirect to login with next=/scripts/trash/.
    2. Authenticated users can open the Trash page (HTTP 200).
    3. A user sees only their own trashed projects.
    4. A user cannot see another user's trashed projects.
    5. Active projects (is_deleted=False) do not appear in Trash.
    6. The empty state renders when the user has no trashed projects.
    7. The displayed deletion timestamp is accurate and rendered when available.
    8. The page does not expose screenplay dialogue, scene content, or private notes.
    9. Visiting the Trash page is strictly read-only and does not mutate project or scene deletion state.
    10. The Trash navigation URL name ('script_trash') resolves to '/scripts/trash/'.
    11. Existing dashboard and normal project-list behavior continue to exclude trashed projects.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='trash_writer',
            email='trash_writer@example.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            username='other_writer',
            email='other_writer@example.com',
            password='Password123!'
        )

        # User's active script
        self.active_script = Script.objects.create(
            user=self.user,
            title='ജീവിക്കുന്ന തിരക്കഥ (Active Script)',
            description='Active description',
            genre='Drama',
            script_type='Feature Film',
            is_deleted=False
        )
        self.active_scene = Scene.objects.create(
            script=self.active_script,
            scene_number=1,
            heading='INT. ACTIVE ROOM - DAY',
            order=0,
            is_deleted=False
        )
        self.active_elem = ScriptElement.objects.create(
            scene=self.active_scene,
            element_type='action',
            content='Active action content text.',
            order=0
        )

        # User's trashed script
        self.deletion_time = timezone.now()
        self.trashed_script = Script.objects.create(
            user=self.user,
            title='മറന്നുപോയ കഥ (Trashed Script)',
            description='Trashed description',
            genre='Thriller',
            script_type='Short Film',
            is_deleted=True,
            deleted_at=self.deletion_time
        )
        self.trashed_scene = Scene.objects.create(
            script=self.trashed_script,
            scene_number=1,
            heading='INT. SECRET TRASHED LOCATION - NIGHT',
            order=0,
            is_deleted=False
        )
        self.trashed_elem = ScriptElement.objects.create(
            scene=self.trashed_scene,
            element_type='dialogue',
            content='CONFIDENTIAL_TRASHED_DIALOGUE_TEXT_12345',
            order=0
        )
        self.trashed_note = ScriptNote.objects.create(
            script=self.trashed_script,
            title='Confidential Idea Note',
            content='SECRET_PRIVATE_NOTE_CONTENT_67890'
        )

        # Other user's trashed script
        self.other_trashed_script = Script.objects.create(
            user=self.other_user,
            title='മറ്റൊരാളുടെ രഹസ്യം (Other User Trashed Script)',
            description='Other user trashed description',
            genre='Horror',
            script_type='Web Series',
            is_deleted=True,
            deleted_at=timezone.now()
        )

    def test_1_unauthenticated_request_redirects_to_login(self):
        """Unauthenticated request redirects to the login page with next=/scripts/trash/."""
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 302)
        expected_url = f"{reverse('login')}?next={reverse('script_trash')}"
        self.assertRedirects(response, expected_url)

    def test_2_authenticated_user_can_access_trash_page(self):
        """An authenticated user can successfully open the Trash page (HTTP 200)."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'scripts/script_trash.html')
        self.assertContains(response, 'Trash')
        self.assertContains(response, 'Back to Dashboard')
        self.assertContains(response, 'Retention Policy')

    def test_3_user_sees_own_trashed_projects(self):
        """A user sees their own trashed projects with metadata."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'മറന്നുപോയ കഥ (Trashed Script)')
        self.assertContains(response, 'Short Film')
        self.assertContains(response, 'Thriller')
        self.assertEqual(response.context['total_trashed'], 1)

    def test_4_user_cannot_see_other_user_trashed_projects(self):
        """A user cannot see another user's trashed projects."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'മറ്റൊരാളുടെ രഹസ്യം (Other User Trashed Script)')

        # Login as other user and verify isolation
        self.client.force_login(self.other_user)
        other_response = self.client.get(reverse('script_trash'))
        self.assertEqual(other_response.status_code, 200)
        self.assertContains(other_response, 'മറ്റൊരാളുടെ രഹസ്യം (Other User Trashed Script)')
        self.assertNotContains(other_response, 'മറന്നുപോയ കഥ (Trashed Script)')

    def test_5_active_projects_do_not_appear_in_trash(self):
        """Active projects (is_deleted=False) never appear in the Trash listing."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ജീവിക്കുന്ന തിരക്കഥ (Active Script)')

    def test_6_empty_state_renders_when_no_trashed_projects(self):
        """The empty state renders cleanly when the user has no trashed projects."""
        # Create a fresh writer with zero trashed projects
        fresh_user = User.objects.create_user(
            username='empty_trash_writer',
            email='empty@example.com',
            password='Password123!'
        )
        self.client.force_login(fresh_user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your Trash is empty.')
        self.assertEqual(response.context['total_trashed'], 0)
        self.assertContains(response, 'Back to Dashboard')

    def test_7_displayed_deletion_timestamp_is_accurate(self):
        """The displayed deletion timestamp corresponds to deleted_at when available."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        formatted_date = self.deletion_time.strftime("%b %d, %Y")
        self.assertContains(response, formatted_date)

    def test_8_page_does_not_expose_screenplay_content_or_notes(self):
        """The Trash listing does not leak screenplay dialogue, action, or private notes."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)
        # Verify private elements/notes are not present in response HTML
        self.assertNotContains(response, 'CONFIDENTIAL_TRASHED_DIALOGUE_TEXT_12345')
        self.assertNotContains(response, 'SECRET_PRIVATE_NOTE_CONTENT_67890')
        self.assertNotContains(response, 'Active action content text.')

    def test_9_visiting_trash_page_does_not_mutate_database(self):
        """Visiting the Trash page is strictly read-only and leaves all records untouched."""
        self.client.force_login(self.user)

        pre_trashed_count = Script.objects.filter(user=self.user, is_deleted=True).count()
        pre_active_count = Script.objects.filter(user=self.user, is_deleted=False).count()

        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)

        # Refresh instances from database
        self.trashed_script.refresh_from_db()
        self.active_script.refresh_from_db()

        self.assertTrue(self.trashed_script.is_deleted)
        self.assertEqual(self.trashed_script.deleted_at, self.deletion_time)
        self.assertFalse(self.active_script.is_deleted)

        post_trashed_count = Script.objects.filter(user=self.user, is_deleted=True).count()
        post_active_count = Script.objects.filter(user=self.user, is_deleted=False).count()
        self.assertEqual(pre_trashed_count, post_trashed_count)
        self.assertEqual(pre_active_count, post_active_count)

    def test_10_trash_navigation_url_resolves_and_appears_in_templates(self):
        """The 'script_trash' URL resolves to /scripts/trash/ and appears in dashboard and base navigation."""
        self.assertEqual(reverse('script_trash'), '/scripts/trash/')

        self.client.force_login(self.user)
        # Dashboard includes Trash link
        dash_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_response.status_code, 200)
        self.assertContains(dash_response, '/scripts/trash/')

        # Script list page inherits base.html which includes user dropdown Trash link
        list_response = self.client.get(reverse('script_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, '/scripts/trash/')

    def test_11_dashboard_and_script_list_continue_to_exclude_trashed_projects(self):
        """Existing dashboard and script_list views continue to exclude trashed projects."""
        self.client.force_login(self.user)

        # Dashboard view
        dash_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_response.status_code, 200)
        self.assertEqual(dash_response.context['total_scripts'], 1)
        self.assertContains(dash_response, 'ജീവിക്കുന്ന തിരക്കഥ (Active Script)')
        self.assertNotContains(dash_response, 'മറന്നുപോയ കഥ (Trashed Script)')

        # Script list view
        list_response = self.client.get(reverse('script_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.context['total_count'], 1)
        self.assertContains(list_response, 'ജീവിക്കുന്ന തിരക്കഥ (Active Script)')
        self.assertNotContains(list_response, 'മറന്നുപോയ കഥ (Trashed Script)')
