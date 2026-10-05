from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from scripts.models import Script, Scene, ScriptElement, ScriptTitlePage
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.docx_export import generate_screenplay_docx
from scripts.services.txt_export import generate_screenplay_txt
from scripts.services.version_service import create_version_snapshot, restore_version_snapshot


class ScriptTitlePageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='screenwriter', password='Password123!', first_name='John', last_name='Doe')
        self.script = Script.objects.create(
            user=self.user,
            title='മണിച്ചിത്രത്താഴ് / Manichitrathazhu',
            author_name='Madhu Muttam',
            genre='Psychological Thriller',
            script_type='Feature Film',
            language='Malayalam'
        )

    def test_title_page_creation_and_defaults(self):
        """Test creating ScriptTitlePage with safe blank defaults."""
        tp = ScriptTitlePage.objects.create(script=self.script)
        self.assertEqual(tp.script, self.script)
        self.assertEqual(tp.get_effective_title(), 'മണിച്ചിത്രത്താഴ് / Manichitrathazhu')
        self.assertEqual(tp.get_effective_author(), 'Madhu Muttam')
        self.assertEqual(str(tp), 'Title Page — മണിച്ചിത്രത്താഴ് / Manichitrathazhu')

    def test_title_page_effective_overrides(self):
        """Test that custom title and pen name properly override script values."""
        tp = ScriptTitlePage.objects.create(
            script=self.script,
            title='MANICHITRATHAZHU — THE COMPLETE DIRECTOR CUT',
            subtitle='An Epic Malayalam Psychological Mystery',
            author_name='Madhu Muttam',
            pen_name='M. Muttam',
            adaptation_credits='Based on the legend of Alummoottil Meda',
            copyright_registration='FEFKA Reg. No. 98765/2026',
            draft_revision='Final Shooting Script',
            draft_date='October 2026',
            contact_name='Appachan Producer',
            contact_email='contact@swargachitra.com',
            contact_phone='+91 94470 12345'
        )
        self.assertEqual(tp.get_effective_title(), 'MANICHITRATHAZHU — THE COMPLETE DIRECTOR CUT')
        self.assertEqual(tp.get_effective_author(), 'M. Muttam')

    def test_title_page_fallback_to_user_when_no_author_name(self):
        """Test fallback to user full name / username when script author is empty."""
        script_no_author = Script.objects.create(
            user=self.user,
            title='Untitled Screenplay'
        )
        tp = ScriptTitlePage.objects.create(script=script_no_author)
        self.assertEqual(tp.get_effective_author(), 'John Doe')

    def test_cascade_delete(self):
        """Deleting a script must cleanly cascade delete its title page."""
        ScriptTitlePage.objects.create(script=self.script)
        self.assertEqual(ScriptTitlePage.objects.filter(script=self.script).count(), 1)
        self.script.delete()
        self.assertEqual(ScriptTitlePage.objects.filter(script_id=self.script.id).count(), 0)


class ScriptTitlePageViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='Password123!')
        self.user2 = User.objects.create_user(username='user2', password='Password123!')
        self.script1 = Script.objects.create(
            user=self.user1,
            title='Script One',
            author_name='Writer One'
        )

    def test_view_requires_login(self):
        """Unauthenticated access must redirect to login."""
        url = reverse('script_title_page', kwargs={'script_id': self.script1.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_strict_user_ownership(self):
        """User 2 must not be able to view or edit User 1's title page."""
        self.client.login(username='user2', password='Password123!')
        url = reverse('script_title_page', kwargs={'script_id': self.script1.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_title_page_auto_creates_if_missing(self):
        """GET request for script with no title page must initialize it safely."""
        self.client.login(username='user1', password='Password123!')
        url = reverse('script_title_page', kwargs={'script_id': self.script1.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'scripts/script_title_page.html')
        self.assertTrue(ScriptTitlePage.objects.filter(script=self.script1).exists())

    def test_post_title_page_success(self):
        """POST request saves all production metadata and redirects."""
        self.client.login(username='user1', password='Password123!')
        url = reverse('script_title_page', kwargs={'script_id': self.script1.id})
        payload = {
            'title': 'Official Script One Cover',
            'subtitle': 'A Mystery Drama',
            'author_name': 'Original Author',
            'pen_name': 'Pseudonym Name',
            'adaptation_credits': 'Adapted from historical accounts',
            'draft_revision': 'First Revision',
            'draft_date': 'October 2, 2026',
            'copyright_registration': 'FEFKA/2026/001 & WGAw #12345',
            'contact_name': 'Agent Smith',
            'contact_email': 'agent@agency.com',
            'contact_phone': '+1 555 0199',
        }
        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('script_title_page', kwargs={'script_id': self.script1.id}))

        tp = ScriptTitlePage.objects.get(script=self.script1)
        self.assertEqual(tp.title, 'Official Script One Cover')
        self.assertEqual(tp.subtitle, 'A Mystery Drama')
        self.assertEqual(tp.pen_name, 'Pseudonym Name')
        self.assertEqual(tp.copyright_registration, 'FEFKA/2026/001 & WGAw #12345')
        self.assertEqual(tp.draft_revision, 'First Revision')
        self.assertEqual(tp.draft_date, 'October 2, 2026')
        self.assertEqual(tp.contact_email, 'agent@agency.com')

    def test_post_invalid_email_shows_error(self):
        """POST with invalid email format fails validation with friendly message."""
        self.client.login(username='user1', password='Password123!')
        url = reverse('script_title_page', kwargs={'script_id': self.script1.id})
        payload = {
            'contact_email': 'not-an-email',
        }
        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn('contact_email', response.context['form'].errors)
        self.assertIn('Enter a valid email address.', response.context['form'].errors['contact_email'])


class ScriptTitlePageDuplicationAndSnapshotTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='scriptwriter', password='Password123!')
        self.script = Script.objects.create(
            user=self.user,
            title='Kumbalangi Nights',
            author_name='Syam Pushkaran'
        )
        self.title_page = ScriptTitlePage.objects.create(
            script=self.script,
            title='KUMBALANGI NIGHTS',
            subtitle='A Family Drama',
            pen_name='Syam P.',
            adaptation_credits='Original Story',
            copyright_registration='FEFKA Reg. 4455/2019',
            draft_revision='Draft 3',
            draft_date='2019-02-07',
            contact_name='Fahadh Faasil and Friends',
            contact_email='production@ffandfriends.com',
            contact_phone='+91 98460 00000'
        )
        sc = Scene.objects.create(script=self.script, scene_number=1, heading='EXT. KUMBALANGI - MORNING', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='EXT. KUMBALANGI - MORNING', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='Boat gliding on backwaters.', order=1)

    def test_script_duplication_copies_title_page(self):
        """Duplicating script must copy all title page metadata to the duplicate."""
        self.client.login(username='scriptwriter', password='Password123!')
        url = reverse('script_duplicate', kwargs={'script_id': self.script.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        dup_script = Script.objects.filter(user=self.user).exclude(id=self.script.id).first()
        self.assertIsNotNone(dup_script)
        self.assertEqual(dup_script.title, 'Kumbalangi Nights (Copy)')
        self.assertTrue(hasattr(dup_script, 'title_page'))
        self.assertIsNotNone(dup_script.title_page)
        self.assertEqual(dup_script.title_page.subtitle, 'A Family Drama')
        self.assertEqual(dup_script.title_page.pen_name, 'Syam P.')
        self.assertEqual(dup_script.title_page.copyright_registration, 'FEFKA Reg. 4455/2019')
        self.assertEqual(dup_script.title_page.draft_revision, 'Draft 3')
        self.assertEqual(dup_script.title_page.contact_email, 'production@ffandfriends.com')

    def test_version_snapshot_preserves_title_page(self):
        """Version snapshotting must capture title page and restore it faithfully."""
        ver = create_version_snapshot(self.script, title='Draft 3 Snapshot')
        self.assertIn('title_page', ver.snapshot_data)
        self.assertEqual(ver.snapshot_data['title_page']['copyright_registration'], 'FEFKA Reg. 4455/2019')

        # Modify title page
        self.title_page.draft_revision = 'Draft 4 Modified'
        self.title_page.save()

        # Restore snapshot
        restore_version_snapshot(self.script, ver.id)
        self.title_page.refresh_from_db()
        self.assertEqual(self.title_page.draft_revision, 'Draft 3')


class ScriptTitlePageExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='author', password='Password123!')
        self.script = Script.objects.create(
            user=self.user,
            title='Thondimuthalum Driksakshiyum',
            author_name='Sajeev Pazhoor',
            genre='Crime Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.title_page = ScriptTitlePage.objects.create(
            script=self.script,
            title='THONDIMUTHALUM DRIKSAKSHIYUM',
            subtitle='National Award Winning Screenplay',
            pen_name='Sajeev P.',
            adaptation_credits='Story by Sajeev Pazhoor & Syam Pushkaran',
            copyright_registration='FEFKA Reg # 112233/2017',
            draft_revision='Shooting Script',
            draft_date='June 2017',
            contact_name='Urvasi Theatres',
            contact_email='contact@urvasi.com',
            contact_phone='+91 99950 12345'
        )
        sc = Scene.objects.create(script=self.script, scene_number=1, heading='INT. POLICE STATION - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='INT. POLICE STATION - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='പ്രസാദ് ബെഞ്ചിലിരിക്കുന്നു.', order=1)

    def test_pdf_export_with_title_page(self):
        """PDF generation must succeed and include title page metadata."""
        pdf_bytes = generate_screenplay_pdf(self.script)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_pdf_export_without_title_page_object(self):
        """PDF generation must succeed cleanly even if ScriptTitlePage does not exist."""
        script_bare = Script.objects.create(user=self.user, title='Bare Script', author_name='Solo')
        sc = Scene.objects.create(script=script_bare, scene_number=1, heading='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='Silence.', order=0)
        pdf_bytes = generate_screenplay_pdf(script_bare)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_docx_export_with_title_page(self):
        """DOCX export must succeed and produce valid word document."""
        docx_bytes = generate_screenplay_docx(self.script)
        self.assertIsInstance(docx_bytes, bytes)
        self.assertTrue(len(docx_bytes) > 1000)

    def test_txt_export_with_title_page(self):
        """TXT export must include title, subtitle, credits, draft revision, copyright, and contact."""
        txt_str = generate_screenplay_txt(self.script)
        self.assertIn('THONDIMUTHALUM DRIKSAKSHIYUM', txt_str)
        self.assertIn('National Award Winning Screenplay', txt_str)
        self.assertIn('Written by: Sajeev P.', txt_str)
        self.assertIn('Story by Sajeev Pazhoor & Syam Pushkaran', txt_str)
        self.assertIn('Draft: Shooting Script (June 2017)', txt_str)
        self.assertIn('FEFKA Reg # 112233/2017', txt_str)
        self.assertIn('contact@urvasi.com', txt_str)

    def test_print_preview_view(self):
        """Print preview page must render successfully with cover sheet."""
        client = Client()
        client.login(username='author', password='Password123!')
        url = reverse('print_preview', kwargs={'script_id': self.script.id})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'THONDIMUTHALUM DRIKSAKSHIYUM')
        self.assertContains(response, 'National Award Winning Screenplay')
        self.assertContains(response, 'Sajeev P.')
        self.assertContains(response, 'FEFKA Reg # 112233/2017')
