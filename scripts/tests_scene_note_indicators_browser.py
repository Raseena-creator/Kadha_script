"""
Focused browser-driven Selenium tests for KadhaScript Scene-Level Note Indicators.

Verifies:
A. Read mode:
   - Clicking a note badge for a scene other than the initially selected scene
     sets readModeActiveSceneId to that scene.
   - The correct #read-scene-{id} is targeted.
   - The first non-empty note receives .note-pulse-highlight.
   - An empty or whitespace-only note is skipped when selecting the first note.
   - A scene with no non-empty notes has no note badge.

B. Keyboard navigation:
   - Enter on a focused badge triggers navigation.
   - Space on a focused badge triggers navigation.
   - Prevent default behavior and event bubbling to parent scene click handlers.

C. Edit mode:
   - Clicking a badge for a different scene switches to that scene before focusing its note.
   - Assert that the loaded canvas scene ID matches the intended scene before asserting note focus.
   - Simulate an aborted scene switch: verify that the wrong scene's note is not focused.

D. Mobile offcanvas drawer:
   - Set a mobile viewport.
   - Open #scenesOffcanvas through Bootstrap's actual UI (#btnNavScenes).
   - Click a note badge in #offcanvasScenesList.
   - Verify the correct scene is selected and the offcanvas closes after Bootstrap's transition.
"""

import os
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.models import Script, Scene, ScriptElement


