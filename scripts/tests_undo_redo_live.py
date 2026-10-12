import os
import time
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.models import Script, Scene, ScriptElement

CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"


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
class UndoRedoReliabilityLiveTests(StaticLiveServerTestCase):
    """
    Focused browser tests verifying Undo/Redo timing, debounce interaction,
    scene isolation, composition/Malayalam preservation, and save pipeline integration.
    """

    def setUp(self):
        User = get_user_model()
        self.username = f"undoredo_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")

        self.script = Script.objects.create(
            user=self.user,
            title="Undo Redo Test Script",
            script_type="Feature Film",
            language="Malayalam"
        )
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading="INT. LIVING ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="scene_heading",
            content="INT. LIVING ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="action",
            content="Initial action line.",
            order=1
        )

        self.scene2 = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading="EXT. GARDEN - NIGHT",
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type="scene_heading",
            content="EXT. GARDEN - NIGHT",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type="action",
            content="Scene two action line.",
            order=1
        )

    def get_driver(self):
        opts = Options()
        opts.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-cache")
        opts.add_argument("--incognito")
        opts.add_argument("--window-size=1280,900")

        if os.path.exists(CHROMEDRIVER_PATH):
            service = Service(executable_path=CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
        return driver

    def login_and_open_editor(self, driver):
        driver.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        driver.find_element(By.NAME, "username").send_keys(self.username)
        driver.find_element(By.NAME, "password").send_keys("password123")
        driver.find_element(By.NAME, "password").submit()
        WebDriverWait(driver, 10).until(EC.url_contains("/dashboard/"))

        driver.get(f"{self.live_server_url}/scripts/{self.script.id}/editor/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btnEnterEditMode")))

        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId.length > 0;
            """),
            message="Timed out waiting for initial scene to load into the canvas."
        )

        driver.execute_script("window.editorInstance.setEditorMode('edit');")

        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("""
                const page = document.getElementById('screenplayPage');
                return window.editorInstance.editorMode === 'edit' &&
                       page &&
                       getComputedStyle(page).display !== 'none';
            """),
            message="Timed out waiting for editor to switch into edit mode."
        )

    def test_01_immediate_undo_before_debounce(self):
        """1. Typing followed immediately by Undo (before 500ms debounce) restores baseline and clears timer."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                const baselineText = actionBlock.innerText;

                let customListenerInvoked = false;
                actionBlock.addEventListener('input', () => { customListenerInvoked = true; });

                actionBlock.innerText = baselineText + " Immediate typed edit.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));

                const timerBefore = Boolean(ed.textEditTimer);
                const timerSidBefore = ed.textEditTimerSceneId;

                // Test direct recordTextEdit if needed
                if (!timerBefore) {
                    ed.recordTextEdit();
                }
                const timerAfterRecord = Boolean(ed.textEditTimer);

                ed.undo();
                const freshActionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                const textAfterUndo = freshActionBlock ? freshActionBlock.innerText : null;

                return {
                    customListenerInvoked,
                    timerBefore,
                    timerSidBefore,
                    timerAfterRecord,
                    timerAfterUndo: Boolean(ed.textEditTimer),
                    textAfterUndo,
                    baselineText
                };
            """)

            self.assertTrue(res['timerBefore'], "Timer should be scheduled immediately after typing input")
            self.assertEqual(res['textAfterUndo'], res['baselineText'], "Immediate undo must restore baseline text")
            self.assertFalse(res['timerAfterUndo'], "Immediate undo must clear the pending textEditTimer")
        finally:
            driver.quit()

    def test_02_undo_after_debounce_expires(self):
        """2. Typing followed by waiting for 500ms debounce then Undo restores baseline."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                actionBlock.innerText = "Action text with debounce.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));
            """)

            # Wait 650ms for debounce to fire
            time.sleep(0.65)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const timerExpired = !ed.textEditTimer;
                const sid = Number(ed.currentSceneId);
                const undoStackLen = (ed.undoStacks[sid] || []).length;

                ed.undo();

                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                return {
                    timerExpired,
                    undoStackLen,
                    restoredText: actionBlock.innerText
                };
            """)

            self.assertTrue(res['timerExpired'], "Timer should have expired after 650ms")
            self.assertGreaterEqual(res['undoStackLen'], 2, "Debounced edit should be committed to undo stack")
            self.assertEqual(res['restoredText'], "Initial action line.", "Undo after debounce must restore original text")
        finally:
            driver.quit()

    def test_03_redo_after_undo(self):
        """3. Redo after immediate or debounced Undo restores the undone edit."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');

                // Immediate edit
                actionBlock.innerText = "Edit to be undone then redone.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));

                ed.undo();
                const textAfterUndo = (ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content') || {}).innerText;

                ed.redo();
                const textAfterRedo = (ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content') || {}).innerText;

                return {
                    textAfterUndo,
                    textAfterRedo
                };
            """)

            self.assertEqual(res['textAfterUndo'], "Initial action line.")
            self.assertEqual(res['textAfterRedo'], "Edit to be undone then redone.")
        finally:
            driver.quit()

    def test_04_repeated_undo_and_redo(self):
        """4. Repeated Undo and Redo maintain consistent stack ordering."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');

                // Step 1: structural edit (new block)
                ed.createElementBlock('character', 'HERO', ed.pageContainer.lastElementChild);
                ed.pushUndoSnapshot();

                // Step 2: edit character content
                const charEl = ed.pageContainer.querySelector('.script-element-block[data-type="character"] .element-content');
                charEl.innerText = "SUPER HERO";
                charEl.dispatchEvent(new Event('input', { bubbles: true }));
                ed.flushPendingTextEdit();

                // Step 3: undo character edit
                ed.undo();
                const charElAfterUndo1 = ed.pageContainer.querySelector('.script-element-block[data-type="character"] .element-content');
                const charAfterUndo1 = charElAfterUndo1 ? charElAfterUndo1.innerText : null;

                // Step 4: undo character creation
                ed.undo();
                const hasCharAfterUndo2 = Boolean(ed.pageContainer.querySelector('.script-element-block[data-type="character"]'));

                // Step 5: redo character creation
                ed.redo();
                const hasCharAfterRedo1 = Boolean(ed.pageContainer.querySelector('.script-element-block[data-type="character"]'));

                // Step 6: redo character edit
                ed.redo();
                const charElAfterRedo2 = ed.pageContainer.querySelector('.script-element-block[data-type="character"] .element-content');
                const charAfterRedo2 = charElAfterRedo2 ? charElAfterRedo2.innerText : null;

                return {
                    charAfterUndo1: charAfterUndo1,
                    hasCharAfterUndo2: hasCharAfterUndo2,
                    hasCharAfterRedo1: hasCharAfterRedo1,
                    charAfterRedo2: charAfterRedo2
                };
            """)

            self.assertEqual(res['charAfterUndo1'], "HERO")
            self.assertFalse(res['hasCharAfterUndo2'])
            self.assertTrue(res['hasCharAfterRedo1'])
            self.assertEqual(res['charAfterRedo2'], "SUPER HERO")
        finally:
            driver.quit()

    def test_05_new_edit_after_undo_clears_redo(self):
        """5. A new edit after Undo invalidates the redo branch."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const sid = Number(ed.currentSceneId);
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');

                actionBlock.innerText = "Branch A text.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));
                ed.flushPendingTextEdit();

                ed.undo();
                const redoCountAfterUndo = (ed.redoStacks[sid] || []).length;

                // Branch B edit
                actionBlock.innerText = "Branch B text.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));
                ed.flushPendingTextEdit();

                const redoCountAfterNewEdit = (ed.redoStacks[sid] || []).length;

                return {
                    redoCountAfterUndo,
                    redoCountAfterNewEdit
                };
            """)

            self.assertGreater(res['redoCountAfterUndo'], 0, "Redo stack should have item after undo")
            self.assertEqual(res['redoCountAfterNewEdit'], 0, "New edit must invalidate redo stack")
        finally:
            driver.quit()

    def test_06_structural_edit_undo_redo(self):
        """6. Structural edit (element insertion/deletion) followed by Undo and Redo."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const initialCount = ed.pageContainer.querySelectorAll('.script-element-block').length;

                const preSnap = ed.captureSnapshot();
                const newBlock = ed.createElementBlock('dialogue', 'A dialogue line.', ed.pageContainer.lastElementChild);
                ed.pushUndoSnapshot(preSnap);

                const countAfterAdd = ed.pageContainer.querySelectorAll('.script-element-block').length;

                ed.undo();
                const countAfterUndo = ed.pageContainer.querySelectorAll('.script-element-block').length;

                ed.redo();
                const countAfterRedo = ed.pageContainer.querySelectorAll('.script-element-block').length;

                return {
                    initialCount,
                    countAfterAdd,
                    countAfterUndo,
                    countAfterRedo
                };
            """)

            self.assertEqual(res['countAfterAdd'], res['initialCount'] + 1)
            self.assertEqual(res['countAfterUndo'], res['initialCount'])
            self.assertEqual(res['countAfterRedo'], res['initialCount'] + 1)
        finally:
            driver.quit()

    def test_07_pending_text_edit_followed_by_scene_switch(self):
        """7. Pending text edit in Scene 1 does not contaminate Scene 2 upon scene switch."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const s1Id = Number(ed.currentSceneId);

                // Modify text in scene 1
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                actionBlock.innerText = "Scene 1 edited uncommitted text.";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));

                const timerActiveBeforeSwitch = Boolean(ed.textEditTimer);
                const timerSidBeforeSwitch = ed.textEditTimerSceneId;

                return {
                    s1Id,
                    timerActiveBeforeSwitch,
                    timerSidBeforeSwitch
                };
            """)

            self.assertTrue(res['timerActiveBeforeSwitch'])
            self.assertEqual(res['timerSidBeforeSwitch'], res['s1Id'])

            # Switch scene immediately before 500ms debounce
            driver.execute_script(f"window.editorInstance.switchScene({self.scene2.id});")

            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script(f"""
                    return window.editorInstance &&
                           Number(window.editorInstance.currentSceneId) === {self.scene2.id} &&
                           !window.editorInstance.isSwitchingScene;
                """),
                message="Timed out waiting to switch to Scene 2"
            )

            # Wait to ensure any old debounce timer would have elapsed
            time.sleep(0.7)

            check = driver.execute_script("""
                const ed = window.editorInstance;
                const s2Id = arguments[0];
                const s1Id = arguments[1];

                const s2Stack = ed.undoStacks[s2Id] || [];
                // Check if s2 stack contains any scene 1 edited text
                const s2Corrupted = s2Stack.some(snap =>
                    (snap.elements || []).some(e => (e.content || '').includes("Scene 1 edited"))
                );

                // Scene 2 DOM content
                const s2DomText = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content').innerText;

                return {
                    s2Corrupted: s2Corrupted,
                    s2DomText: s2DomText,
                    timerActiveAfter: Boolean(ed.textEditTimer)
                };
            """, self.scene2.id, self.scene1.id)

            self.assertFalse(check['s2Corrupted'], "Scene 2 history stack must NOT contain Scene 1 content")
            self.assertEqual(check['s2DomText'], "Scene two action line.", "Scene 2 DOM must show Scene 2 content")
            self.assertFalse(check['timerActiveAfter'], "No stray timer should be active after scene load")
        finally:
            driver.quit()

    def test_08_malayalam_text_and_composition(self):
        """8. Malayalam Unicode is preserved exactly, and composition does not record mid-IME snapshots."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                const malayalamText = "നായകൻ മുറിയിലേക്ക് കയറി ചുറ്റും നോക്കുന്നു.";

                // Start IME composition
                actionBlock.dispatchEvent(new Event('compositionstart', { bubbles: true }));
                actionBlock.innerText = "നായ";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));

                const timerDuringComposition = Boolean(ed.textEditTimer);

                // End IME composition
                actionBlock.innerText = malayalamText;
                actionBlock.dispatchEvent(new Event('compositionend', { bubbles: true }));

                const timerAfterComposition = Boolean(ed.textEditTimer);

                // Undo immediately
                ed.undo();
                const afterUndo = (ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content') || {}).innerText;

                // Redo immediately
                ed.redo();
                const afterRedo = (ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content') || {}).innerText;

                return {
                    timerDuringComposition,
                    timerAfterComposition,
                    afterUndo,
                    afterRedo,
                    malayalamText
                };
            """)

            self.assertFalse(res['timerDuringComposition'], "Timer must not start during active composition")
            self.assertTrue(res['timerAfterComposition'], "Timer should start after compositionend")
            self.assertEqual(res['afterUndo'], "Initial action line.", "Undo restores baseline text")
            self.assertEqual(res['afterRedo'], res['malayalamText'], "Redo restores full Malayalam Unicode exactly")
        finally:
            driver.quit()

    def test_09_history_isolation_between_scenes(self):
        """9. History stacks remain strictly isolated between two scenes."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # Edit in Scene 1
            driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content');
                actionBlock.innerText = "Scene 1 Unique Change";
                actionBlock.dispatchEvent(new Event('input', { bubbles: true }));
                ed.flushPendingTextEdit();
            """)

            # Switch to Scene 2
            driver.execute_script(f"window.editorInstance.switchScene({self.scene2.id});")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script(f"""
                    return window.editorInstance &&
                           Number(window.editorInstance.currentSceneId) === {self.scene2.id} &&
                           !window.editorInstance.isSwitchingScene;
                """)
            )

            # In Scene 2, verify undo only affects Scene 2
            res = driver.execute_script("""
                const ed = window.editorInstance;
                const s2Id = arguments[0];
                const s1Id = arguments[1];

                const s2UndoLen = (ed.undoStacks[s2Id] || []).length;
                const s1UndoLen = (ed.undoStacks[s1Id] || []).length;

                // Attempt undo on Scene 2 (which has only baseline)
                ed.undo();
                const s2TextAfterUndo = ed.pageContainer.querySelector('.script-element-block[data-type="action"] .element-content').innerText;

                return {
                    s2UndoLen: s2UndoLen,
                    s1UndoLen: s1UndoLen,
                    s2TextAfterUndo: s2TextAfterUndo
                };
            """, self.scene2.id, self.scene1.id)

            self.assertEqual(res['s2UndoLen'], 1, "Scene 2 should have only 1 baseline snapshot")
            self.assertGreaterEqual(res['s1UndoLen'], 2, "Scene 1 should retain its own snapshots")
            self.assertEqual(res['s2TextAfterUndo'], "Scene two action line.", "Undo in Scene 2 should not alter Scene 2")
        finally:
            driver.quit()


    def test_10_undo_redo_save_pipeline_integrity(self):
        """10. Undo/Redo marks the editor dirty and persists the final state."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            driver.execute_script("""
                const ed = window.editorInstance;
                const actionBlock = ed.pageContainer.querySelector(
                    '.script-element-block[data-type="action"] .element-content'
                );

                actionBlock.innerText = "Modified line for save test.";
                actionBlock.dispatchEvent(
                    new Event('input', { bubbles: true })
                );
                ed.flushPendingTextEdit();
            """)

            # Undo and Redo must both mark the editor dirty.
            res = driver.execute_script("""
                const ed = window.editorInstance;

                ed.undo();
                const isDirtyAfterUndo = ed.isDirty;
                const changeVersionAfterUndo = ed.changeVersion;

                ed.redo();
                const isDirtyAfterRedo = ed.isDirty;
                const changeVersionAfterRedo = ed.changeVersion;

                return {
                    isDirtyAfterUndo,
                    changeVersionAfterUndo,
                    isDirtyAfterRedo,
                    changeVersionAfterRedo
                };
            """)

            self.assertTrue(
                res["isDirtyAfterUndo"],
                "Undo must mark the editor dirty."
            )
            self.assertGreater(
                res["changeVersionAfterUndo"], 0,
                "Undo must increment changeVersion."
            )
            self.assertTrue(
                res["isDirtyAfterRedo"],
                "Redo must mark the editor dirty."
            )
            self.assertGreater(
                res["changeVersionAfterRedo"],
                res["changeVersionAfterUndo"],
                "Redo must increment changeVersion."
            )

            # Trigger the existing save pipeline and wait until it finishes.
            driver.execute_script("""
                const ed = window.editorInstance;
                ed.saveCurrentScene();
            """)

            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("""
                    const ed = window.editorInstance;
                    return ed &&
                           !ed.isDirty &&
                           !ed.isSaving;
                """)
            )

            # Verify the saved action content in the isolated test database.
            saved_element = ScriptElement.objects.filter(
                scene=self.scene1,
                element_type="action"
            ).first()

            self.assertIsNotNone(
                saved_element,
                "The action element should exist in the test database."
            )
            self.assertEqual(
                saved_element.content,
                "Modified line for save test.",
                "Redo content must be persisted by the existing save pipeline."
            )

        finally:
            driver.quit()
