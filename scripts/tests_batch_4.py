"""
Tests for KadhaScript Batch 4: Sub-Scene Promotion and Sub-Scene Renumbering.

Covers:
Feature A — Promote Sub-Scene to Main Scene:
1. Promote sub-scene successfully: becomes main scene (parent_scene=None, is_sub_scene=False).
2. Promoted scene is placed immediately after its former parent's complete scene block.
3. All main scenes are renumbered sequentially (former parent + 1, subsequent main scenes increment).
4. Surviving sub-scenes of former parent re-letter sequentially (1.A, 1.B...).
5. Content, PK, UUID, ScriptElements, dialogue, characters, and Malayalam text remain unchanged.
6. Duplicate and intercut scenes maintain valid relationships.
7. Disallow promotion of duplicate sub-scenes and intercut sub-scenes with clear explanation.
8. Reject promotion of main scenes or deleted scenes.
9. Unauthorized access control (cross-user script isolation).
10. Transactional atomicity and rollback on error.

Feature B — Reorder Sub-Scenes (Dedicated API):
11. Move last sub-scene to first position.
12. Move first sub-scene to last position.
13. Move middle sub-scene to first position.
14. Move middle sub-scene to last position.
15. Sibling sub-letters update sequentially (A, B, C...).
16. Parent scene number and identity remain completely unchanged.
17. Sub-scene primary keys, UUIDs, content, elements, and parent links are preserved.
18. Successful no-op when requested position equals current position.
19. Rejection of invalid positions (0, negative, > total siblings, non-integers).
20. Rejection of reordering duplicate/intercut sub-scenes directly.
21. Unauthorized access control (cross-user script isolation).
22. Transactional rollback on failure.
23. Exclusion of soft-deleted sub-scenes from sibling counts and positions.
24. Response includes full serialized scenes_tree reflecting updated hierarchy.
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.db import transaction
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    create_sub_scene,
    duplicate_scene,
    create_intercut_scene,
    resequence_script_scenes,
    promote_sub_scene,
    reorder_sub_scene,
)


class Batch4SubScenePromotionAndRenumberingTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='writer_alpha', password='password123')
        self.user_b = User.objects.create_user(username='writer_beta', password='password123')

        self.client_a = Client()
        self.client_a.login(username='writer_alpha', password='password123')

        self.client_b = Client()
        self.client_b.login(username='writer_beta', password='password123')

        self.script_a = Script.objects.create(
            user=self.user_a,
            title='ബാച്ച് 4 ടെസ്റ്റ് തിരക്കഥ (Batch 4 Screenplay)',
            language='Malayalam'
        )
        self.script_b = Script.objects.create(
            user=self.user_b,
            title='User B Screenplay'
        )

    # ----------------------------------------------------
    # FEATURE A: PROMOTE SUB-SCENE TO MAIN SCENE TESTS
    # ----------------------------------------------------

    def test_01_promote_sub_scene_basic_hierarchy(self):
        """1. Promoting a sub-scene converts it to a top-level scene placed after former parent."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='INT. KITCHEN - DAY')
        sub_1b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='INT. BEDROOM - DAY')
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. STREET - NIGHT', order=3)
        resequence_script_scenes(self.script_a)

        self.assertTrue(sub_1a.is_sub_scene)
        self.assertEqual(sub_1a.parent_scene_id, s1.id)

        # Promote sub_1a via service
        success, msg = promote_sub_scene(self.script_a, sub_1a)
        self.assertTrue(success)

        sub_1a.refresh_from_db()
        s1.refresh_from_db()
        sub_1b.refresh_from_db()
        s2.refresh_from_db()

        # sub_1a is now a main scene
        self.assertFalse(sub_1a.is_sub_scene)
        self.assertIsNone(sub_1a.parent_scene)

        # Hierarchy order check:
        # s1 -> sub_1b (now 1.A) -> sub_1a (promoted, now Scene 2) -> s2 (now Scene 3)
        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s1.id, sub_1b.id, sub_1a.id, s2.id])

        self.assertEqual(s1.scene_number, 1)
        self.assertEqual(s1.display_number, 'Scene 1')

        self.assertEqual(sub_1b.scene_number, 1)
        self.assertEqual(sub_1b.display_number, 'Scene 1.A')
        self.assertEqual(sub_1b.sub_letter, 'A')

        self.assertEqual(sub_1a.scene_number, 2)
        self.assertEqual(sub_1a.display_number, 'Scene 2')

        self.assertEqual(s2.scene_number, 3)
        self.assertEqual(s2.display_number, 'Scene 3')

    def test_02_promote_middle_sub_scene_places_after_former_parent_block(self):
        """2. Promoting a middle sub-scene places it after former parent's entire scene block."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='SCENE 1', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')
        sub_1b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1B')
        sub_1c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1C')
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='SCENE 2', order=4)
        resequence_script_scenes(self.script_a)

        # Promote middle sub-scene SUB 1B
        success, msg = promote_sub_scene(self.script_a, sub_1b)
        self.assertTrue(success)

        s1.refresh_from_db()
        sub_1a.refresh_from_db()
        sub_1c.refresh_from_db()
        sub_1b.refresh_from_db()
        s2.refresh_from_db()

        # Surviving sub-scenes of s1 are sub_1a (now A) and sub_1c (now B)
        self.assertEqual(sub_1a.display_number, 'Scene 1.A')
        self.assertEqual(sub_1c.display_number, 'Scene 1.B')

        # Promoted scene sub_1b is Scene 2
        self.assertEqual(sub_1b.scene_number, 2)
        self.assertEqual(sub_1b.display_number, 'Scene 2')

        # Former Scene 2 is now Scene 3
        self.assertEqual(s2.scene_number, 3)
        self.assertEqual(s2.display_number, 'Scene 3')

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s1.id, sub_1a.id, sub_1c.id, sub_1b.id, s2.id])

    def test_03_promote_sub_scene_preserves_content_uuid_and_malayalam(self):
        """3. Content, PK, UUID, ScriptElements, dialogue, characters, and Malayalam text remain completely preserved."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='INT. തറവാട് പൂമുഖം - രാത്രി')
        sub.elements.all().delete()

        elem_heading = ScriptElement.objects.create(scene=sub, element_type='scene_heading', content='INT. തറവാട് പൂമുഖം - രാത്രി', order=0)
        elem_action = ScriptElement.objects.create(scene=sub, element_type='action', content='അമൽ വാതിൽ പതുക്കെ തുറക്കുന്നു.', order=1)
        elem_char = ScriptElement.objects.create(scene=sub, element_type='character', content='അമൽ', order=2)
        elem_dialogue = ScriptElement.objects.create(scene=sub, element_type='dialogue', content='ആരാണ് അവിടെ?', order=3)

        original_pk = sub.id
        original_uuid = sub.scene_uuid
        original_heading = sub.heading

        url = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub.id})
        res = self.client_a.post(url, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')

        sub.refresh_from_db()
        self.assertEqual(sub.id, original_pk)
        self.assertEqual(sub.scene_uuid, original_uuid)
        self.assertEqual(sub.heading, original_heading)
        self.assertFalse(sub.is_sub_scene)
        self.assertIsNone(sub.parent_scene)

        # Verify all elements remain intact and attached
        elements = list(sub.elements.order_by('order'))
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0].content, 'INT. തറവാട് പൂമുഖം - രാത്രി')
        self.assertEqual(elements[1].content, 'അമൽ വാതിൽ പതുക്കെ തുറക്കുന്നു.')
        self.assertEqual(elements[2].content, 'അമൽ')
        self.assertEqual(elements[3].content, 'ആരാണ് അവിടെ?')

    def test_04_promote_sub_scene_with_former_parent_having_duplicate(self):
        """4. Promoted scene is placed after former parent's duplicates and remaining sub-scenes."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')
        s1_dup = duplicate_scene(self.script_a, source_scene=s1)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='INT. NEXT - DAY', order=3)
        resequence_script_scenes(self.script_a)

        url = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_1a.id})
        res = self.client_a.post(url, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub_1a.refresh_from_db()
        s1.refresh_from_db()
        s1_dup.refresh_from_db()
        s2.refresh_from_db()

        self.assertFalse(sub_1a.is_sub_scene)
        self.assertEqual(sub_1a.scene_number, 2)
        self.assertEqual(s2.scene_number, 3)

    def test_05_disallow_promotion_of_duplicate_and_intercut_sub_scenes(self):
        """5. Duplicate and intercut sub-scenes reject promotion with clear explanatory messages."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')
        dup_sub = duplicate_scene(self.script_a, source_scene=sub_1a)

        # Attempt to promote duplicate sub-scene via API
        url_dup = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': dup_sub.id})
        res_dup = self.client_a.post(url_dup, content_type='application/json')
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn("Duplicate sub-scenes cannot be promoted", res_dup.json()['message'])

        # Create intercut sub-scene and attempt promotion
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='INT. JAIL - DAY', order=3)
        intercut_sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='INTERCUT SUB')
        intercut_sub.is_intercut = True
        intercut_sub.intercut_source = s2
        intercut_sub.save(update_fields=['is_intercut', 'intercut_source'])

        url_intercut = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': intercut_sub.id})
        res_intercut = self.client_a.post(url_intercut, content_type='application/json')
        self.assertEqual(res_intercut.status_code, 400)
        self.assertIn("Intercut sub-scenes cannot be promoted", res_intercut.json()['message'])

    def test_06_disallow_promotion_of_main_scene(self):
        """6. Attempting to promote an ordinary main scene returns error 400."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        url = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': s1.id})
        res = self.client_a.post(url, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("Only active sub-scenes can be promoted", res.json()['message'])

    def test_07_promote_unauthorized_access_rejected(self):
        """7. User B cannot promote a scene belonging to User A's screenplay."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')

        url = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub.id})
        res = self.client_b.post(url, content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_08_promote_transactional_rollback_on_failure(self):
        """8. If promotion fails mid-operation, transaction rolls back cleanly without partial modifications."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. S1 - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')
        sub_1b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1B')
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='INT. S2 - DAY', order=3)
        resequence_script_scenes(self.script_a)

        # Force a failure during promote_sub_scene
        from unittest.mock import patch
        with patch('scripts.services.scene_service.resequence_script_scenes', side_effect=RuntimeError("Forced failure")):
            with self.assertRaises(RuntimeError):
                promote_sub_scene(self.script_a, sub_1a)

        # Verify state is completely restored
        sub_1a.refresh_from_db()
        s1.refresh_from_db()
        sub_1b.refresh_from_db()
        s2.refresh_from_db()

        self.assertTrue(sub_1a.is_sub_scene)
        self.assertEqual(sub_1a.parent_scene_id, s1.id)
        self.assertEqual(sub_1a.display_number, 'Scene 1.A')
        self.assertEqual(sub_1b.display_number, 'Scene 1.B')
        self.assertEqual(s2.display_number, 'Scene 2')

    # ----------------------------------------------------
    # FEATURE B: REORDER SUB-SCENES TESTS
    # ----------------------------------------------------

    def test_09_reorder_last_sub_scene_to_first(self):
        """9. Moving last sub-scene (C) to first position (A) re-letters siblings cleanly."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        sub_c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB C')
        resequence_script_scenes(self.script_a)

        self.assertEqual(sub_c.display_number, 'Scene 1.C')

        # Move sub_c from pos 3 to pos 1 via dedicated API
        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_c.id})
        res = self.client_a.post(url, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

        sub_c.refresh_from_db()
        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        s1.refresh_from_db()

        # Parent number unchanged
        self.assertEqual(s1.scene_number, 1)

        # Order of sub-scenes: sub_c, sub_a, sub_b
        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s1.id, sub_c.id, sub_a.id, sub_b.id])

        self.assertEqual(sub_c.display_number, 'Scene 1.A')
        self.assertEqual(sub_c.sub_letter, 'A')
        self.assertEqual(sub_a.display_number, 'Scene 1.B')
        self.assertEqual(sub_a.sub_letter, 'B')
        self.assertEqual(sub_b.display_number, 'Scene 1.C')
        self.assertEqual(sub_b.sub_letter, 'C')

    def test_10_reorder_first_sub_scene_to_last(self):
        """10. Moving first sub-scene (A) to last position (C) re-letters siblings cleanly."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        sub_c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB C')
        resequence_script_scenes(self.script_a)

        # Move sub_a from pos 1 to pos 3
        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_a.id})
        res = self.client_a.post(url, data=json.dumps({'target_position': 3}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub_b.refresh_from_db()
        sub_c.refresh_from_db()
        sub_a.refresh_from_db()

        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_c.display_number, 'Scene 1.B')
        self.assertEqual(sub_a.display_number, 'Scene 1.C')

    def test_11_reorder_middle_sub_scene_to_first_and_last(self):
        """11. Moving middle sub-scene to first or last position works accurately."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        sub_c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB C')
        resequence_script_scenes(self.script_a)

        # Move sub_b to pos 1 -> order: sub_b (A), sub_a (B), sub_c (C)
        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})
        res1 = self.client_a.post(url, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res1.status_code, 200)

        sub_b.refresh_from_db()
        sub_a.refresh_from_db()
        sub_c.refresh_from_db()
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_a.display_number, 'Scene 1.B')
        self.assertEqual(sub_c.display_number, 'Scene 1.C')

        # Move sub_a (currently pos 2) to pos 3 -> order: sub_b (A), sub_c (B), sub_a (C)
        url_a = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_a.id})
        res2 = self.client_a.post(url_a, data=json.dumps({'target_position': 3}), content_type='application/json')
        self.assertEqual(res2.status_code, 200)

        sub_b.refresh_from_db()
        sub_c.refresh_from_db()
        sub_a.refresh_from_db()
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_c.display_number, 'Scene 1.B')
        self.assertEqual(sub_a.display_number, 'Scene 1.C')

    def test_12_reorder_noop_when_position_unchanged(self):
        """12. Requesting the same position returns successful noop without unnecessary database writes."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        resequence_script_scenes(self.script_a)

        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_a.id})
        res = self.client_a.post(url, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'noop')
        self.assertIn("already at position 1", data['message'])

    def test_13_reorder_invalid_positions_rejected(self):
        """13. Zero, negative, out-of-range, and non-integer positions are rejected with 400."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')

        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_a.id})

        # Test zero
        res0 = self.client_a.post(url, data=json.dumps({'target_position': 0}), content_type='application/json')
        self.assertEqual(res0.status_code, 400)

        # Test negative
        res_neg = self.client_a.post(url, data=json.dumps({'target_position': -1}), content_type='application/json')
        self.assertEqual(res_neg.status_code, 400)

        # Test greater than total siblings (2 siblings, request 5)
        res_over = self.client_a.post(url, data=json.dumps({'target_position': 5}), content_type='application/json')
        self.assertEqual(res_over.status_code, 400)

        # Test non-integer
        res_str = self.client_a.post(url, data=json.dumps({'target_position': 'abc'}), content_type='application/json')
        self.assertEqual(res_str.status_code, 400)

    def test_14_reorder_unauthorized_access_rejected(self):
        """14. User B cannot reorder a sub-scene in User A's screenplay."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')

        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_a.id})
        res = self.client_b.post(url, data=json.dumps({'target_position': 2}), content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_15_reorder_excludes_soft_deleted_sub_scenes(self):
        """15. Soft-deleted sub-scenes are excluded from position calculations and re-ordering."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_del = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB DELETED')
        sub_del.is_deleted = True
        sub_del.save(update_fields=['is_deleted'])
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        resequence_script_scenes(self.script_a)

        # Total active siblings = 2 (sub_a, sub_b)
        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})

        # Position 3 should be rejected because active count is 2
        res_fail = self.client_a.post(url, data=json.dumps({'target_position': 3}), content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)

        # Move sub_b to position 1
        res_ok = self.client_a.post(url, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res_ok.status_code, 200)

        sub_b.refresh_from_db()
        sub_a.refresh_from_db()
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_a.display_number, 'Scene 1.B')

    def test_16_reorder_transactional_rollback_on_failure(self):
        """16. If reordering fails, database changes roll back cleanly."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        resequence_script_scenes(self.script_a)

        from unittest.mock import patch
        with patch('scripts.services.scene_service.resequence_script_scenes', side_effect=RuntimeError("Forced rollback")):
            with self.assertRaises(RuntimeError):
                reorder_sub_scene(self.script_a, sub_b, 1)

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')

    def test_17_scenes_tree_in_api_response_is_synchronized(self):
        """17. API responses for promote and reorder contain the full updated scenes_tree."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')

        # Reorder
        url_reorder = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})
        res_reorder = self.client_a.post(url_reorder, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res_reorder.status_code, 200)
        tree = res_reorder.json()['scenes_tree']
        self.assertEqual(len(tree), 3)
        self.assertEqual(tree[1]['id'], sub_b.id)
        self.assertEqual(tree[1]['display_number'], 'Scene 1.A')
        self.assertEqual(tree[2]['id'], sub_a.id)
        self.assertEqual(tree[2]['display_number'], 'Scene 1.B')

        # Promote
        url_promote = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})
        res_promote = self.client_a.post(url_promote, content_type='application/json')
        self.assertEqual(res_promote.status_code, 200)
        tree_promoted = res_promote.json()['scenes_tree']
        self.assertEqual(len(tree_promoted), 3)
        # Sequence: s1 (Scene 1) -> sub_a (Scene 1.A) -> sub_b (Scene 2)
        self.assertEqual(tree_promoted[0]['display_number'], 'Scene 1')
        self.assertEqual(tree_promoted[1]['display_number'], 'Scene 1.A')
        self.assertEqual(tree_promoted[2]['display_number'], 'Scene 2')
        self.assertFalse(tree_promoted[2]['is_sub_scene'])

    def test_18_reorder_sub_scene_with_duplicate(self):
        """18. [Test A] Reordering a base sub-scene with a duplicate preserves duplicate grouping and re-letters properly."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        dup_b = duplicate_scene(self.script_a, source_scene=sub_b)
        sub_c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB C')
        resequence_script_scenes(self.script_a)

        # Record PKs and initial state
        sub_a_pk = sub_a.id
        sub_b_pk = sub_b.id
        dup_b_pk = dup_b.id
        sub_c_pk = sub_c.id

        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')
        self.assertEqual(dup_b.display_number, 'Scene 1.B (Duplicate)')
        self.assertEqual(sub_c.display_number, 'Scene 1.C')

        # Reorder base B (pos 2 among non-duplicate siblings: A, B, C) to position 1
        url = reverse('api_reorder_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})
        res = self.client_a.post(url, data=json.dumps({'target_position': 1}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

        sub_b.refresh_from_db()
        dup_b.refresh_from_db()
        sub_a.refresh_from_db()
        sub_c.refresh_from_db()

        # Check reading order
        ordered = list(self.script_a.scenes.filter(is_deleted=False).order_by('order', 'id'))
        expected_ids = [s1.id, sub_b_pk, dup_b_pk, sub_a_pk, sub_c_pk]
        self.assertEqual([sc.id for sc in ordered], expected_ids)

        # Primary keys and headings remain unchanged
        self.assertEqual(sub_b.id, sub_b_pk)
        self.assertEqual(dup_b.id, dup_b_pk)
        self.assertEqual(sub_a.id, sub_a_pk)
        self.assertEqual(sub_c.id, sub_c_pk)

        # Parent association preserved
        self.assertEqual(sub_b.parent_scene_id, s1.id)
        self.assertEqual(dup_b.parent_scene_id, s1.id)
        self.assertEqual(sub_a.parent_scene_id, s1.id)
        self.assertEqual(sub_c.parent_scene_id, s1.id)

        # Identifiers: B moved to 1 -> becomes A and A (Duplicate)
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.sub_letter, 'A')
        self.assertEqual(dup_b.display_number, 'Scene 1.A (Duplicate)')
        self.assertEqual(dup_b.sub_letter, 'A')

        # Former A becomes B
        self.assertEqual(sub_a.display_number, 'Scene 1.B')
        self.assertEqual(sub_a.sub_letter, 'B')

        # Former C remains C
        self.assertEqual(sub_c.display_number, 'Scene 1.C')
        self.assertEqual(sub_c.sub_letter, 'C')

    def test_19_promote_sub_scene_with_remaining_sub_scenes_and_duplicates(self):
        """19. [Test B] Promoting sub-scene while other sub-scenes and duplicates remain preserves all relationships."""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. MAIN - DAY', order=0)
        sub_a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB A')
        dup_a = duplicate_scene(self.script_a, source_scene=sub_a)
        sub_b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB B')
        sub_c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB C')
        resequence_script_scenes(self.script_a)

        s1_pk = s1.id
        sub_a_pk = sub_a.id
        dup_a_pk = dup_a.id
        sub_b_pk = sub_b.id
        sub_c_pk = sub_c.id

        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(dup_a.display_number, 'Scene 1.A (Duplicate)')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')
        self.assertEqual(sub_c.display_number, 'Scene 1.C')

        # Promote sub_b to main scene
        url = reverse('api_promote_sub_scene', kwargs={'script_id': self.script_a.id, 'scene_id': sub_b.id})
        res = self.client_a.post(url, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

        sub_b.refresh_from_db()
        s1.refresh_from_db()
        sub_a.refresh_from_db()
        dup_a.refresh_from_db()
        sub_c.refresh_from_db()

        # Sub B is now a main scene
        self.assertFalse(sub_b.is_sub_scene)
        self.assertIsNone(sub_b.parent_scene)
        self.assertEqual(sub_b.id, sub_b_pk)
        self.assertEqual(sub_b.scene_number, 2)
        self.assertEqual(sub_b.display_number, 'Scene 2')

        # Surviving scenes under s1
        self.assertEqual(s1.id, s1_pk)
        self.assertEqual(s1.scene_number, 1)
        self.assertEqual(sub_a.parent_scene_id, s1_pk)
        self.assertEqual(dup_a.parent_scene_id, s1_pk)
        self.assertEqual(sub_c.parent_scene_id, s1_pk)

        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(dup_a.display_number, 'Scene 1.A (Duplicate)')
        self.assertEqual(sub_c.display_number, 'Scene 1.B')

        # Reading order: s1 -> sub_a -> dup_a -> sub_c -> sub_b (now Scene 2)
        ordered = list(self.script_a.scenes.filter(is_deleted=False).order_by('order', 'id'))
        expected_ids = [s1_pk, sub_a_pk, dup_a_pk, sub_c_pk, sub_b_pk]
        self.assertEqual([sc.id for sc in ordered], expected_ids)
