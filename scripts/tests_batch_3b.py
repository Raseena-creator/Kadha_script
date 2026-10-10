import uuid
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch

from scripts.models import Script, Scene, ScriptElement, ScriptVersion, ScriptTitlePage
from scripts.services.version_service import create_version_snapshot, restore_version_snapshot


class VersionRestorationSafetyBatch3BTests(TestCase):
    """
    Batch 3B Test Suite: Version Restoration Safety and Trash Preservation.
    Verifies that version restoration:
    - Never permanently deletes scenes or elements currently in Trash.
    - Never silently reactivates trashed scenes.
    - Excludes trashed scenes and sub-scenes from version snapshots.
    - Preserves active scene ordering and sub-scene parent relationships.
    - Safely reconciles UUID collisions with trashed scenes.
    - Safely handles legacy snapshots without UUIDs or intercut metadata.
    - Reconstructs intercut links when sources are valid and active.
    - Gracefully handles missing/corrupt intercut sources without crashes or guessing.
    - Retains the automatic pre-restoration snapshot.
    - Transactionally rolls back on restoration errors.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='batch3b_writer', password='TestPassword123!')
        self.script = Script.objects.create(
            user=self.user,
            title='ആരണ്യം (Aaranyam)',
            description='Active screenplay for Batch 3B version safety tests',
            author_name='Rasi'
        )

    def test_1_restoring_version_preserves_trashed_main_scene(self):
        """1. Restoring a version must never permanently delete a trashed main scene."""
        # Active Scene 1
        sc1 = Scene.objects.create(
            script=self.script,
            heading='INT. HOUSE - NIGHT',
            order=0,
            is_deleted=False
        )
        ScriptElement.objects.create(scene=sc1, element_type='scene_heading', content='INT. HOUSE - NIGHT', order=0)

        # Snapshot of Version 1
        v1 = create_version_snapshot(self.script, title='Version 1')

        # Trashed Scene 2
        sc_trashed = Scene.objects.create(
            script=self.script,
            heading='EXT. FOREST - DAY',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        ScriptElement.objects.create(scene=sc_trashed, element_type='action', content='Deep woods.', order=0)

        # Restore Version 1
        res = restore_version_snapshot(self.script, v1.id)
        self.assertTrue(res)

        # Assert trashed scene still exists in database
        self.assertTrue(Scene.objects.filter(id=sc_trashed.id, is_deleted=True).exists())
        trashed_refreshed = Scene.objects.get(id=sc_trashed.id)
        self.assertEqual(trashed_refreshed.heading, 'EXT. FOREST - DAY')
        self.assertTrue(trashed_refreshed.is_deleted)

    def test_2_restoring_version_preserves_trashed_sub_scene(self):
        """2. Restoring a version must preserve a trashed sub-scene without cascading deletion."""
        # Active Main Scene 1
        sc1 = Scene.objects.create(
            script=self.script,
            heading='INT. HOUSE - DAY',
            order=0,
            is_deleted=False
        )

        # Trashed Sub-Scene 1.A (attached to sc1 before sc1 gets replaced)
        sub_trashed = Scene.objects.create(
            script=self.script,
            parent_scene=sc1,
            heading='INT. BEDROOM - DAY',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now(),
            original_parent_uuid=sc1.scene_uuid,
            original_parent_scene_number=sc1.scene_number,
            original_parent_heading=sc1.heading
        )
        ScriptElement.objects.create(scene=sub_trashed, element_type='action', content='Secret letter hidden.', order=0)

        # Version 1 with sc1
        v1 = create_version_snapshot(self.script, title='Version 1')

        # Restore
        restore_version_snapshot(self.script, v1.id)

        # Sub-scene must still exist in DB and remain trashed
        self.assertTrue(Scene.objects.filter(id=sub_trashed.id, is_deleted=True).exists())
        refreshed_sub = Scene.objects.get(id=sub_trashed.id)
        self.assertTrue(refreshed_sub.is_deleted)
        self.assertEqual(refreshed_sub.original_parent_uuid, sc1.scene_uuid)

    def test_3_elements_belonging_to_trashed_scenes_remain_intact(self):
        """3. ScriptElements belonging to trashed scenes must remain intact in DB."""
        sc_trashed = Scene.objects.create(
            script=self.script,
            heading='INT. BASEMENT - NIGHT',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        elem1 = ScriptElement.objects.create(
            scene=sc_trashed,
            element_type='dialogue',
            content='ആരുണ്ട് അവിടെ? (Who is there?)',
            order=0
        )
        elem2 = ScriptElement.objects.create(
            scene=sc_trashed,
            element_type='action',
            content='Footsteps echo in the dark.',
            order=1
        )

        # Active Scene
        sc_active = Scene.objects.create(script=self.script, heading='INT. OFFICE - DAY', order=0)
        v1 = create_version_snapshot(self.script, title='V1')

        # Restore
        restore_version_snapshot(self.script, v1.id)

        # Verify elements still exist and belong to the trashed scene
        self.assertTrue(ScriptElement.objects.filter(id=elem1.id, scene_id=sc_trashed.id).exists())
        self.assertTrue(ScriptElement.objects.filter(id=elem2.id, scene_id=sc_trashed.id).exists())
        self.assertEqual(ScriptElement.objects.get(id=elem1.id).content, 'ആരുണ്ട് അവിടെ? (Who is there?)')

    def test_4_trashed_scenes_do_not_become_active_through_restoration(self):
        """4. Trashed scenes must never have is_deleted flipped to False during restore."""
        sc_trashed = Scene.objects.create(
            script=self.script,
            heading='EXT. OLD FORT - SUNSET',
            order=2,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        sc_active = Scene.objects.create(script=self.script, heading='INT. CABIN - DAY', order=0)
        v1 = create_version_snapshot(self.script, title='V1')

        restore_version_snapshot(self.script, v1.id)

        refreshed_trashed = Scene.objects.get(id=sc_trashed.id)
        self.assertTrue(refreshed_trashed.is_deleted)
        self.assertIsNotNone(refreshed_trashed.deleted_at)

    def test_5_new_snapshots_exclude_trashed_scenes_and_sub_scenes(self):
        """5. create_version_snapshot must exclude trashed main scenes and trashed sub-scenes."""
        active_main = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE MAIN - DAY',
            order=0,
            is_deleted=False
        )
        active_sub = Scene.objects.create(
            script=self.script,
            parent_scene=active_main,
            heading='INT. ACTIVE SUB - DAY',
            order=1,
            is_deleted=False
        )

        trashed_main = Scene.objects.create(
            script=self.script,
            heading='EXT. TRASHED MAIN - NIGHT',
            order=2,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        trashed_sub_under_active = Scene.objects.create(
            script=self.script,
            parent_scene=active_main,
            heading='INT. TRASHED SUB - DAY',
            order=3,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        ver = create_version_snapshot(self.script, title='Exclusion Snapshot')
        snap_scenes = ver.snapshot_data['scenes']

        # Only 1 main scene serialized
        self.assertEqual(len(snap_scenes), 1)
        self.assertEqual(snap_scenes[0]['heading'], 'INT. ACTIVE MAIN - DAY')

        # Only 1 sub-scene serialized under active_main
        sub_scenes = snap_scenes[0]['sub_scenes']
        self.assertEqual(len(sub_scenes), 1)
        self.assertEqual(sub_scenes[0]['heading'], 'INT. ACTIVE SUB - DAY')

    def test_6_active_scene_ordering_is_preserved(self):
        """6. Active scene order and sequencing must be properly restored."""
        s1 = Scene.objects.create(script=self.script, heading='INT. FIRST - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, heading='INT. SECOND - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, heading='INT. THIRD - DAY', order=2)

        v1 = create_version_snapshot(self.script, title='Ordering Test')

        # Mutate current active scenes
        s1.order = 2
        s1.save()
        s3.order = 0
        s3.save()

        # Restore
        restore_version_snapshot(self.script, v1.id)

        ordered = self.script.get_ordered_scenes()
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0].heading, 'INT. FIRST - DAY')
        self.assertEqual(ordered[1].heading, 'INT. SECOND - DAY')
        self.assertEqual(ordered[2].heading, 'INT. THIRD - DAY')
        self.assertEqual(ordered[0].order, 0)
        self.assertEqual(ordered[1].order, 1)
        self.assertEqual(ordered[2].order, 2)

    def test_7_active_sub_scene_parent_relationships_preserved(self):
        """7. Restored sub-scenes must be attached to the correct restored main scene."""
        main_scene = Scene.objects.create(script=self.script, heading='INT. HOSPITAL - DAY', order=0)
        sub_scene = Scene.objects.create(script=self.script, parent_scene=main_scene, heading='INT. ICU - DAY', order=1)

        v1 = create_version_snapshot(self.script, title='Sub-Scene Parent Test')

        restore_version_snapshot(self.script, v1.id)

        active_scenes = self.script.get_ordered_scenes()
        self.assertEqual(len(active_scenes), 2)
        restored_main = active_scenes[0]
        restored_sub = active_scenes[1]

        self.assertIsNone(restored_main.parent_scene)
        self.assertEqual(restored_sub.parent_scene_id, restored_main.id)
        self.assertEqual(restored_sub.heading, 'INT. ICU - DAY')

    def test_8_intercut_metadata_and_source_references_restored_safely(self):
        """8. Intercut metadata and source scene references must be restored safely."""
        source_scene = Scene.objects.create(
            script=self.script,
            heading='INT. POLICE CONTROL ROOM - NIGHT',
            order=0
        )
        intercut_scene = Scene.objects.create(
            script=self.script,
            heading='INT. PATROL CAR - NIGHT',
            order=1,
            is_intercut=True,
            intercut_source=source_scene
        )

        v1 = create_version_snapshot(self.script, title='Intercut Test')
        self.assertTrue(v1.snapshot_data['scenes'][1]['is_intercut'])
        self.assertEqual(v1.snapshot_data['scenes'][1]['intercut_source_uuid'], str(source_scene.scene_uuid))

        restore_version_snapshot(self.script, v1.id)

        scenes = self.script.get_ordered_scenes()
        self.assertEqual(len(scenes), 2)
        restored_source = scenes[0]
        restored_intercut = scenes[1]

        self.assertTrue(restored_intercut.is_intercut)
        self.assertEqual(restored_intercut.intercut_source_id, restored_source.id)

    def test_9_uuid_collisions_with_trashed_scenes_handled_safely(self):
        """9. If a snapshot scene has a UUID already held by a trashed scene, assign a fresh UUID."""
        fixed_uuid = uuid.uuid4()
        trashed_scene = Scene.objects.create(
            script=self.script,
            scene_uuid=fixed_uuid,
            heading='EXT. OLD RUINS - DUSK',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # Snapshot with a scene having the identical fixed_uuid
        snapshot_data = {
            'title': self.script.title,
            'scenes': [
                {
                    'scene_uuid': str(fixed_uuid),
                    'heading': 'INT. RESTORED SCENE - DAY',
                    'order': 0,
                    'scene_number': 1,
                    'elements': []
                }
            ]
        }
        v1 = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='UUID Collision Snapshot',
            snapshot_data=snapshot_data
        )

        restore_version_snapshot(self.script, v1.id)

        # Trashed scene must still have fixed_uuid and remain trashed
        trashed_refreshed = Scene.objects.get(id=trashed_scene.id)
        self.assertTrue(trashed_refreshed.is_deleted)
        self.assertEqual(trashed_refreshed.scene_uuid, fixed_uuid)

        # Restored active scene must NOT reuse fixed_uuid (generated a fresh UUID)
        active_scene = self.script.scenes.filter(is_deleted=False).first()
        self.assertIsNotNone(active_scene)
        self.assertNotEqual(active_scene.scene_uuid, fixed_uuid)
        self.assertEqual(active_scene.heading, 'INT. RESTORED SCENE - DAY')

    def test_10_legacy_snapshots_without_uuids_handled_safely(self):
        """10. Legacy snapshots lacking scene_uuid or intercut metadata must restore safely."""
        legacy_snapshot = {
            'title': self.script.title,
            'scenes': [
                {
                    'scene_number': 1,
                    'heading': 'INT. TRADITIONAL HOME - MORNING',
                    'order': 0,
                    'transition': 'CUT TO',
                    'summary': 'Breakfast scene',
                    'elements': [
                        {'element_type': 'scene_heading', 'content': 'INT. TRADITIONAL HOME - MORNING', 'order': 0},
                        {'element_type': 'action', 'content': 'Tea is being poured.', 'order': 1}
                    ],
                    'sub_scenes': [
                        {
                            'scene_number': 1,
                            'heading': 'INT. KITCHEN - MORNING',
                            'order': 1,
                            'transition': 'CUT TO',
                            'elements': [
                                {'element_type': 'dialogue', 'content': 'ചായ തയ്യാറാണ്. (Tea is ready.)', 'order': 0}
                            ]
                        }
                    ]
                }
            ]
        }
        v_legacy = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Legacy Version Snapshot',
            snapshot_data=legacy_snapshot
        )

        res = restore_version_snapshot(self.script, v_legacy.id)
        self.assertTrue(res)

        active_scenes = self.script.get_ordered_scenes()
        self.assertEqual(len(active_scenes), 2)
        main_sc = active_scenes[0]
        sub_sc = active_scenes[1]

        self.assertEqual(main_sc.heading, 'INT. TRADITIONAL HOME - MORNING')
        self.assertIsInstance(main_sc.scene_uuid, uuid.UUID)
        self.assertEqual(sub_sc.parent_scene_id, main_sc.id)
        self.assertIsInstance(sub_sc.scene_uuid, uuid.UUID)
        self.assertEqual(sub_sc.elements.first().content, 'ചായ തയ്യാറാണ്. (Tea is ready.)')

    def test_11_missing_intercut_source_reverts_safely_without_crashing(self):
        """11. Missing intercut source UUIDs must not crash or guess; reverts to non-intercut."""
        snapshot_missing_source = {
            'title': self.script.title,
            'scenes': [
                {
                    'scene_uuid': str(uuid.uuid4()),
                    'heading': 'INT. ALONE - NIGHT',
                    'order': 0,
                    'is_intercut': True,
                    'intercut_source_uuid': str(uuid.uuid4()),  # Non-existent source UUID
                    'elements': []
                }
            ]
        }
        ver = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Missing Intercut Source',
            snapshot_data=snapshot_missing_source
        )

        restore_version_snapshot(self.script, ver.id)

        scenes = self.script.get_ordered_scenes()
        self.assertEqual(len(scenes), 1)
        # Safely reverted intercut to False and None source
        self.assertFalse(scenes[0].is_intercut)
        self.assertIsNone(scenes[0].intercut_source)

    def test_12_failed_restoration_rolls_back_all_changes(self):
        """12. If restoration raises an error, all database changes must roll back."""
        sc_original = Scene.objects.create(
            script=self.script,
            heading='INT. ORIGINAL UNTOUCHED - DAY',
            order=0,
            is_deleted=False
        )

        # Corrupt snapshot (scenes is not a list)
        corrupt_version = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Corrupt Version',
            snapshot_data={'scenes': 'not-a-list'}
        )

        with self.assertRaises(ValueError):
            restore_version_snapshot(self.script, corrupt_version.id)

        # Original scene still exists and unchanged
        self.assertTrue(Scene.objects.filter(id=sc_original.id).exists())
        self.assertEqual(Scene.objects.get(id=sc_original.id).heading, 'INT. ORIGINAL UNTOUCHED - DAY')

    def test_13_automatic_pre_restoration_snapshot_remains_intact(self):
        """13. The automatic pre-restoration snapshot must be recorded in history."""
        Scene.objects.create(script=self.script, heading='INT. PRE-RESTORE SCENE - DAY', order=0)
        v1 = create_version_snapshot(self.script, title='Target Restore Version')

        # Change active scene
        Scene.objects.filter(script=self.script).update(heading='INT. EDITED SCENE - DAY')

        init_version_count = self.script.versions.count()

        restore_version_snapshot(self.script, v1.id)

        self.assertEqual(self.script.versions.count(), init_version_count + 1)
        auto_backup = self.script.versions.order_by('-version_number').first()
        self.assertIn('Auto-backup before restoring', auto_backup.title)
        self.assertEqual(auto_backup.snapshot_data['scenes'][0]['heading'], 'INT. EDITED SCENE - DAY')

    def test_14_existing_versioning_behavior_title_page_preserved(self):
        """14. Title page metadata and production credits are correctly restored."""
        tp = ScriptTitlePage.objects.create(
            script=self.script,
            title='Custom Title',
            author_name='Rasi Writer',
            draft_revision='Draft 1',
            copyright_registration='FEFKA Reg 1234'
        )
        Scene.objects.create(script=self.script, heading='INT. SCENE 1 - DAY', order=0)

        v1 = create_version_snapshot(self.script, title='With Title Page')

        # Mutate title page
        tp.draft_revision = 'Draft 99 Modified'
        tp.save()

        restore_version_snapshot(self.script, v1.id)

        tp.refresh_from_db()
        self.assertEqual(tp.draft_revision, 'Draft 1')
        self.assertEqual(tp.copyright_registration, 'FEFKA Reg 1234')

    def test_15_duplicate_uuid_with_ambiguous_intercut_rejected(self):
        """
        Test A — Duplicate UUID and intercut ambiguity:
        Create a snapshot containing two scenes with the same UUID and a third scene
        whose intercut source references that duplicate UUID.
        Assert that:
        - Restoration raises a clear ValueError before mutations.
        - The current active screenplay remains unchanged.
        - Trashed scenes and their elements remain unchanged.
        - No partial replacement occurs.
        """
        shared_uuid = str(uuid.uuid4())

        # Existing active scene and elements
        sc_active = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE INITIAL - DAY',
            order=0,
            is_deleted=False
        )
        elem_active = ScriptElement.objects.create(
            scene=sc_active,
            element_type='action',
            content='Initial active dialogue and action.',
            order=0
        )

        # Existing trashed scene and elements
        sc_trashed = Scene.objects.create(
            script=self.script,
            heading='EXT. TRASHED INITIAL - NIGHT',
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        elem_trashed = ScriptElement.objects.create(
            scene=sc_trashed,
            element_type='dialogue',
            content='Initial trashed line.',
            order=0
        )

        initial_active_count = Scene.objects.filter(script=self.script, is_deleted=False).count()
        initial_trashed_count = Scene.objects.filter(script=self.script, is_deleted=True).count()
        initial_element_count = ScriptElement.objects.filter(scene__script=self.script).count()

        # Malformed snapshot: scene 1 and scene 2 have same raw UUID, scene 3 intercuts targeting shared_uuid
        ambiguous_snapshot = {
            'scenes': [
                {
                    'scene_uuid': shared_uuid,
                    'scene_number': 1,
                    'heading': 'INT. ROOM A - DAY',
                    'order': 0,
                    'is_intercut': False,
                    'elements': [{'element_type': 'action', 'content': 'In Room A', 'order': 0}],
                    'sub_scenes': []
                },
                {
                    'scene_uuid': shared_uuid,
                    'scene_number': 2,
                    'heading': 'INT. ROOM B - DAY',
                    'order': 1,
                    'is_intercut': False,
                    'elements': [{'element_type': 'action', 'content': 'In Room B', 'order': 0}],
                    'sub_scenes': []
                },
                {
                    'scene_uuid': str(uuid.uuid4()),
                    'scene_number': 3,
                    'heading': 'INT. ROOM C - DAY',
                    'order': 2,
                    'is_intercut': True,
                    'intercut_source_uuid': shared_uuid,
                    'elements': [{'element_type': 'action', 'content': 'In Room C Intercut', 'order': 0}],
                    'sub_scenes': []
                }
            ]
        }

        bad_version = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Ambiguous Duplicate UUID Version',
            snapshot_data=ambiguous_snapshot
        )

        with self.assertRaises(ValueError) as ctx:
            restore_version_snapshot(self.script, bad_version.id)

        self.assertIn("ambiguous duplicate UUID(s)", str(ctx.exception))
        self.assertIn(shared_uuid, str(ctx.exception))

        # Assert active screenplay is completely unchanged
        self.assertEqual(Scene.objects.filter(script=self.script, is_deleted=False).count(), initial_active_count)
        sc_active_refreshed = Scene.objects.get(id=sc_active.id)
        self.assertEqual(sc_active_refreshed.heading, 'INT. ACTIVE INITIAL - DAY')
        self.assertFalse(sc_active_refreshed.is_deleted)
        self.assertTrue(ScriptElement.objects.filter(id=elem_active.id, content='Initial active dialogue and action.').exists())

        # Assert trashed scene and its elements remain completely unchanged
        self.assertEqual(Scene.objects.filter(script=self.script, is_deleted=True).count(), initial_trashed_count)
        sc_trashed_refreshed = Scene.objects.get(id=sc_trashed.id)
        self.assertEqual(sc_trashed_refreshed.heading, 'EXT. TRASHED INITIAL - NIGHT')
        self.assertTrue(sc_trashed_refreshed.is_deleted)
        self.assertTrue(ScriptElement.objects.filter(id=elem_trashed.id, content='Initial trashed line.').exists())

        # Total elements unchanged (no partial replacement)
        self.assertEqual(ScriptElement.objects.filter(scene__script=self.script).count(), initial_element_count)

    def test_16_duplicate_uuid_without_relationship_restores_safely(self):
        """
        Test B — Duplicate UUID without a relationship:
        If duplicate raw UUIDs are not referenced by any parent or intercut relationship,
        independent scenes are restored safely, each scene receives unique UUIDs,
        and no ambiguous relationship is created.
        """
        shared_uuid = str(uuid.uuid4())

        independent_snapshot = {
            'scenes': [
                {
                    'scene_uuid': shared_uuid,
                    'scene_number': 1,
                    'heading': 'INT. INDEPENDENT SCENE 1 - DAY',
                    'order': 0,
                    'is_intercut': False,
                    'elements': [{'element_type': 'action', 'content': 'Action 1', 'order': 0}],
                    'sub_scenes': []
                },
                {
                    'scene_uuid': shared_uuid,
                    'scene_number': 2,
                    'heading': 'INT. INDEPENDENT SCENE 2 - NIGHT',
                    'order': 1,
                    'is_intercut': False,
                    'elements': [{'element_type': 'action', 'content': 'Action 2', 'order': 0}],
                    'sub_scenes': []
                }
            ]
        }

        version = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Duplicate UUID Without Relationships',
            snapshot_data=independent_snapshot
        )

        success = restore_version_snapshot(self.script, version.id)
        self.assertTrue(success)

        restored_scenes = list(self.script.get_ordered_scenes())
        self.assertEqual(len(restored_scenes), 2)
        self.assertEqual(restored_scenes[0].heading, 'INT. INDEPENDENT SCENE 1 - DAY')
        self.assertEqual(restored_scenes[1].heading, 'INT. INDEPENDENT SCENE 2 - NIGHT')

        # Assert each scene has a distinct, valid UUID (no duplication)
        self.assertNotEqual(restored_scenes[0].scene_uuid, restored_scenes[1].scene_uuid)

        # Neither scene is intercut or linked ambiguously
        self.assertFalse(restored_scenes[0].is_intercut)
        self.assertFalse(restored_scenes[1].is_intercut)
        self.assertIsNone(restored_scenes[0].intercut_source)
        self.assertIsNone(restored_scenes[1].intercut_source)

    def test_17_mid_transaction_failure_rolls_back_detached_trash_metadata(self):
        """
        Test C — Failure inside the transaction:
        Construct a scenario containing:
        - An active main scene.
        - A trashed sub-scene attached to that active main scene.
        - Existing elements belonging to active and trashed scenes.
        - A valid snapshot to restore.

        Inject a controlled exception inside the transaction after Step A has detached the sub-scene.

        Assert that:
        - The original active scene row and its elements remain intact.
        - The trashed sub-scene row remains intact.
        - Its is_deleted, deleted_at, scene_uuid, parent_scene_id, and original parent metadata
          return to their exact pre-call values.
        - Elements belonging to the trashed sub-scene remain intact.
        - No partially restored scenes or elements remain.
        - The automatic pre-restoration snapshot survives the failed restoration.
        """
        # Active main scene
        sc_active = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE MAIN SCENE - DAY',
            order=0,
            is_deleted=False
        )
        elem_active = ScriptElement.objects.create(
            scene=sc_active,
            element_type='action',
            content='Active main action text',
            order=0
        )

        del_time = timezone.now()
        # Trashed sub-scene attached to active main scene
        sub_trashed = Scene.objects.create(
            script=self.script,
            parent_scene=sc_active,
            heading='INT. TRASHED SUB SCENE - DAY',
            order=1,
            is_deleted=True,
            deleted_at=del_time,
            original_parent_uuid=sc_active.scene_uuid,
            original_parent_scene_number=sc_active.scene_number,
            original_parent_heading=sc_active.heading
        )
        elem_trashed = ScriptElement.objects.create(
            scene=sub_trashed,
            element_type='dialogue',
            content='Trashed dialogue text',
            order=0
        )

        # Record exact pre-call values
        pre_active_id = sc_active.id
        pre_active_uuid = sc_active.scene_uuid
        pre_sub_id = sub_trashed.id
        pre_sub_uuid = sub_trashed.scene_uuid
        pre_sub_parent_id = sub_trashed.parent_scene_id
        pre_sub_orig_uuid = sub_trashed.original_parent_uuid
        pre_sub_orig_num = sub_trashed.original_parent_scene_number
        pre_sub_orig_hd = sub_trashed.original_parent_heading

        valid_snapshot = {
            'scenes': [
                {
                    'scene_uuid': str(uuid.uuid4()),
                    'scene_number': 1,
                    'heading': 'INT. RESTORED SCENE - NIGHT',
                    'order': 0,
                    'is_intercut': False,
                    'elements': [{'element_type': 'action', 'content': 'Restored action text', 'order': 0}],
                    'sub_scenes': []
                }
            ]
        }

        v_valid = ScriptVersion.objects.create(
            script=self.script,
            version_number=1,
            title='Valid Target Version',
            snapshot_data=valid_snapshot
        )

        initial_version_count = self.script.versions.count()

        # Inject exception inside transaction at resequence_script_scenes (Step F),
        # which runs after Step A (detaching trashed scenes), Step B (deleting active scenes),
        # and Step C/D/E (inserting restored scenes/elements).
        with patch('scripts.services.version_service.resequence_script_scenes', side_effect=RuntimeError("Simulated DB Crash Inside Transaction")):
            with self.assertRaises(RuntimeError):
                restore_version_snapshot(self.script, v_valid.id)

        # Invariant 1: Original active scene row and elements intact
        sc_active.refresh_from_db()
        self.assertEqual(sc_active.id, pre_active_id)
        self.assertEqual(sc_active.scene_uuid, pre_active_uuid)
        self.assertEqual(sc_active.heading, 'INT. ACTIVE MAIN SCENE - DAY')
        self.assertFalse(sc_active.is_deleted)
        self.assertTrue(ScriptElement.objects.filter(id=elem_active.id, content='Active main action text').exists())

        # Invariant 2: Trashed sub-scene row remains intact
        sub_trashed.refresh_from_db()
        self.assertEqual(sub_trashed.id, pre_sub_id)
        self.assertEqual(sub_trashed.scene_uuid, pre_sub_uuid)
        self.assertTrue(sub_trashed.is_deleted)
        self.assertEqual(sub_trashed.deleted_at, del_time)

        # Invariant 3: Exact pre-call values for parent_scene_id and original parent metadata restored
        self.assertEqual(sub_trashed.parent_scene_id, pre_sub_parent_id)
        self.assertEqual(sub_trashed.original_parent_uuid, pre_sub_orig_uuid)
        self.assertEqual(sub_trashed.original_parent_scene_number, pre_sub_orig_num)
        self.assertEqual(sub_trashed.original_parent_heading, pre_sub_orig_hd)

        # Invariant 4: Elements belonging to trashed sub-scene remain intact
        self.assertTrue(ScriptElement.objects.filter(id=elem_trashed.id, content='Trashed dialogue text').exists())

        # Invariant 5: No partially restored scenes or elements exist
        self.assertFalse(Scene.objects.filter(heading='INT. RESTORED SCENE - NIGHT').exists())
        self.assertFalse(ScriptElement.objects.filter(content='Restored action text').exists())

        # Invariant 6: The automatic pre-restoration snapshot survived because it was committed prior to transaction
        self.assertEqual(self.script.versions.count(), initial_version_count + 1)
        latest_version = self.script.versions.order_by('-version_number').first()
        self.assertIn('Auto-backup before restoring', latest_version.title)
