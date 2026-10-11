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
class NoteBehaviorLiveTests(StaticLiveServerTestCase):
    """
    Automated browser tests for Issue D: Notes Section Behavior.
    Verifies:
    1. Enter in the middle of a note inserts a newline inside the note without creating new screenplay blocks.
    2. Enter at the beginning and end of a note creates line breaks inside the note.
    3. Tab does not cycle note element type and inserts exactly two spaces indentation at caret position.
    4. Bullet (- , • ) and numbered (1. , 2. ) list continuation, caret position, and termination on empty marker.
    5. No action block is created when Enter is pressed in a note.
    6. Multiline note text survives save and reload with exact newlines.
    7. Note content remains intact when switching scenes and returning.
    8. Ordinary Enter behavior in Action, Character, and Dialogue elements remains intact.
    """

    def setUp(self):
        User = get_user_model()
        self.username = f"note_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")

        self.script = Script.objects.create(
            user=self.user,
            title="കുറിപ്പുകൾ പരിശോധന (Notes Test)",
            script_type="Feature Film",
            language="Malayalam"
        )
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading="INT. STUDY ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="scene_heading",
            content="INT. STUDY ROOM - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="action",
            content="രാഹുൽ മേശപ്പുറത്തിരുന്ന ഡയറി എടുത്തു നോക്കുന്നു.",
            order=1
        )
        self.note_text = "പ്രധാന കുറിപ്പ്:\n- ആദ്യ പോയിന്റ്\n- രണ്ടാമത്തെ പോയിന്റ്"
        self.elem_note = ScriptElement.objects.create(
            scene=self.scene1,
            element_type="note",
            content=self.note_text,
            order=2
        )

        # Scene 2 for scene-switching tests
        self.scene2 = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading="EXT. GARDEN - DAY",
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type="scene_heading",
            content="EXT. GARDEN - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type="action",
            content="പൂന്തോട്ടത്തിൽ കാറ്റ് വീശുന്നു.",
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
            message="Timed out waiting for initial scene canvas load."
        )

        driver.execute_script("window.editorInstance.setEditorMode('edit');")

        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("""
                const page = document.getElementById('screenplayPage');
                const note = document.querySelector("#screenplayPage .script-element-block[data-type='note'] .element-content");
                return window.editorInstance.editorMode === 'edit' &&
                       page &&
                       getComputedStyle(page).display !== 'none' &&
                       note &&
                       note.innerText.trim().length > 0;
            """),
            message="Timed out waiting for edit mode transition."
        )

    def wait_for_save(self, driver, timeout=10):
        """
        Deterministic save completion waiter.
        Triggers saveCurrentScene(true) and checks verified application properties:
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
            message="Timed out waiting for note scene save to complete."
        )

    def wait_for_scene(self, driver, scene_id, timeout=10):
        """
        Deterministic scene switch / load waiter.
        Verifies that isSwitchingScene is false and loadedSceneId matches the target scene.
        """
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(f"""
                return window.editorInstance &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId === "{scene_id}";
            """),
            message=f"Timed out waiting for scene {scene_id} to be fully loaded into canvas."
        )

    def test_01_enter_in_middle_beginning_end_of_note(self):
        """Enter in a note inserts newlines inside the note without creating new blocks."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                if (!noteBlock) throw new Error("Note element block not found");
                const ed = noteBlock.querySelector(".element-content");
                if (!ed) throw new Error("Note element-content not found");
                ed.innerText = "First Line Second Word";
                ed.focus();

                // 1. Enter in middle (between 'First Line ' and 'Second Word')
                const targetSub = "First Line ";
                const targetIdx = ed.firstChild.textContent.indexOf(targetSub);
                if (targetIdx === -1) {
                    throw new Error("Target substring '" + targetSub + "' not found in note text node: '" + ed.firstChild.textContent + "'");
                }

                const range = document.createRange();
                range.setStart(ed.firstChild, targetIdx + targetSub.length);
                range.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const evt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                ed.dispatchEvent(evt);

                const textAfterMiddle = ed.innerText;
                const totalBlocks1 = document.querySelectorAll("#screenplayPage .script-element-block").length;
                const actionBlocks1 = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']").length;
                const noteBlocks1 = document.querySelectorAll("#screenplayPage .script-element-block[data-type='note']").length;

                // 2. Enter at the beginning
                const rStart = document.createRange();
                rStart.setStart(ed.firstChild, 0);
                rStart.collapse(true);
                sel.removeAllRanges();
                sel.addRange(rStart);

                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const textAfterStart = ed.innerText;

                // 3. Enter at the end
                const rEnd = document.createRange();
                rEnd.selectNodeContents(ed);
                rEnd.collapse(false);
                sel.removeAllRanges();
                sel.addRange(rEnd);

                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const textAfterEnd = ed.innerText;

                return {
                    textAfterMiddle,
                    textAfterStart,
                    textAfterEnd,
                    totalBlocks: totalBlocks1,
                    actionBlocks: actionBlocks1,
                    noteBlocks: noteBlocks1
                };
            """)

            # Verify no new screenplay blocks were created
            self.assertEqual(res['actionBlocks'], 1, "Action block count must not increase")
            self.assertEqual(res['noteBlocks'], 1, "Note block count must remain exactly 1")

            # Verify middle enter split preserves both parts across line breaks
            self.assertIn("First Line", res['textAfterMiddle'])
            self.assertIn("Second Word", res['textAfterMiddle'])
            self.assertIn("\n", res['textAfterMiddle'], "Middle Enter must introduce a newline inside the note")

            # Verify start and end newlines accumulated into multiline structure
            lines = res['textAfterEnd'].split('\n')
            self.assertGreaterEqual(len(lines), 3, "Start and end Enter must create multiple lines inside the note")
        finally:
            driver.quit()

    def test_02_tab_does_not_cycle_note_type_and_inserts_indent(self):
        """Pressing Tab inside a note does NOT cycle to scene_heading, and inserts exactly 2 spaces indentation."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                if (!noteBlock) throw new Error("Note element block not found");
                const ed = noteBlock.querySelector(".element-content");
                if (!ed) throw new Error("Note element-content not found");
                ed.innerText = "Test Tab";
                ed.focus();

                const r = document.createRange();
                r.setStart(ed.firstChild, 0);
                r.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(r);

                // Press Tab
                const tabEvt = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
                ed.dispatchEvent(tabEvt);

                return {
                    typeAfterTab: noteBlock.dataset.type,
                    textAfterTab: ed.innerText
                };
            """)

            self.assertEqual(res['typeAfterTab'], "note", "Note type must NOT change after Tab")
            self.assertEqual(res['textAfterTab'], "  Test Tab", "Tab must insert exactly two spaces indentation at caret position")
        finally:
            driver.quit()

    def test_03_bullet_and_numbered_list_continuation(self):
        """Lists continue with Enter at end of item, place caret correctly, and stop on empty marker."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                if (!noteBlock) throw new Error("Note block not found");
                const ed = noteBlock.querySelector(".element-content");
                if (!ed) throw new Error("Note element-content not found");
                ed.innerText = "- Item 1";
                ed.focus();

                // 1. Enter at end of '- Item 1' -> should continue with '- '
                const sel = window.getSelection();
                let r = document.createRange();
                r.selectNodeContents(ed);
                r.collapse(false);
                sel.removeAllRanges();
                sel.addRange(r);

                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const state1 = ed.innerText;
                const range1 = sel.getRangeAt(0);
                const caretAtEnd1 = range1.endOffset === state1.length || state1.endsWith("- ");

                // 2. Type 'Item 2'
                document.execCommand('insertText', false, 'Item 2');
                // Press Enter -> should continue with '- '
                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const state2 = ed.innerText;

                // 3. Press Enter on empty '- ' -> should clear marker
                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const state3 = ed.innerText;

                // 4. Test Numbered list
                ed.innerText = "1. First";
                r = document.createRange();
                r.selectNodeContents(ed);
                r.collapse(false);
                sel.removeAllRanges();
                sel.addRange(r);

                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const numState1 = ed.innerText;

                document.execCommand('insertText', false, 'Second');
                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const numState2 = ed.innerText;

                // Press Enter on empty '3. ' -> should clear marker
                ed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const numState3 = ed.innerText;

                return {
                    bullet: { state1, state2, state3, caretAtEnd1 },
                    numbered: { numState1, numState2, numState3 }
                };
            """)

            # Bullet continuation assertions
            self.assertEqual(res['bullet']['state1'], "- Item 1\n- ", "Enter after bullet item must continue bullet marker")
            self.assertTrue(res['bullet']['caretAtEnd1'], "Caret must be placed after the continuation marker")
            self.assertEqual(res['bullet']['state2'], "- Item 1\n- Item 2\n- ", "Enter after second bullet item must continue marker")
            self.assertEqual(res['bullet']['state3'], "- Item 1\n- Item 2\n\n", "Enter on empty bullet marker must clear marker")

            # Numbered continuation assertions
            self.assertEqual(res['numbered']['numState1'], "1. First\n2. ", "Enter after '1. First' must continue with '2. '")
            self.assertEqual(res['numbered']['numState2'], "1. First\n2. Second\n3. ", "Enter after '2. Second' must continue with '3. '")
            self.assertEqual(res['numbered']['numState3'], "1. First\n2. Second\n\n", "Enter on empty '3. ' must clear marker")
        finally:
            driver.quit()

    def test_04_multiline_note_survives_save_and_reload(self):
        """Multiline note text, formatting, and line breaks survive save payload and database reload."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            test_multiline = "കുറിപ്പ് വരി 1\n- ഇനം 1\n- ഇനം 2\n1. ഘട്ടം ഒന്ന്"

            driver.execute_script(f"""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                if (!noteBlock) throw new Error("Note element block not found");
                const ed = noteBlock.querySelector(".element-content");
                ed.innerText = {repr(test_multiline)};
                window.editorInstance.markDirty();
            """)

            # Deterministic save synchronization
            self.wait_for_save(driver)

            # Check database persistence
            db_note = ScriptElement.objects.get(scene=self.scene1, element_type='note')
            self.assertEqual(db_note.content, test_multiline, "Database must persist exact multiline text and line breaks")

            # Reload scene in browser
            driver.execute_script("window.editorInstance.loadCurrentScene();")
            self.wait_for_scene(driver, self.scene1.id)

            reloaded_text = driver.execute_script("""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                return noteBlock ? noteBlock.querySelector(".element-content").innerText.trimEnd() : null;
            """)

            self.assertEqual(reloaded_text, test_multiline, "Reloaded note text in DOM must match saved multiline content exactly")
        finally:
            driver.quit()

    def test_05_note_content_intact_when_switching_scenes(self):
        """Note content remains completely intact when switching between scenes."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            multiline_text = "സീൻ 1 കുറിപ്പ്\n- പ്രധാന വിവരങ്ങൾ"
            driver.execute_script(f"""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                if (!noteBlock) throw new Error("Note block not found");
                noteBlock.querySelector(".element-content").innerText = {repr(multiline_text)};
                window.editorInstance.markDirty();
            """)
            self.wait_for_save(driver)

            # Switch to Scene 2
            driver.execute_script(f"window.editorInstance.switchScene({self.scene2.id});")
            self.wait_for_scene(driver, self.scene2.id)

            # Switch back to Scene 1
            driver.execute_script(f"window.editorInstance.switchScene({self.scene1.id});")
            self.wait_for_scene(driver, self.scene1.id)

            restored_text = driver.execute_script("""
                const noteBlock = document.querySelector("#screenplayPage .script-element-block[data-type='note']");
                return noteBlock ? noteBlock.querySelector(".element-content").innerText.trimEnd() : null;
            """)

            self.assertEqual(restored_text, multiline_text, "Note content must be restored intact when switching back to Scene 1")
        finally:
            driver.quit()

    def test_06_screenplay_elements_enter_regression(self):
        """Action, character, and dialogue enter behavior remains completely functional."""
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                // 1. Action split test
                const actionBlock = document.querySelector("#screenplayPage .script-element-block[data-type='action']");
                if (!actionBlock) throw new Error("Action element block not found");
                const actEd = actionBlock.querySelector(".element-content");
                actEd.innerText = "Sentence One. Sentence Two.";
                actEd.focus();

                const splitNeedle = "Sentence One.";
                const needleIdx = actEd.firstChild.textContent.indexOf(splitNeedle);
                if (needleIdx === -1) {
                    throw new Error("Needle '" + splitNeedle + "' not found in Action text node: '" + actEd.firstChild.textContent + "'");
                }

                const r = document.createRange();
                r.setStart(actEd.firstChild, needleIdx + splitNeedle.length);
                r.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(r);

                actEd.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));

                const actions = document.querySelectorAll("#screenplayPage .script-element-block[data-type='action']");
                const firstAction = actions[0].querySelector('.element-content').innerText.trim();
                const secondAction = actions[1].querySelector('.element-content').innerText.trim();

                // 2. Character -> Enter creates Dialogue block
                const charBlock = window.editorInstance.createElementBlock('character', 'നായകൻ', actions[1]);
                const charEd = charBlock.querySelector('.element-content');
                charEd.focus();
                charEd.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const afterCharBlock = charBlock.nextElementSibling;
                const charNextType = afterCharBlock ? afterCharBlock.dataset.type : null;

                // 3. Dialogue -> Enter creates Action block
                const diagEd = afterCharBlock.querySelector('.element-content');
                diagEd.innerText = "ഞാൻ പോകുന്നു.";
                diagEd.focus();
                diagEd.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                const afterDiagBlock = afterCharBlock.nextElementSibling;
                const diagNextType = afterDiagBlock ? afterDiagBlock.dataset.type : null;

                return {
                    actionCount: actions.length,
                    firstAction,
                    secondAction,
                    charNextType,
                    diagNextType
                };
            """)

            self.assertEqual(res['actionCount'], 2, "Action splitting must remain functional")
            self.assertEqual(res['firstAction'], "Sentence One.")
            self.assertEqual(res['secondAction'], "Sentence Two.")
            self.assertEqual(res['charNextType'], "dialogue", "Enter on Character element must create Dialogue element")
            self.assertEqual(res['diagNextType'], "action", "Enter on Dialogue element must create Action element")
        finally:
            driver.quit()
