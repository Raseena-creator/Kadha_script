import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from scripts.models import Script, Scene, ScriptElement


class ScriptWatermarkModelAndAPITests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='writer_a', password='password123')
        self.user_b = User.objects.create_user(username='writer_b', password='password123')

        self.client_a = Client()
        self.client_a.login(username='writer_a', password='password123')

        self.client_b = Client()
        self.client_b.login(username='writer_b', password='password123')

        self.unauth_client = Client()

        self.script_a = Script.objects.create(
            user=self.user_a,
            title='ആനന്ദം (Anandam)',
            description='A beautiful screenplay',
            genre='Drama',
            script_type='Feature Film',
            author_name='Raseena'
        )

    def test_01_new_script_instance_default_watermark_is_empty(self):
        """1. New Script instances must have watermark == '' by default."""
        new_script = Script.objects.create(
            user=self.user_a,
            title='പുതിയ തിരക്കഥ (New Screenplay)'
        )
        self.assertEqual(new_script.watermark, '')

    def test_02_english_watermark_saves_correctly(self):
        """2. English watermark 'CONFIDENTIAL DRAFT' saves correctly on the model."""
        self.script_a.watermark = 'CONFIDENTIAL DRAFT'
        self.script_a.save(update_fields=['watermark', 'updated_at'])
        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, 'CONFIDENTIAL DRAFT')

    def test_03_malayalam_watermark_saves_correctly(self):
        """3. Malayalam Unicode watermark e.g. 'രഹസ്യ രേഖ' saves correctly."""
        malayalam_text = 'രഹസ്യ രേഖ'
        self.script_a.watermark = malayalam_text
        self.script_a.save(update_fields=['watermark', 'updated_at'])
        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, malayalam_text)

    def test_04_api_strips_leading_and_trailing_whitespace(self):
        """4. Whitespace is stripped via API: '  CONFIDENTIAL  ' -> 'CONFIDENTIAL'."""
        url = reverse('script_watermark', args=[self.script_a.id])
        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': '   CONFIDENTIAL   '}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['watermark'], 'CONFIDENTIAL')
        self.assertEqual(data['script_id'], self.script_a.id)

        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, 'CONFIDENTIAL')

    def test_05_empty_or_whitespace_only_watermark_clears_value(self):
        """5. Empty, None, or whitespace-only watermark clears value to ''."""
        # First set a watermark
        self.script_a.watermark = 'INITIAL DRAFT'
        self.script_a.save(update_fields=['watermark'])

        url = reverse('script_watermark', args=[self.script_a.id])

        # Whitespace-only string
        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': '     '}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['watermark'], '')
        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, '')

        # None value
        self.script_a.watermark = 'ANOTHER DRAFT'
        self.script_a.save(update_fields=['watermark'])

        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': None}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['watermark'], '')
        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, '')

    def test_06_authenticated_owner_can_post_json_and_form_encoded(self):
        """6. Authenticated owner can POST via JSON and form-data to update watermark."""
        url = reverse('script_watermark', args=[self.script_a.id])

        # JSON format
        res_json = self.client_a.post(
            url,
            data=json.dumps({'watermark': 'FIRST DRAFT'}),
            content_type='application/json'
        )
        self.assertEqual(res_json.status_code, 200)
        self.assertEqual(res_json.json()['watermark'], 'FIRST DRAFT')

        # Form-encoded format
        res_form = self.client_a.post(
            url,
            data={'watermark': 'SECOND DRAFT'}
        )
        self.assertEqual(res_form.status_code, 200)
        self.assertEqual(res_form.json()['watermark'], 'SECOND DRAFT')

        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, 'SECOND DRAFT')

    def test_07_authenticated_owner_can_clear_watermark(self):
        """7. Authenticated owner can clear the watermark using empty string."""
        self.script_a.watermark = 'SECRET_VERSION'
        self.script_a.save(update_fields=['watermark'])

        url = reverse('script_watermark', args=[self.script_a.id])
        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': ''}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['watermark'], '')

        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, '')

    def test_08_unauthenticated_access_follows_login_behavior(self):
        """8. Unauthenticated access follows login redirect behavior."""
        url = reverse('script_watermark', args=[self.script_a.id])
        res = self.unauth_client.post(
            url,
            data=json.dumps({'watermark': 'HACK'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn('/accounts/login/', res.url)

    def test_09_user_b_cannot_modify_user_a_screenplay(self):
        """9. User B cannot modify User A's screenplay (404 from get_user_script)."""
        self.script_a.watermark = 'ORIGINAL WATERMARK'
        self.script_a.save(update_fields=['watermark'])

        url = reverse('script_watermark', args=[self.script_a.id])
        res = self.client_b.post(
            url,
            data=json.dumps({'watermark': 'UNAUTHORIZED OVERWRITE'}),
            content_type='application/json'
        )
        # get_user_script uses get_object_or_404(Script, id=script_id, user=user, is_deleted=False)
        self.assertEqual(res.status_code, 404)

        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.watermark, 'ORIGINAL WATERMARK')

    def test_10_existing_screenplay_data_unaffected(self):
        """10. Updating watermark does not affect scenes, elements, title, or metadata."""
        scene = Scene.objects.create(
            script=self.script_a,
            scene_number=1,
            heading='INT. HOUSE - DAY',
            order=0
        )
        element = ScriptElement.objects.create(
            scene=scene,
            element_type='action',
            content='Characters talking in the living room.',
            order=0
        )

        url = reverse('script_watermark', args=[self.script_a.id])
        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': 'WATERMARK TEST'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        self.script_a.refresh_from_db()
        self.assertEqual(self.script_a.title, 'ആനന്ദം (Anandam)')
        self.assertEqual(self.script_a.description, 'A beautiful screenplay')
        self.assertEqual(self.script_a.genre, 'Drama')
        self.assertEqual(self.script_a.author_name, 'Raseena')
        self.assertEqual(self.script_a.scenes.count(), 1)
        self.assertEqual(self.script_a.scenes.first().elements.count(), 1)
        self.assertEqual(self.script_a.scenes.first().elements.first().content, 'Characters talking in the living room.')

    def test_11_unsupported_http_methods_rejected(self):
        """11. GET, PUT, DELETE methods return 405 Method Not Allowed."""
        url = reverse('script_watermark', args=[self.script_a.id])

        res_get = self.client_a.get(url)
        self.assertEqual(res_get.status_code, 405)

        res_delete = self.client_a.delete(url)
        self.assertEqual(res_delete.status_code, 405)

    def test_12_watermark_length_validation(self):
        """12. Watermark text exceeding 255 characters returns 400 bad request."""
        url = reverse('script_watermark', args=[self.script_a.id])
        too_long = 'A' * 256
        res = self.client_a.post(
            url,
            data=json.dumps({'watermark': too_long}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('cannot exceed 255 characters', data['message'])

    def test_13_dashboard_renders_watermark_action_and_modal(self):
        """13. Dashboard contains Watermark button in dropdown and reusable modal."""
        res = self.client_a.get(reverse('dashboard'))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        # Dropdown action
        self.assertIn('btn-action-watermark-script', html)
        self.assertIn('Watermark', html)
        self.assertIn(f'data-id="{self.script_a.id}"', html)
        self.assertIn('data-watermark=""', html)

        # Modal elements
        self.assertIn('id="watermarkScriptModal"', html)
        self.assertIn('id="watermarkModalScriptTitle"', html)
        self.assertIn('id="watermarkTextInput"', html)
        self.assertIn('id="watermarkCharCount"', html)
        self.assertIn('id="watermarkPreviewSheet"', html)
        self.assertIn('id="watermarkPreviewOverlay"', html)
        self.assertIn('id="btnRemoveWatermark"', html)
        self.assertIn('id="btnSubmitWatermark"', html)

    def test_14_dashboard_renders_existing_watermark_in_data_attribute(self):
        """14. Existing watermark on script is rendered in data-watermark attribute."""
        self.script_a.watermark = 'CONFIDENTIAL DRAFT'
        self.script_a.save(update_fields=['watermark'])

        res = self.client_a.get(reverse('dashboard'))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn('data-watermark="CONFIDENTIAL DRAFT"', html)

    def test_15_dashboard_preserves_unrelated_actions(self):
        """15. Existing card actions (Rename, Export PDF, Export DOCX, Delete) are intact."""
        res = self.client_a.get(reverse('dashboard'))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn('btn-action-rename-script', html)
        self.assertIn('btn-action-delete-script', html)
        self.assertIn('Export PDF', html)
        self.assertIn('Export Word (.docx)', html)


class PrintPreviewWatermarkTests(TestCase):
    """Focused tests for KadhaScript Print Preview custom watermark (Phase 5)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='print_wm_user',
            password='password123'
        )
        self.client = Client()
        self.client.login(username='print_wm_user', password='password123')

        self.script = Script.objects.create(
            user=self.user,
            title='മലയാളം തിരക്കഥ (Screenplay)',
            genre='Drama',
            script_type='Feature Film',
            author_name='Raseena',
            watermark=''
        )
        self.scene = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. COURTYARD - DAY',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='action',
            content='മഴ ശക്തമായി പെയ്യുന്നു.',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='character',
            content='RAVI',
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='parenthetical',
            content='softly',
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='dialogue',
            content='നമുക്ക് പോകാം.',
            order=3
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='shot',
            content='WIDE SHOT ON GATE',
            order=4
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type='transition',
            content='CUT TO:',
            order=5
        )

    def test_01_english_watermark_appears_in_print_preview(self):
        """1. English watermark appears in print-preview HTML when configured."""
        self.script.watermark = 'CONFIDENTIAL DRAFT'
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn(
            '<div class="sp-watermark font-malayalam" aria-hidden="true">CONFIDENTIAL DRAFT</div>',
            html
        )

    def test_02_malayalam_watermark_appears_in_print_preview(self):
        """2. Malayalam watermark appears in print-preview HTML when configured."""
        self.script.watermark = 'കരട് പ്രതി'
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn(
            '<div class="sp-watermark font-malayalam" aria-hidden="true">കരട് പ്രതി</div>',
            html
        )

    def test_03_empty_watermark_produces_no_watermark_element(self):
        """3. Empty watermark produces no watermark HTML element."""
        self.script.watermark = ''
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertNotIn('<div class="sp-watermark', html)

    def test_04_whitespace_only_watermark_produces_no_watermark_element(self):
        """4. Whitespace-only watermark produces no watermark HTML element."""
        self.script.watermark = '     \t  '
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertNotIn('<div class="sp-watermark', html)

    def test_05_special_characters_are_safely_autoescaped(self):
        """5. Special characters in watermark are safely autoescaped in print-preview HTML."""
        self.script.watermark = 'Draft & Review <2026> - "Confidential"'
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn(
            '<div class="sp-watermark font-malayalam" aria-hidden="true">'
            'Draft &amp; Review &lt;2026&gt; - &quot;Confidential&quot;'
            '</div>',
            html
        )
        self.assertNotIn('<2026>', html)

    def test_06_existing_screenplay_content_remains_present(self):
        """6. Existing screenplay content (title page, scenes, elements) remains intact."""
        self.script.watermark = 'INTERNAL REVIEW'
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn('മലയാളം തിരക്കഥ (Screenplay)', html)
        self.assertIn('Raseena', html)
        self.assertIn('SCENE 1 : INT. COURTYARD - DAY', html)
        self.assertIn('മഴ ശക്തമായി പെയ്യുന്നു.', html)
        self.assertIn('RAVI', html)
        self.assertIn('(softly)', html)
        self.assertIn('നമുക്ക് പോകാം.', html)
        self.assertIn('WIDE SHOT ON GATE', html)
        self.assertIn('CUT TO:', html)

    def test_07_print_css_keeps_watermark_visible(self):
        """7. The @media print CSS keeps the watermark visible and does not hide it."""
        self.script.watermark = 'CONFIDENTIAL'
        self.script.save(update_fields=['watermark'])

        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        media_print_idx = html.index('@media print')
        print_css_block = html[media_print_idx:html.index('</style>', media_print_idx)]

        self.assertIn('.sp-watermark', print_css_block)
        self.assertIn('display: block !important;', print_css_block)
        self.assertIn('position: fixed !important;', print_css_block)
        self.assertNotIn('.sp-watermark { display: none', print_css_block)

    def test_08_watermark_css_is_fixed_diagonal_and_non_interactive(self):
        """8. The watermark CSS uses position: fixed, -35deg rotation, and pointer-events: none."""
        res = self.client.get(reverse('print_preview', args=[self.script.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        style_block = html[html.index('<style>'):html.index('</style>')]
        self.assertIn('.sp-watermark', style_block)
        self.assertIn('position: fixed;', style_block)
        self.assertIn('translate(-50%, -50%) rotate(-35deg)', style_block)
        self.assertIn('pointer-events: none;', style_block)
        self.assertIn('user-select: none;', style_block)
        self.assertIn('white-space: nowrap;', style_block)
        self.assertIn('opacity: 0.08;', style_block)

    def test_09_watermark_does_not_introduce_content_flow_elements(self):
        """9. Adding a watermark does not add any .sp-scene, .sp-action, or screenplay flow elements."""
        res_empty = self.client.get(reverse('print_preview', args=[self.script.id]))
        html_empty = res_empty.content.decode('utf-8')

        self.script.watermark = 'WATERMARK OVERLAY'
        self.script.save(update_fields=['watermark'])

        res_wm = self.client.get(reverse('print_preview', args=[self.script.id]))
        html_wm = res_wm.content.decode('utf-8')

        for flow_marker in [
            'class="sp-title-block"',
            'class="sp-scene"',
            'class="sp-scene-heading',
            'class="sp-action',
            'class="sp-character"',
            'class="sp-dialogue',
            'class="sp-parenthetical"',
            'class="sp-transition"',
            'class="sp-shot"',
        ]:
            self.assertEqual(
                html_wm.count(flow_marker),
                html_empty.count(flow_marker),
                f'Flow marker count changed for {flow_marker}'
            )
        self.assertEqual(html_empty.count('class="sp-watermark'), 0)
        self.assertEqual(html_wm.count('class="sp-watermark'), 1)