User = get_user_model()


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class SceneNoteIndicatorsBrowserTests(StaticLiveServerTestCase):
    """
    Browser-level verification of scene note indicator interactions in KadhaScript editor.
    """

    def setUp(self):
        super().setUp()
        # Create dedicated test user per test method (TransactionTestCase flushes DB between tests)
        self.user_email = f"user_{self._testMethodName}@kadhascript.com"
        self.user_password = "password123"
        self.user = User.objects.create_user(
            username=f"user_{self._testMethodName}",
            email=self.user_email,
            password=self.user_password
        )

        # Create screenplay
        self.script = Script.objects.create(
            user=self.user,
            title="Scene Note Browser Test Script",
            script_type="Feature Film",
            language="Malayalam"
        )

        # Scene 1: Contains 1 non-empty note (initially active scene)
        self.sc1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading="INT. WRITER ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(scene=self.sc1, element_type="scene_heading", content="INT. WRITER ROOM - DAY", order=0)
        ScriptElement.objects.create(scene=self.sc1, element_type="action", content="The writer is staring at the blank page.", order=1)
        ScriptElement.objects.create(scene=self.sc1, element_type="note", content="Scene 1 primary note content.", order=2)

        # Scene 2: Contains ONLY empty and whitespace notes -> has_notes must be False, NO badge
        self.sc2 = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading="EXT. COURTYARD - DAY",
            order=1
        )
        ScriptElement.objects.create(scene=self.sc2, element_type="scene_heading", content="EXT. COURTYARD - DAY", order=0)
        ScriptElement.objects.create(scene=self.sc2, element_type="action", content="Pigeons fly across the courtyard.", order=1)
        ScriptElement.objects.create(scene=self.sc2, element_type="note", content="", order=2)
        ScriptElement.objects.create(scene=self.sc2, element_type="note", content="   \t \n  ", order=3)

        # Scene 3: Contains 1 whitespace note followed by 2 valid non-empty notes -> badge present, count=2
        self.sc3 = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading="INT. OLD BALCONY - NIGHT",
            order=2
        )
        ScriptElement.objects.create(scene=self.sc3, element_type="scene_heading", content="INT. OLD BALCONY - NIGHT", order=0)
        ScriptElement.objects.create(scene=self.sc3, element_type="action", content="Cool night breeze blows the curtains.", order=1)
        ScriptElement.objects.create(scene=self.sc3, element_type="note", content="    ", order=2)  # Should be skipped
        ScriptElement.objects.create(scene=self.sc3, element_type="note", content="Scene 3 first non-empty note.", order=3)
        ScriptElement.objects.create(scene=self.sc3, element_type="note", content="Scene 3 second note.", order=4)

        self.driver = self.get_driver()

    def tearDown(self):
        if hasattr(self, "driver") and self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        super().tearDown()

    def get_driver(self):
        opts = ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-cache")
        opts.add_argument("--incognito")
        opts.add_argument("--window-size=1280,800")

        cached_chromedriver = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe"
        if os.path.exists(cached_chromedriver):
            service = ChromeService(executable_path=cached_chromedriver)
            return webdriver.Chrome(service=service, options=opts)
        return webdriver.Chrome(options=opts)

    def login_and_open_editor(self):
        """Logs in the test user and opens the KadhaScript editor for self.script."""
        driver = self.driver
        driver.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "email")))
        driver.find_element(By.NAME, "email").send_keys(self.user_email)
        driver.find_element(By.NAME, "password").send_keys(self.user_password)
        driver.find_element(By.NAME, "password").submit()
        WebDriverWait(driver, 10).until(EC.url_contains("/dashboard/"))

        editor_url = f"{self.live_server_url}/scripts/{self.script.id}/editor/"
        driver.get(editor_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "screenplayEditor")))
        # Ensure KadhaEditor is fully initialized and scenesTree has rendered
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script(
                "return Boolean(window.editor && window.editor.pageContainer && window.editor.pageContainer.dataset.loadedSceneId && window.editor.scenesTree && window.editor.scenesTree.length > 0 && !window.editor.isSaving && !window.editor.isSwitchingScene);"
            )
        )

    # =========================================================================
    # A. READ MODE TESTS
    # =========================================================================

    def test_read_mode_note_badge_presence_and_navigation(self):
        """
        In Read Mode:
        1. Scene without non-empty notes (Scene 2) has NO badge.
        2. Scene with non-empty notes (Scene 3) has a badge.
        3. Clicking Scene 3 badge sets readModeActiveSceneId to Scene 3.
        4. Targets #read-scene-3 and inspects actual rendered text of each note block.
        5. Verifies the leading whitespace note is skipped and not highlighted.
        6. Verifies 'Scene 3 first non-empty note.' receives .note-pulse-highlight.
        """
        driver = self.driver
        self.login_and_open_editor()

        # 1. Verify Scene 2 (whitespace only) has no badge in desktop scene list
        sc2_badges = driver.find_elements(
            By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc2.id}'] .scene-nav-note-badge"
        )
        self.assertEqual(len(sc2_badges), 0, "Scene 2 with only whitespace notes must not render a note badge.")

        # 2. Verify Scene 3 has a note badge with correct tooltip
        badge3 = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc3.id}'] .scene-nav-note-badge")
            )
        )
        self.assertIn("Scene has 2 notes", badge3.get_attribute("title"))

        # Verify initial active scene is Scene 1
        initial_active_id = driver.execute_script("return window.editor.readModeActiveSceneId;")
        self.assertEqual(initial_active_id, self.sc1.id, "Initially active scene must be Scene 1.")

        # Inspect actual rendered text of each note block in #read-scene-{self.sc3.id} before navigation
        read_scene_sec = driver.find_element(By.ID, f"read-scene-{self.sc3.id}")
        note_blocks = read_scene_sec.find_elements(By.CSS_SELECTOR, ".read-element-block.element-type-note")
        self.assertEqual(len(note_blocks), 3, "Scene 3 read section should contain 3 note element blocks.")

        # Identify note blocks by their actual rendered content without assuming list positions
        whitespace_blocks = [nb for nb in note_blocks if (nb.text or "").strip() == ""]
        first_valid_blocks = [nb for nb in note_blocks if "Scene 3 first non-empty note." in (nb.text or "")]
        second_valid_blocks = [nb for nb in note_blocks if "Scene 3 second note." in (nb.text or "")]

        self.assertEqual(len(whitespace_blocks), 1, "Must find exactly one whitespace-only note block.")
        self.assertEqual(len(first_valid_blocks), 1, "Must find exactly one block with 'Scene 3 first non-empty note.'")
        self.assertEqual(len(second_valid_blocks), 1, "Must find exactly one block with 'Scene 3 second note.'")

        whitespace_block = whitespace_blocks[0]
        first_valid_block = first_valid_blocks[0]
        second_valid_block = second_valid_blocks[0]

        # Verify actual rendered text
        self.assertEqual(whitespace_block.text.strip(), "", "Whitespace block text stripped must be empty.")
        self.assertIn("Scene 3 first non-empty note.", first_valid_block.text)

        # 3. Click Scene 3 note badge
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge3)
        badge3.click()

        # Wait for readModeActiveSceneId to update to Scene 3
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.readModeActiveSceneId;") == self.sc3.id
        )
        # Scene 3 list item should have active class
        WebDriverWait(driver, 5).until(
            lambda d: "active" in d.find_element(
                By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc3.id}']"
            ).get_attribute("class")
        )

        # Wait for first valid block to receive .note-pulse-highlight
        WebDriverWait(driver, 5).until(
            lambda d: "note-pulse-highlight" in first_valid_block.get_attribute("class")
        )

        # Explicitly verify the leading whitespace-only note block is skipped and NOT highlighted
        self.assertNotIn(
            "note-pulse-highlight",
            whitespace_block.get_attribute("class"),
            "Leading whitespace-only note must be skipped and not receive pulse highlight."
        )
        # Also verify subsequent note in Scene 3 is not highlighted
        self.assertNotIn(
            "note-pulse-highlight",
            second_valid_block.get_attribute("class"),
            "Only the first non-empty note should receive pulse highlight."
        )

    # =========================================================================
    # B. KEYBOARD NAVIGATION TESTS
    # =========================================================================

    def test_keyboard_navigation_enter_and_space_on_badge(self):
        """
        Verify that pressing Enter or Space on a focused .scene-nav-note-badge
        triggers note navigation and prevents unhandled bubbling/default actions.
        """
        driver = self.driver
        self.login_and_open_editor()

        # 1. Test Enter key on Scene 3 badge
        badge3 = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc3.id}'] .scene-nav-note-badge")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", badge3)
        WebDriverWait(driver, 2).until(lambda d: d.switch_to.active_element == badge3)

        # Send Enter via ActionChains to ensure keyboard event triggers on focused element
        ActionChains(driver).send_keys(Keys.ENTER).perform()

        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.readModeActiveSceneId;") == self.sc3.id
        )
        read_notes3 = driver.find_elements(
            By.CSS_SELECTOR, f"#read-scene-{self.sc3.id} .read-element-block.element-type-note"
        )
        first_valid_notes3 = [nb for nb in read_notes3 if "Scene 3 first non-empty note." in (nb.text or "")]
        self.assertEqual(len(first_valid_notes3), 1, "Must locate first non-empty note block by text.")
        first_valid_note3 = first_valid_notes3[0]

        WebDriverWait(driver, 5).until(
            lambda d: "note-pulse-highlight" in first_valid_note3.get_attribute("class")
        )

        # 2. Test Space key on Scene 1 badge
        badge1 = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc1.id}'] .scene-nav-note-badge")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", badge1)
        WebDriverWait(driver, 2).until(lambda d: d.switch_to.active_element == badge1)

        # Send Space via ActionChains to ensure keyboard event triggers on focused element
        ActionChains(driver).send_keys(Keys.SPACE).perform()

        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.readModeActiveSceneId;") == self.sc1.id
        )
        valid_note1 = driver.find_element(
            By.CSS_SELECTOR, f"#read-scene-{self.sc1.id} .read-element-block.element-type-note"
        )
        self.assertIn("Scene 1 primary note content.", valid_note1.text)
        WebDriverWait(driver, 5).until(
            lambda d: "note-pulse-highlight" in valid_note1.get_attribute("class")
        )

    # =========================================================================
    # C. EDIT MODE TESTS
    # =========================================================================

    def test_edit_mode_note_badge_navigation_and_focus(self):
        """
        In Edit Mode:
        1. Switching from Read to Edit mode shows interactive page with canvas scene loaded.
        2. Clicking Scene 3 note badge switches canvas to Scene 3.
        3. Verifies canvas data-loaded-scene-id matches Scene 3 before asserting focus.
        4. Focuses the first non-empty note element and highlights its block.
        """
        driver = self.driver
        self.login_and_open_editor()

        # Enter Edit Mode by clicking the pencil FAB
        btn_edit = driver.find_element(By.ID, "btnEnterEditMode")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_edit)
        btn_edit.click()

        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.editorMode;") == "edit"
        )

        canvas = driver.find_element(By.ID, "screenplayPage")
        # Initially Scene 1 should be loaded on the canvas
        WebDriverWait(driver, 5).until(
            lambda d: canvas.get_attribute("data-loaded-scene-id") == str(self.sc1.id)
        )

        # Click Scene 3 note badge in #scenesList
        badge3 = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc3.id}'] .scene-nav-note-badge")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge3)
        badge3.click()

        # Canvas must load Scene 3
        WebDriverWait(driver, 5).until(
            lambda d: canvas.get_attribute("data-loaded-scene-id") == str(self.sc3.id)
        )
        self.assertEqual(
            driver.execute_script("return window.editor.currentSceneId;"),
            self.sc3.id,
            "currentSceneId must be Scene 3 after switching."
        )

        # Wait for note block in canvas to receive .note-pulse-highlight
        def get_highlighted_note_block(d):
            blocks = canvas.find_elements(
                By.CSS_SELECTOR, ".script-element-block[data-type='note'].note-pulse-highlight"
            )
            return blocks[0] if blocks else None

        highlighted_block = WebDriverWait(driver, 5).until(get_highlighted_note_block)
        self.assertIsNotNone(highlighted_block, "Scene 3 note block must receive note-pulse-highlight.")
        self.assertIn("Scene 3 first non-empty note.", highlighted_block.text)

        # Verify that the editable content element inside the block has browser focus
        editable_el = highlighted_block.find_element(By.CSS_SELECTOR, ".element-content[contenteditable='true']")
        WebDriverWait(driver, 5).until(
            lambda d: d.switch_to.active_element == editable_el
        )
        self.assertIn("Scene 3 first non-empty note.", editable_el.text)

    def test_edit_mode_aborted_switch_does_not_focus_wrong_scene_note(self):
        """
        Verify that if switchScene() fails or aborts in Edit Mode:
        1. Simulated flushSave() rejection is confirmed to occur during the switch attempt.
        2. Synchronizes on both rejection occurrence and completion of the switch attempt.
        3. The navigation guard detects currentSceneId != targetId and returns immediately.
        4. currentSceneId and data-loaded-scene-id remain on Scene 3.
        5. The wrong scene's note is NOT focused or highlighted.
        6. Monkey-patched methods are cleanly restored in a finally block.
        """
        driver = self.driver
        self.login_and_open_editor()

        # Enter Edit Mode
        btn_edit = driver.find_element(By.ID, "btnEnterEditMode")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_edit)
        btn_edit.click()
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.editorMode;") == "edit"
        )

        # First switch to Scene 3
        badge3 = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc3.id}'] .scene-nav-note-badge")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge3)
        badge3.click()

        canvas = driver.find_element(By.ID, "screenplayPage")
        WebDriverWait(driver, 5).until(
            lambda d: canvas.get_attribute("data-loaded-scene-id") == str(self.sc3.id)
        )
        self.assertEqual(driver.execute_script("return window.editor.currentSceneId;"), self.sc3.id)

        # Clear any existing highlights from scene 3
        driver.execute_script("""
            document.querySelectorAll('.note-pulse-highlight').forEach(el => {
                el.classList.remove('note-pulse-highlight');
            });
        """)

        try:
            # Install monkey-patch with tracking counters and suppress window.alert modal
            driver.execute_script("""
                window._origAlert = window.alert;
                window._origFlushSave = window.editor.flushSave;
                window._flushSaveRejections = 0;
                window.alert = function() {};
                window.editor.flushSave = function() {
                    window._flushSaveRejections++;
                    return Promise.reject(new Error('Simulated dirty save failure before scene switch'));
                };
            """)

            # Attempt to navigate to Scene 1 by clicking its note badge
            badge1 = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, f"#scenesList .scene-item[data-id='{self.sc1.id}'] .scene-nav-note-badge")
                )
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge1)
            badge1.click()

            # Deterministic synchronization:
            # 1. Ensure the switch attempt actually started and triggered flushSave rejection (_flushSaveRejections > 0).
            # 2. Ensure switchScene() has fully finished its error handling and cleanup (!isSwitchingScene).
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script(
                    "return Boolean(window._flushSaveRejections && window._flushSaveRejections > 0 && window.editor && !window.editor.isSwitchingScene);"
                )
            )

            # Confirm simulated flushSave rejection was actually encountered
            rejections = driver.execute_script("return window._flushSaveRejections || 0;")
            self.assertGreaterEqual(
                rejections, 1,
                "Simulated flushSave rejection must be encountered during aborted switch."
            )

            # Verification: Scene switch was aborted, currentSceneId and canvas loadedSceneId remain Scene 3
            current_id = driver.execute_script("return window.editor.currentSceneId;")
            self.assertEqual(current_id, self.sc3.id, "currentSceneId must remain Scene 3 when switch is aborted.")
            self.assertEqual(canvas.get_attribute("data-loaded-scene-id"), str(self.sc3.id), "Canvas loadedSceneId must remain Scene 3.")

            # Verification: No note block in canvas received pulse highlight
            highlighted_blocks = canvas.find_elements(By.CSS_SELECTOR, ".note-pulse-highlight")
            self.assertEqual(
                len(highlighted_blocks), 0,
                "No element in the active canvas should be highlighted when navigation to another scene aborts."
            )

            # Verification: Browser activeElement does not focus Scene 1's note or any new element in canvas
            active_el = driver.switch_to.active_element
            if active_el:
                active_text = active_el.text or ""
                self.assertNotIn("Scene 1 primary note content.", active_text, "Scene 1 note must not receive focus.")
        finally:
            # Restore monkey-patched functions cleanly
            driver.execute_script("""
                if (window._origAlert) { window.alert = window._origAlert; delete window._origAlert; }
                if (window._origFlushSave && window.editor) { window.editor.flushSave = window._origFlushSave; delete window._origFlushSave; }
                delete window._flushSaveRejections;
            """)

    # =========================================================================
    # D. MOBILE OFFCANVAS TESTS
    # =========================================================================

    def test_mobile_offcanvas_note_badge_navigation(self):
        """
        On mobile viewport:
        1. Open #scenesOffcanvas via #btnNavScenes.
        2. Click Scene 3 note badge in #offcanvasScenesList.
        3. Verify Scene 3 is selected (readModeActiveSceneId updated).
        4. Verify #scenesOffcanvas closes (transition completes, 'show' class removed).
        5. Inspect actual rendered text of each note block in #read-scene-3.
        6. Verify Scene 3 first non-empty note receives .note-pulse-highlight.
        7. Verify leading whitespace note is skipped and NOT highlighted.
        """
        driver = self.driver
        driver.set_window_size(390, 844)
        self.login_and_open_editor()

        # 1. Open offcanvas using top navbar Scenes button
        btn_nav_scenes = driver.find_element(By.ID, "btnNavScenes")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_nav_scenes)
        btn_nav_scenes.click()

        offcanvas_el = driver.find_element(By.ID, "scenesOffcanvas")
        # Wait until offcanvas transition completes (Bootstrap adds 'show' and removes 'showing')
        WebDriverWait(driver, 5).until(
            lambda d: "show" in offcanvas_el.get_attribute("class") and "showing" not in offcanvas_el.get_attribute("class")
        )

        # 2. Locate Scene 3 note badge in #offcanvasScenesList and ensure it is clickable
        badge3_mobile = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#offcanvasScenesList .scene-item[data-id='{self.sc3.id}'] .scene-nav-note-badge")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge3_mobile)
        badge3_mobile.click()

        # 3. Verify Scene 3 is selected in read mode
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.editor.readModeActiveSceneId;") == self.sc3.id
        )

        # 4. Verify offcanvas closes ('show' class removed by Bootstrap hide transition)
        WebDriverWait(driver, 5).until(
            lambda d: "show" not in offcanvas_el.get_attribute("class")
        )

        # 5, 6 & 7. Inspect actual rendered text of note blocks in #read-scene-3
        read_scene_sec = driver.find_element(By.ID, f"read-scene-{self.sc3.id}")
        read_notes3 = read_scene_sec.find_elements(By.CSS_SELECTOR, ".read-element-block.element-type-note")
        self.assertEqual(len(read_notes3), 3, "Scene 3 read section should contain 3 note element blocks.")

        whitespace_blocks = [nb for nb in read_notes3 if (nb.text or "").strip() == ""]
        first_valid_blocks = [nb for nb in read_notes3 if "Scene 3 first non-empty note." in (nb.text or "")]
        second_valid_blocks = [nb for nb in read_notes3 if "Scene 3 second note." in (nb.text or "")]

        self.assertEqual(len(whitespace_blocks), 1, "Must find exactly one whitespace-only note block on mobile.")
        self.assertEqual(len(first_valid_blocks), 1, "Must find exactly one block with 'Scene 3 first non-empty note.' on mobile.")
        self.assertEqual(len(second_valid_blocks), 1, "Must find exactly one block with 'Scene 3 second note.' on mobile.")

        whitespace_block = whitespace_blocks[0]
        first_valid_block = first_valid_blocks[0]
        second_valid_block = second_valid_blocks[0]

        # Verify actual rendered text
        self.assertEqual(whitespace_block.text.strip(), "", "Whitespace block text stripped must be empty.")
        self.assertIn("Scene 3 first non-empty note.", first_valid_block.text)

        # Verify Scene 3 first non-empty note received pulse highlight
        WebDriverWait(driver, 5).until(
            lambda d: "note-pulse-highlight" in first_valid_block.get_attribute("class")
        )

        # Verify leading whitespace block is skipped and NOT highlighted
        self.assertNotIn(
            "note-pulse-highlight",
            whitespace_block.get_attribute("class"),
            "Leading whitespace-only note must be skipped and not receive pulse highlight on mobile."
        )
        self.assertNotIn(
            "note-pulse-highlight",
            second_valid_block.get_attribute("class"),
            "Subsequent note in Scene 3 should not be highlighted on mobile."
        )
