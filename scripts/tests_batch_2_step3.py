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
class ClipboardPartialCopyPasteLiveTests(StaticLiveServerTestCase):
    """
    Automated browser tests for Batch 2, Issue E: Partial Text Selection and Copy/Paste Behavior.
    Verifies:
    1. Copy substring from Action, Dialogue, Character, and multiline Note blocks.
    2. Exact line-separated text when copying partial text spanning across multiple blocks.
    3. Partial copy does NOT generate structured screenplay payloads (lastCopiedPayload is null).
    4. Inline paste at caret inside an element inserts plain text without creating extra blocks.
    5. Paste over selected substring replaces selected text inline without creating extra blocks.
    6. Complete block copy produces structured screenplay payload (application/x-kadhascript-elements).
    7. Pasting complete blocks creates elements of correct types, exact content, order, and placement.
    8. Read-only mode copies exact plain text without metadata, and rejects edits/pastes.
    9. copyFullScene() and the Canvas-to-Save-Target Integrity Guard remain intact.

    Note: Synthetic ClipboardEvent and KeyboardEvent dispatches verify application event interception,
    DOM selection parsing, and serialization logic; native OS clipboard synchronization is handled
    by the host environment.
    """

    def setUp(self):
        User = get_user_model()
        self.username = f"clipboard_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")

        self.script = Script.objects.create(
            user=self.user,
            title="ക്ലിപ്പ്ബോർഡ് പരിശോധന (Clipboard Test)",
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
            content="നായകൻ മുറിയിലേക്ക് കയറി ചുറ്റും നോക്കുന്നു.",
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="character",
            content="രാഹുൽ",
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="dialogue",
            content="ഞാൻ നാളെ തിരിച്ചുവരും, തീർച്ച!",
            order=3
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="note",
            content="- കുറിപ്പ് 1\n- കുറിപ്പ് 2\n- കുറിപ്പ് 3",
            order=4
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
        opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})

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

        # Wait until editor finishes initial async load
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

    def test_partial_copy_single_blocks_action_dialogue_character_note(self):
        """
        Verify copying a substring from Action, Dialogue, Character, and multiline Note:
        - Copies exact text.
        - Does NOT attach application/x-kadhascript-elements or structured data.
        - Sets lastCopiedPayload to null.
        - Preserves Malayalam Unicode and punctuation.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # 1. Action block partial copy
            res_action = driver.execute_script("""
                const actEd = document.querySelector('.script-element-block[data-type="action"] .element-content');
                if (!actEd || !actEd.firstChild) throw new Error("Action block text node not found");
                const text = actEd.firstChild.textContent;
                const startSub = 'മുറിയിലേക്ക്';
                const startIdx = text.indexOf(startSub);
                if (startIdx === -1) {
                    throw new Error("Substring '" + startSub + "' not found in action text: '" + text + "'");
                }
                const selectText = 'മുറിയിലേക്ക് കയറി';
                const endIdx = startIdx + selectText.length;

                const range = document.createRange();
                range.setStart(actEd.firstChild, startIdx);
                range.setEnd(actEd.firstChild, endIdx);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertEqual(res_action['plainText'], 'മുറിയിലേക്ക് കയറി')
            self.assertFalse(res_action['hasCustom'])
            self.assertIsNone(res_action['lastPayload'])

            # 2. Dialogue block partial copy (with punctuation)
            res_diag = driver.execute_script("""
                const diagEd = document.querySelector('.script-element-block[data-type="dialogue"] .element-content');
                if (!diagEd || !diagEd.firstChild) throw new Error("Dialogue block text node not found");
                const text = diagEd.firstChild.textContent;
                const startSub = 'തിരിച്ചുവരും';
                const startIdx = text.indexOf(startSub);
                if (startIdx === -1) {
                    throw new Error("Substring '" + startSub + "' not found in dialogue text: '" + text + "'");
                }
                const endIdx = text.indexOf('!');
                if (endIdx === -1) {
                    throw new Error("Punctuation '!' not found in dialogue text: '" + text + "'");
                }

                const range = document.createRange();
                range.setStart(diagEd.firstChild, startIdx);
                range.setEnd(diagEd.firstChild, endIdx + 1);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertEqual(res_diag['plainText'], 'തിരിച്ചുവരും, തീർച്ച!')
            self.assertFalse(res_diag['hasCustom'])
            self.assertIsNone(res_diag['lastPayload'])

            # 3. Character block partial copy
            res_char = driver.execute_script("""
                const charEd = document.querySelector('.script-element-block[data-type="character"] .element-content');
                if (!charEd || !charEd.firstChild) throw new Error("Character block text node not found");
                if (charEd.firstChild.textContent.length < 2) {
                    throw new Error("Character text node has fewer than 2 characters: '" + charEd.firstChild.textContent + "'");
                }

                // Text: 'രാഹുൽ' -> select first 2 chars ('രാ')
                const range = document.createRange();
                range.setStart(charEd.firstChild, 0);
                range.setEnd(charEd.firstChild, 2);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertEqual(res_char['plainText'], 'രാ')
            self.assertFalse(res_char['hasCustom'])
            self.assertIsNone(res_char['lastPayload'])

            # 4. Multiline Note partial copy
            res_note = driver.execute_script("""
                const noteEd = document.querySelector('.script-element-block[data-type="note"] .element-content');
                if (!noteEd) throw new Error("Note element-content not found");
                let targetNode = null;
                let targetOffset = 0;
                const walker = document.createTreeWalker(noteEd, NodeFilter.SHOW_TEXT);
                while (walker.nextNode()) {
                    const idx = walker.currentNode.textContent.indexOf('കുറിപ്പ് 2');
                    if (idx !== -1) {
                        targetNode = walker.currentNode;
                        targetOffset = idx;
                        break;
                    }
                }

                if (!targetNode) {
                    throw new Error("Target substring 'കുറിപ്പ് 2' not found in note text nodes");
                }

                const range = document.createRange();
                range.setStart(targetNode, targetOffset);
                range.setEnd(targetNode, targetOffset + 'കുറിപ്പ് 2'.length);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertEqual(res_note['plainText'], 'കുറിപ്പ് 2')
            self.assertFalse(res_note['hasCustom'])
            self.assertIsNone(res_note['lastPayload'])

        finally:
            driver.quit()

    def test_partial_copy_spanning_multiple_blocks(self):
        """
        Verify partial selection spanning from Action to Dialogue:
        - Copies exact text inside selection from each block, joined by newline.
        - Does NOT copy full unselected prefixes or suffixes.
        - Does NOT attach structured screenplay metadata.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const actEd = document.querySelector('.script-element-block[data-type="action"] .element-content');
                const diagEd = document.querySelector('.script-element-block[data-type="dialogue"] .element-content');
                if (!actEd || !actEd.firstChild) throw new Error("Action block text node not found");
                if (!diagEd || !diagEd.firstChild) throw new Error("Dialogue block text node not found");

                // From 'ചുറ്റും' in Action through 'ഞാൻ നാളെ' in Dialogue
                const actText = actEd.firstChild.textContent;
                const startIdx = actText.indexOf('ചുറ്റും');
                if (startIdx === -1) {
                    throw new Error("Substring 'ചുറ്റും' not found in Action text: '" + actText + "'");
                }

                const diagText = diagEd.firstChild.textContent;
                const endIdx = diagText.indexOf('തിരിച്ചുവരും');
                if (endIdx === -1) {
                    throw new Error("Substring 'തിരിച്ചുവരും' not found in Dialogue text: '" + diagText + "'");
                }

                const range = document.createRange();
                range.setStart(actEd.firstChild, startIdx);
                range.setEnd(diagEd.firstChild, endIdx);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            # Verify exact line-separated contents across the multi-block selection
            expected_text = "ചുറ്റും നോക്കുന്നു.\nരാഹുൽ\nഞാൻ നാളെ "
            self.assertEqual(res['plainText'], expected_text, "Multi-block partial copy must join extracted text with exact newlines")
            self.assertNotIn('നായകൻ മുറിയിലേക്ക് കയറി', res['plainText'], "Unselected prefix of Action must be excluded")
            self.assertNotIn('തീർച്ച!', res['plainText'], "Unselected suffix of Dialogue must be excluded")
            self.assertFalse(res['hasCustom'], "Partial multi-block copy must not attach structured metadata")
            self.assertIsNone(res['lastPayload'], "Partial multi-block copy must set lastCopiedPayload to null")

        finally:
            driver.quit()

    def test_partial_paste_inline_middle_and_replace_selection(self):
        """
        Verify pasting partial text inline into an existing Action and Dialogue block:
        1. Caret in middle: inserts inline without creating new blocks, marks dirty.
        2. Text selected: replaces selected text inline without creating new blocks.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # Test 1: Paste inline in middle of Action block
            res_middle = driver.execute_script("""
                const actEd = document.querySelector('.script-element-block[data-type="action"] .element-content');
                if (!actEd || !actEd.firstChild) throw new Error("Action text node not found");
                actEd.focus();

                // Position caret after 'കയറി '
                const text = actEd.firstChild.textContent;
                const matchStr = 'കയറി ';
                const matchIdx = text.indexOf(matchStr);
                if (matchIdx === -1) {
                    throw new Error("Substring '" + matchStr + "' not found in action text: '" + text + "'");
                }
                const caretPos = matchIdx + matchStr.length;

                const range = document.createRange();
                range.setStart(actEd.firstChild, caretPos);
                range.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const countBefore = document.querySelectorAll('.script-element-block').length;

                // Paste partial text
                const dt = new DataTransfer();
                dt.setData('text/plain', 'വേഗത്തിൽ ');
                const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(pasteEvt);

                return {
                    countBefore: countBefore,
                    countAfter: document.querySelectorAll('.script-element-block').length,
                    updatedText: actEd.innerText,
                    isDirty: window.editorInstance.isDirty
                };
            """)

            self.assertEqual(res_middle['countBefore'], res_middle['countAfter'], "Inline paste must not add new blocks")
            self.assertEqual(res_middle['updatedText'], 'നായകൻ മുറിയിലേക്ക് കയറി വേഗത്തിൽ ചുറ്റും നോക്കുന്നു.', "Inline paste must insert text exactly at caret position")
            self.assertTrue(res_middle['isDirty'], "Editor must be marked dirty after inline paste")

            # Test 2: Paste replacing selected substring in Dialogue block
            res_replace = driver.execute_script("""
                const diagEd = document.querySelector('.script-element-block[data-type="dialogue"] .element-content');
                if (!diagEd || !diagEd.firstChild) throw new Error("Dialogue text node not found");
                diagEd.focus();

                // Select 'തീർച്ച!'
                const text = diagEd.firstChild.textContent;
                const matchStr = 'തീർച്ച!';
                const startIdx = text.indexOf(matchStr);
                if (startIdx === -1) {
                    throw new Error("Substring '" + matchStr + "' not found in dialogue text: '" + text + "'");
                }
                const endIdx = startIdx + matchStr.length;

                const range = document.createRange();
                range.setStart(diagEd.firstChild, startIdx);
                range.setEnd(diagEd.firstChild, endIdx);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const countBefore = document.querySelectorAll('.script-element-block').length;

                const dt = new DataTransfer();
                dt.setData('text/plain', 'സത്യം!');
                const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(pasteEvt);

                return {
                    countBefore: countBefore,
                    countAfter: document.querySelectorAll('.script-element-block').length,
                    updatedText: diagEd.innerText,
                    blockType: diagEd.closest('.script-element-block').dataset.type
                };
            """)

            self.assertEqual(res_replace['countBefore'], res_replace['countAfter'], "Selection replacement paste must not create extra blocks")
            self.assertEqual(res_replace['updatedText'], 'ഞാൻ നാളെ തിരിച്ചുവരും, സത്യം!', "Selected text must be replaced with pasted text exactly")
            self.assertEqual(res_replace['blockType'], 'dialogue', "Element type must remain dialogue")

        finally:
            driver.quit()

    def test_complete_blocks_copy_paste_preservation(self):
        """
        Verify that selecting COMPLETE blocks (from start of first block to end of last block):
        - Produces structured screenplay clipboard payload (application/x-kadhascript-elements).
        - Sets lastCopiedPayload.
        - Pasting structured data creates proper screenplay blocks with exact types, content, order, and placement.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            res = driver.execute_script("""
                const charEd = document.querySelector('.script-element-block[data-type="character"] .element-content');
                const diagEd = document.querySelector('.script-element-block[data-type="dialogue"] .element-content');
                if (!charEd || !charEd.firstChild) throw new Error("Character block text node not found");
                if (!diagEd || !diagEd.firstChild) throw new Error("Dialogue block text node not found");

                // Select complete Character and complete Dialogue blocks
                const range = document.createRange();
                range.setStart(charEd.firstChild, 0);
                range.setEnd(diagEd.firstChild, diagEd.firstChild.textContent.length);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                const hasCustom = dt.types.includes('application/x-kadhascript-elements');
                const rawCustom = dt.getData('application/x-kadhascript-elements');
                let parsed = null;
                try { parsed = JSON.parse(rawCustom); } catch(e){}

                return {
                    hasCustom: hasCustom,
                    elementTypes: parsed ? parsed.elements.map(e => e.type) : [],
                    elementContents: parsed ? parsed.elements.map(e => e.content) : [],
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertTrue(res['hasCustom'], "Complete block copy must attach custom MIME type")
            self.assertEqual(res['elementTypes'], ['character', 'dialogue'], "Structured elements must preserve character and dialogue types")
            self.assertEqual(res['elementContents'], ['രാഹുൽ', 'ഞാൻ നാളെ തിരിച്ചുവരും, തീർച്ച!'], "Structured elements must preserve exact text content")
            self.assertIsNotNone(res['lastPayload'], "lastCopiedPayload must be set on complete block copy")

            # Paste the structured payload immediately after Action block
            paste_res = driver.execute_script("""
                const blocksBefore = document.querySelectorAll('.script-element-block').length;
                const actBlock = document.querySelector('.script-element-block[data-type="action"]');
                if (!actBlock) throw new Error("Action block not found");
                window.editorInstance.activeElementBlock = actBlock;

                // Paste using structured clipboard payload
                const dt = new DataTransfer();
                dt.setData('application/x-kadhascript-elements', JSON.stringify(window.editorInstance.lastCopiedPayload));
                const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(pasteEvt);

                const allBlocks = Array.from(document.querySelectorAll('.script-element-block'));
                const actIndex = allBlocks.indexOf(actBlock);
                const inserted1 = allBlocks[actIndex + 1];
                const inserted2 = allBlocks[actIndex + 2];

                return {
                    blocksBefore: blocksBefore,
                    blocksAfter: allBlocks.length,
                    inserted1Type: inserted1 ? inserted1.dataset.type : null,
                    inserted1Content: inserted1 ? inserted1.querySelector('.element-content').innerText.trim() : null,
                    inserted2Type: inserted2 ? inserted2.dataset.type : null,
                    inserted2Content: inserted2 ? inserted2.querySelector('.element-content').innerText.trim() : null
                };
            """)

            self.assertEqual(paste_res['blocksAfter'], paste_res['blocksBefore'] + 2, "Structured paste must insert exactly 2 blocks")
            self.assertEqual(paste_res['inserted1Type'], 'character', "First inserted block must be character")
            self.assertEqual(paste_res['inserted1Content'], 'രാഹുൽ', "First inserted block content must be 'രാഹുൽ'")
            self.assertEqual(paste_res['inserted2Type'], 'dialogue', "Second inserted block must be dialogue")
            self.assertEqual(paste_res['inserted2Content'], 'ഞാൻ നാളെ തിരിച്ചുവരും, തീർച്ച!', "Second inserted block content must match copied dialogue")

        finally:
            driver.quit()

    def test_readonly_partial_copy_and_edit_rejection(self):
        """
        Verify that in Read Mode:
        - Partial text selection copies exact text as plain text without structured metadata.
        - Pasting into read mode is rejected without altering DOM.
        - Typing/keydown events into read mode are rejected without altering DOM or creating blocks.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # Switch to Read Mode
            driver.execute_script("window.editorInstance.setEditorMode('read');")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("""
                    const rc = document.getElementById('readModeContainer');
                    return window.editorInstance.editorMode === 'read' &&
                           rc &&
                           getComputedStyle(rc).display !== 'none';
                """),
                message="Timed out waiting for transition to read mode."
            )

            # 1. Partial copy in read mode
            res_copy = driver.execute_script("""
                const readAction = document.querySelector('#readModeContainer .read-element-block.element-type-action .element-content');
                if (!readAction || !readAction.firstChild) throw new Error("Read action element text node not found");
                const text = readAction.firstChild.textContent;
                const matchStr = 'മുറിയിലേക്ക്';
                const startIdx = text.indexOf(matchStr);
                if (startIdx === -1) {
                    throw new Error("Substring '" + matchStr + "' not found in read action text: '" + text + "'");
                }
                const endIdx = startIdx + 'മുറിയിലേക്ക് കയറി'.length;

                const range = document.createRange();
                range.setStart(readAction.firstChild, startIdx);
                range.setEnd(readAction.firstChild, endIdx);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            self.assertEqual(res_copy['plainText'], 'മുറിയിലേക്ക് കയറി', "Read mode partial copy must extract exact text")
            self.assertFalse(res_copy['hasCustom'], "Read mode partial copy must not attach custom MIME type")
            self.assertIsNone(res_copy['lastPayload'], "Read mode partial copy must set lastCopiedPayload to null")

            # 2. Paste rejection in read mode
            res_rejection = driver.execute_script("""
                const rc = document.getElementById('readModeContainer');
                const readItemsBefore = rc.querySelectorAll('.read-scene-heading, .read-element-block').length;
                const textBefore = rc.innerText;

                // Dispatch paste event targeting read mode element
                const readAction = document.querySelector('#readModeContainer .read-element-block.element-type-action');
                const dt = new DataTransfer();
                dt.setData('text/plain', 'MODIFICATION_ATTEMPT');
                const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                readAction.dispatchEvent(pasteEvt);

                // Dispatch Enter keydown event targeting read mode element
                const keyEvt = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                readAction.dispatchEvent(keyEvt);

                const readItemsAfter = rc.querySelectorAll('.read-scene-heading, .read-element-block').length;
                const textAfter = rc.innerText;

                return {
                    readItemsBefore: readItemsBefore,
                    readItemsAfter: readItemsAfter,
                    containsInjectedText: textAfter.includes('MODIFICATION_ATTEMPT'),
                    isDirty: window.editorInstance.isDirty
                };
            """)

            self.assertEqual(res_rejection['readItemsBefore'], res_rejection['readItemsAfter'], "Read mode elements count must not change on paste or Enter")
            self.assertFalse(res_rejection['containsInjectedText'], "Read mode text must not accept pasted text")
            self.assertFalse(res_rejection['isDirty'], "Editor must remain clean after attempted edit in read mode")

        finally:
            driver.quit()

    def test_partial_copy_with_unselected_trailing_whitespace_regression(self):
        """
        Regression test for Issue E / isBlockFullySelected:
        Verify that selecting visible text while leaving trailing whitespace outside the selection:
        - Is correctly treated as a partial text selection (hasBefore=false, hasAfter=true).
        - Produces plain text on the clipboard without structured payload (hasCustom=false, lastPayload=null).
        - Pasting into another block inserts the text inline at the caret without creating a new block.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            # Step 1: Set up Action block with visible text followed by trailing spaces, and copy only visible text
            copy_res = driver.execute_script("""
                const actBlock = document.querySelector('.script-element-block[data-type="action"]');
                if (!actBlock) throw new Error("Action element block not found");
                const actEd = actBlock.querySelector('.element-content');
                if (!actEd) throw new Error("Action element-content not found");

                const visibleText = "റഹീം അകത്തേക്ക് വന്നു.";
                const trailingSpaces = "    ";
                actEd.innerText = visibleText + trailingSpaces;

                if (!actEd.firstChild) throw new Error("Text node not created in Action block");
                const fullText = actEd.firstChild.textContent;
                const startIdx = fullText.indexOf(visibleText);
                if (startIdx === -1) {
                    throw new Error("Target visible text '" + visibleText + "' not found in: '" + fullText + "'");
                }
                const endIdx = startIdx + visibleText.length;

                // Select ONLY the visible text, leaving the 4 trailing spaces outside the selection
                const range = document.createRange();
                range.setStart(actEd.firstChild, startIdx);
                range.setEnd(actEd.firstChild, endIdx);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const dt = new DataTransfer();
                const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(copyEvt);

                return {
                    plainText: dt.getData('text/plain'),
                    hasCustom: dt.types.includes('application/x-kadhascript-elements'),
                    lastPayload: window.editorInstance.lastCopiedPayload
                };
            """)

            copied_text = copy_res['plainText']
            self.assertFalse(copy_res['hasCustom'], "Partial copy leaving trailing whitespace must not attach custom MIME type")
            self.assertIsNone(copy_res['lastPayload'], "lastCopiedPayload must remain null for partial selection")
            self.assertEqual(copied_text, "റഹീം അകത്തേക്ക് വന്നു.", "Plain text must contain exactly the selected visible text")

            # Step 2: Place caret inside Dialogue block and paste the actual copied text
            paste_res = driver.execute_script("""
                const textToPaste = arguments[0];
                const diagBlock = document.querySelector('.script-element-block[data-type="dialogue"]');
                if (!diagBlock) throw new Error("Dialogue block not found");
                const diagEd = diagBlock.querySelector('.element-content');
                if (!diagEd || !diagEd.firstChild) throw new Error("Dialogue text node not found");
                diagEd.focus();

                const targetWord = "തീർച്ച!";
                const diagText = diagEd.firstChild.textContent;
                const targetIdx = diagText.indexOf(targetWord);
                if (targetIdx === -1) {
                    throw new Error("Target word '" + targetWord + "' not found in dialogue text: '" + diagText + "'");
                }

                // Place caret immediately before 'തീർച്ച!'
                const range = document.createRange();
                range.setStart(diagEd.firstChild, targetIdx);
                range.collapse(true);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);

                const countBefore = document.querySelectorAll('.script-element-block').length;

                // Paste the actual copied plain text
                const dt = new DataTransfer();
                dt.setData('text/plain', textToPaste);
                const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                document.dispatchEvent(pasteEvt);

                const countAfter = document.querySelectorAll('.script-element-block').length;
                return {
                    countBefore: countBefore,
                    countAfter: countAfter,
                    updatedText: diagEd.innerText,
                    dialogueType: diagBlock.dataset.type
                };
            """, copied_text)

            self.assertEqual(paste_res['countBefore'], paste_res['countAfter'], "Pasting partial text must NOT create a new screenplay block")
            self.assertIn(copied_text, paste_res['updatedText'], "Pasted text must be inserted inline at caret")
            self.assertIn("തീർച്ച!", paste_res['updatedText'], "Original dialogue text after caret must be preserved")
            self.assertEqual(paste_res['dialogueType'], 'dialogue', "Target block must remain dialogue")

        finally:
            driver.quit()

    def test_copy_full_scene_and_safeguards_regression(self):
        """
        Verify that copyFullScene() and scene-save integrity guard remain fully intact.
        """
        driver = self.get_driver()
        try:
            self.login_and_open_editor(driver)

            full_scene = driver.execute_script("""
                return typeof window.editorInstance.copyFullScene === 'function';
            """)
            self.assertTrue(full_scene, "copyFullScene method must be preserved!")

            # Verify integrity guard exists
            save_guard = driver.execute_script("""
                return window.editorInstance.saveCurrentScene.toString().includes('Canvas-to-Save-Target Integrity Guard');
            """)
            self.assertTrue(save_guard, "Canvas-to-Save-Target Integrity Guard must be preserved!")

        finally:
            driver.quit()
