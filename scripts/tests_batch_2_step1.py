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
class ActionParagraphSplittingLiveTests(StaticLiveServerTestCase):
    """
    Automated browser tests for Issue C: Action Paragraph Splitting.
    Verifies:
    1. Enter in the middle of an action block (splits into two action blocks with exact text).
    2. Enter at the beginning of an action block (inserts empty block before, keeps text in second).
    3. Enter at the end of an action block (retains text in first, inserts empty block after).
    4. Enter with a text selection (replaces selection with block split).
    5. Malayalam Unicode preservation (vowel signs, chillu letters, punctuation).
    6. Empty action block handling.
    7. Correct element ordering and database persistence on save for all split cases.
    """

    def setUp(self):
        User = get_user_model()
        self.username = f"split_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")

        self.script = Script.objects.create(
            user=self.user,
            title="ഖണ്ഡിക വിഭജനം (Paragraph Split)",
            script_type="Feature Film",
            language="Malayalam"
        )
        self.scene = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading="INT. LIVING ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type="scene_heading",
            content="INT. LIVING ROOM - DAY",
            order=0
        )
        # Test Malayalam text with diacritics, chillu letters, and punctuation
        self.initial_text = "അനു വാതിലിലേക്ക് നോക്കി. റഹീം അകത്തേക്ക് വന്നു."
        self.elem_action = ScriptElement.objects.create(
            scene=self.scene,
            element_type="action",
            content=self.initial_text,
            order=1
        )

    def get_driver(self):
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-cache")
        opts.add_argument("--incognito")
        opts.add_argument("--window-size=1280,800")
        opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        if os.path.exists(CHROMEDRIVER_PATH):
            service = Service(executable_path=CHROMEDRIVER_PATH)
            return webdriver.Chrome(service=service, options=opts)
        return webdriver.Chrome(options=opts)

    def login_and_open_editor(self, driver):
        driver.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        driver.find_element(By.NAME, "username").send_keys(self.username)
        driver.find_element(By.NAME, "password").send_keys("password123")
        driver.find_element(By.NAME, "password").submit()
        WebDriverWait(driver, 10).until(EC.url_contains("/dashboard/"))

        # Navigate to editor
        driver.get(f"{self.live_server_url}/scripts/{self.script.id}/editor/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btnEnterEditMode")))

        # Wait until editor finishes initial async load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId.length > 0;
            """),
            message="Timed out waiting for initial scene data to load into the canvas."
        )

        # Switch to Edit Mode safely
        driver.execute_script("window.editorInstance.setEditorMode('edit');")

        # Wait until editor is in edit mode and action block is ready and displayed
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("""
                const page = document.getElementById('screenplayPage');
                const act = document.querySelector("#screenplayPage .script-element-block[data-type='action'] .element-content");
                return window.editorInstance.editorMode === 'edit' &&
                       page &&
                       getComputedStyle(page).display !== 'none' &&
                       act &&
                       act.innerText.trim().length > 0;
            """),
            message="Timed out waiting for editor to transition to edit mode."
        )

    def wait_for_save(self, driver, timeout=10):
        """
        Deterministic save completion waiter.
        Triggers saveCurrentScene(true) and verifies verified state properties:
        isDirty === false, isSaving === false, and saveBadge contains 'saved'.
        """
        driver.execute_script("window.editorInstance.saveCurrentScene(true);")
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isDirty &&
                       !window.editorInstance.isSaving &&
                       window.editorInstance.saveBadge &&
                       window.editorInstance.saveBadge.classList.contains('saved');
            """),
            message="Timed out waiting for saveCurrentScene() to finish saving to database."
        )

    def test_01_split_in_middle_malayalam(self):
        """Case A: Pressing Enter between two sentences splits the action block with exact text."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # Split between sentence 1 and sentence 2 inside the action element
            res = driver.execute_script("""
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const ed = actionBlock.querySelector(".element-content");
                if (!ed) throw new Error("Action element-content not found");
                ed.focus();

                // Find text node and index of period '.'
                let textNode = null;
                for (let n of ed.childNodes) {
                    if (n.nodeType === Node.TEXT_NODE) {
                        textNode = n;
                        break;
                    }
                }
                if (!textNode) textNode = ed.firstChild;
                if (!textNode || !textNode.textContent) throw new Error("Text node not found or empty");

                const text = textNode.textContent;
                const dotIdx = text.indexOf('.');
                if (dotIdx === -1) {
                    throw new Error("Target delimiter '.' not found in action text node: '" + text + "'");
                }
                const splitIndex = dotIdx + 1; // split right after period

                const range = document.createRange();
                range.setStart(textNode, splitIndex);
                range.collapse(true);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                // Invoke handleEnterKey via keyboard event
                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const blocks = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                return {
                    blocksCount: blocks.length,
                    firstText: blocks[0].querySelector('.element-content').innerText,
                    secondText: blocks[1].querySelector('.element-content').innerText
                };
            """)

            self.assertEqual(res['blocksCount'], 2, "Splitting in middle must produce exactly 2 action blocks")
            self.assertEqual(res['firstText'], "അനു വാതിലിലേക്ക് നോക്കി.", "First block text must match sentence 1 exactly")
            self.assertEqual(res['secondText'], "റഹീം അകത്തേക്ക് വന്നു.", "Second block text must match sentence 2 exactly")

            # Flush save deterministically and verify database persistence
            self.wait_for_save(driver)

            db_elements = list(ScriptElement.objects.filter(scene=self.scene, element_type='action').order_by('order'))
            self.assertEqual(len(db_elements), 2, "Database must persist exactly 2 action blocks")
            self.assertEqual(db_elements[0].content, "അനു വാതിലിലേക്ക് നോക്കി.")
            self.assertEqual(db_elements[1].content, "റഹീം അകത്തേക്ക് വന്നു.")
            self.assertLess(db_elements[0].order, db_elements[1].order)
        finally:
            driver.quit()

    def test_02_enter_at_beginning_inserts_empty_block_before(self):
        """Case B: Pressing Enter at index 0 inserts an empty block before and focuses the second block."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const ed = actionBlock.querySelector(".element-content");
                if (!ed) throw new Error("Action element-content not found");
                ed.focus();

                let textNode = null;
                for (let n of ed.childNodes) {
                    if (n.nodeType === Node.TEXT_NODE) {
                        textNode = n;
                        break;
                    }
                }
                if (!textNode) textNode = ed.firstChild;
                if (!textNode || !textNode.textContent) throw new Error("Text node not found or empty");

                // Place cursor at the very beginning (offset 0)
                const range = document.createRange();
                range.setStart(textNode, 0);
                range.collapse(true);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const blocks = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                return {
                    blocksCount: blocks.length,
                    firstText: blocks[0].querySelector('.element-content').innerText,
                    secondText: blocks[1].querySelector('.element-content').innerText,
                    isSecondActive: window.editorInstance.activeElementBlock === blocks[1]
                };
            """)

            self.assertEqual(res['blocksCount'], 2, "Enter at beginning must produce 2 action blocks")
            self.assertEqual(res['firstText'], "", "First block must be empty")
            self.assertEqual(res['secondText'], self.initial_text, "Second block must retain original text")
            self.assertTrue(res['isSecondActive'], "Active block must remain the second action block")

            # Verify database persistence
            self.wait_for_save(driver)
            db_elements = list(ScriptElement.objects.filter(scene=self.scene, element_type='action').order_by('order'))
            self.assertEqual(len(db_elements), 2)
            self.assertEqual(db_elements[0].content, "")
            self.assertEqual(db_elements[1].content, self.initial_text)
            self.assertLess(db_elements[0].order, db_elements[1].order)
        finally:
            driver.quit()

    def test_03_enter_at_end_inserts_empty_block_after(self):
        """Case C: Pressing Enter at the end creates an empty action block after."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const ed = actionBlock.querySelector(".element-content");
                if (!ed) throw new Error("Action element-content not found");
                ed.focus();

                let textNode = null;
                for (let n of ed.childNodes) {
                    if (n.nodeType === Node.TEXT_NODE) {
                        textNode = n;
                        break;
                    }
                }
                if (!textNode) textNode = ed.firstChild;
                if (!textNode || !textNode.textContent) throw new Error("Text node not found or empty");

                // Place cursor at end of text
                const range = document.createRange();
                range.setStart(textNode, textNode.textContent.length);
                range.collapse(true);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const blocks = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                return {
                    blocksCount: blocks.length,
                    firstText: blocks[0].querySelector('.element-content').innerText,
                    secondText: blocks[1].querySelector('.element-content').innerText,
                    isNewActive: window.editorInstance.activeElementBlock === blocks[1]
                };
            """)

            self.assertEqual(res['blocksCount'], 2)
            self.assertEqual(res['firstText'], self.initial_text, "First block must retain original text unchanged")
            self.assertEqual(res['secondText'], "", "Second block must be an empty action block")
            self.assertTrue(res['isNewActive'], "Focus must move to the newly created empty block")

            # Verify database persistence
            self.wait_for_save(driver)
            db_elements = list(ScriptElement.objects.filter(scene=self.scene, element_type='action').order_by('order'))
            self.assertEqual(len(db_elements), 2)
            self.assertEqual(db_elements[0].content, self.initial_text)
            self.assertEqual(db_elements[1].content, "")
            self.assertLess(db_elements[0].order, db_elements[1].order)
        finally:
            driver.quit()

    def test_04_enter_with_selection_replaces_selection_with_split(self):
        """Case D: Pressing Enter with a text selection drops the selection and splits remaining text."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const ed = actionBlock.querySelector(".element-content");
                if (!ed) throw new Error("Action element-content not found");
                ed.focus();

                let textNode = null;
                for (let n of ed.childNodes) {
                    if (n.nodeType === Node.TEXT_NODE) {
                        textNode = n;
                        break;
                    }
                }
                if (!textNode) textNode = ed.firstChild;
                if (!textNode || !textNode.textContent) throw new Error("Text node not found or empty");

                // Select the word "വാതിലിലേക്ക്"
                const text = textNode.textContent;
                const word = "വാതിലിലേക്ക്";
                const startIdx = text.indexOf(word);
                if (startIdx === -1) {
                    throw new Error("Target selection word '" + word + "' not found in text node: '" + text + "'");
                }
                const endIdx = startIdx + word.length;

                const range = document.createRange();
                range.setStart(textNode, startIdx);
                range.setEnd(textNode, endIdx);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const blocks = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                return {
                    blocksCount: blocks.length,
                    firstText: blocks[0].querySelector('.element-content').innerText,
                    secondText: blocks[1].querySelector('.element-content').innerText
                };
            """)

            self.assertEqual(res['blocksCount'], 2)
            self.assertEqual(res['firstText'], "അനു", "First block must be exact left text without selection")
            self.assertEqual(res['secondText'], "നോക്കി. റഹീം അകത്തേക്ക് വന്നു.", "Second block must retain text after selection")

            # Verify database persistence
            self.wait_for_save(driver)
            db_elements = list(ScriptElement.objects.filter(scene=self.scene, element_type='action').order_by('order'))
            self.assertEqual(len(db_elements), 2)
            self.assertEqual(db_elements[0].content, "അനു")
            self.assertEqual(db_elements[1].content, "നോക്കി. റഹീം അകത്തേക്ക് വന്നു.")
            self.assertLess(db_elements[0].order, db_elements[1].order)
        finally:
            driver.quit()

    def test_05_enter_in_empty_action_block(self):
        """Case 5: Pressing Enter in an empty action block creates another empty action block after it."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const ed = actionBlock.querySelector(".element-content");
                if (!ed) throw new Error("Action element-content not found");
                ed.innerText = '';
                ed.focus();

                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const blocks = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                return {
                    blocksCount: blocks.length,
                    firstText: blocks[0].querySelector('.element-content').innerText,
                    secondText: blocks[1].querySelector('.element-content').innerText
                };
            """)

            self.assertEqual(res['blocksCount'], 2)
            self.assertEqual(res['firstText'], "", "First block must remain empty")
            self.assertEqual(res['secondText'], "", "Second block must be created empty")

            # Verify database persistence
            self.wait_for_save(driver)
            db_elements = list(ScriptElement.objects.filter(scene=self.scene, element_type='action').order_by('order'))
            self.assertEqual(len(db_elements), 2)
            self.assertEqual(db_elements[0].content, "")
            self.assertEqual(db_elements[1].content, "")
            self.assertLess(db_elements[0].order, db_elements[1].order)
        finally:
            driver.quit()
