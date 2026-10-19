import time
import os
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.models import Script, Scene, ScriptElement

CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"
User = get_user_model()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CopyPasteComprehensiveVerificationTests(StaticLiveServerTestCase):
    """
    Dedicated Task 4 verification suite for:
    1. Copy Full Scene and paste into a new scene.
    2. Character/dialogue structure.
    3. Action blocks and parentheticals.
    4. Scene headings and transitions.
    5. External HTML clipboard content resembling Google Docs or Word.
    6. Plain-text screenplay paste.
    7. Partial selection.
    8. Malayalam Unicode and mixed-language content.
    9. Unsafe HTML handling and XSS protection.
    10. Undo/redo after pasting.
    11. Save and reload after pasting.
    12. No unintended duplicate blocks.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,900")

        service = Service(executable_path=CHROMEDRIVER_PATH)
        cls.driver = webdriver.Chrome(service=service, options=opts)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.driver.quit()
        except Exception:
            pass
        super().tearDownClass()

    def setUp(self):
        self.username = f"cp_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")
        self.script = Script.objects.create(
            user=self.user,
            title="കോപ്പി പേസ്റ്റ് പരീക്ഷണം (Copy Paste Test)",
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
            content="സൂര്യപ്രകാശം മുറിയിലേക്ക് കടന്നുവരുന്നു.",
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="character",
            content="മോഹൻലാൽ",
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type="dialogue",
            content="നമസ്കാരം, സുഖമാണോ?",
            order=3
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
            content="",
            order=1
        )

        self.login_and_open_editor()

    def login_and_open_editor(self):
        d = self.driver
        d.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(d, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        d.find_element(By.NAME, "username").send_keys(self.username)
        d.find_element(By.NAME, "password").send_keys("password123")
        d.find_element(By.NAME, "password").submit()
        WebDriverWait(d, 10).until(EC.url_contains("/dashboard/"))

        d.get(f"{self.live_server_url}/scripts/{self.script.id}/editor/")
        WebDriverWait(d, 10).until(EC.presence_of_element_located((By.ID, "btnEnterEditMode")))

        WebDriverWait(d, 10).until(
            lambda drv: drv.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId.length > 0;
            """),
            message="Timed out waiting for initial scene to load into the canvas."
        )
        d.execute_script("window.editorInstance.setEditorMode('edit');")

    def test_01_copy_full_scene_and_paste_into_new_scene(self):
        """1. Copy Full Scene and paste into a new scene preserves all elements and heading structure."""
        res = self.driver.execute_script(f"""
            const inst = window.editorInstance;
            return (async () => {{
                // 1. Copy full scene 1
                await inst.copyFullScene({self.scene1.id});
                const payload = inst.lastCopiedPayload;

                // 2. Load scene 2 into canvas
                await inst.switchScene({self.scene2.id});

                // 3. Clear existing empty action in scene 2
                const page = inst.pageContainer;
                page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());

                // 4. Create an anchor block to paste into
                const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
                const anchor = inst.createElementBlock('action', '', heading);
                anchor.querySelector('.element-content').focus();
                inst.activeElementBlock = anchor;

                // 5. Simulate internal semantic paste
                const jsonStr = JSON.stringify(payload);
                const event = new Event('paste', {{ bubbles: true, cancelable: true }});
                event.clipboardData = {{
                    getData: function(format) {{
                        if (format === 'application/x-kadhascript-elements') return jsonStr;
                        return '';
                    }}
                }};
                inst.handlePaste(event);

                // 6. Return extracted canvas elements
                return inst.extractScenePayload();
            }})();
        """)
        self.assertIsNotNone(res)
        elements = res.get('elements', [])
        types = [e['element_type'] for e in elements]
        # Scene 1 elements: action, character, dialogue
        self.assertIn('action', types)
        self.assertIn('character', types)
        self.assertIn('dialogue', types)
        char_elem = next((e for e in elements if e['element_type'] == 'character'), None)
        self.assertEqual(char_elem['content'], 'മോഹൻലാൽ')
        dia_elem = next((e for e in elements if e['element_type'] == 'dialogue'), None)
        self.assertEqual(dia_elem['content'], 'നമസ്കാരം, സുഖമാണോ?')

    def test_02_character_dialogue_structure(self):
        """2. Character and dialogue structure correctly classified."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const text = 'ANTONY\\nWait for me at the harbour.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'ANTONY'), None)
        self.assertIsNotNone(char)
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'harbour' in e['content']), None)
        self.assertIsNotNone(dia)

    def test_03_action_blocks_and_parentheticals(self):
        """3. Action blocks and parentheticals are parsed with correct types."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const text = 'A gust of wind shakes the window.\\n\\nPRIYA\\n(whispering)\\nDid you hear that?';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('action', types)
        self.assertIn('parenthetical', types)
        self.assertIn('dialogue', types)
        paren = next((e for e in elems if e['element_type'] == 'parenthetical'), None)
        self.assertEqual(paren['content'], '(whispering)')

    def test_04_scene_headings_and_transitions(self):
        """4. Scene headings and transitions recognized cleanly."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const text = 'INT. METRO STATION - NIGHT\\nFootsteps echo in the hallway.\\n\\nFADE OUT.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('scene_heading', types)
        self.assertIn('action', types)
        self.assertIn('transition', types)

    def test_05_external_html_clipboard_resembling_google_docs_or_word(self):
        """5. External HTML from Word/Docs is stripped of styling and converted to screenplay blocks."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            // Simulated HTML from Google Docs / Microsoft Word with inline styles and span wrappers
            const htmlContent = `
                <meta charset="utf-8">
                <p class="MsoNormal" style="margin-bottom:0cm;line-height:normal">
                    <span style="font-family:'Courier Prime';font-weight:bold">GEORGE</span>
                </p>
                <p class="MsoNormal" style="margin-bottom:0cm;line-height:normal">
                    <span style="font-family:'Courier Prime'">(nervously)</span>
                </p>
                <p class="MsoNormal" style="margin-bottom:0cm;line-height:normal">
                    <span style="font-family:'Courier Prime'">The police are outside.</span>
                </p>
            `;
            const plainText = 'GEORGE\\n(nervously)\\nThe police are outside.';

            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/html') return htmlContent;
                    if (format === 'text/plain') return plainText;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('character', types)
        self.assertIn('parenthetical', types)
        self.assertIn('dialogue', types)
        # Ensure no raw span, style, or class leaked into content
        for e in elems:
            self.assertNotIn('<span', e['content'])
            self.assertNotIn('MsoNormal', e['content'])
            self.assertNotIn('style=', e['content'])

    def test_06_plain_text_screenplay_paste(self):
        """6. Plain-text screenplay paste accurately classified."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const plain = 'EXT. FOREST - DUSK\\n\\nA deer pauses near the stream.\\n\\nHUNTER\\nStay quiet.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return plain;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('scene_heading', types)
        self.assertIn('action', types)
        self.assertIn('character', types)
        self.assertIn('dialogue', types)

    def test_07_partial_selection_copy_paste(self):
        """7. Partial selection clipboard retains selected blocks without whole-scene duplication."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            // Create partial selection payload containing only 2 elements
            const partialPayload = {
                version: "1.0",
                source: "kadhascript",
                is_full_scene: false,
                elements: [
                    { type: 'character', content: 'DIRECTOR' },
                    { type: 'dialogue', content: 'Roll camera!' }
                ]
            };
            const jsonStr = JSON.stringify(partialPayload);
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'application/x-kadhascript-elements') return jsonStr;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """)
        elems = payload.get('elements', [])
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'DIRECTOR'), None)
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and e['content'] == 'Roll camera!'), None)
        self.assertIsNotNone(char)
        self.assertIsNotNone(dia)

    def test_08_malayalam_unicode_and_mixed_language_content(self):
        """8. Malayalam Unicode, complex ligatures, chillu, and mixed English/Malayalam preserved."""
        malayalam_text = "രാമൻ\n(വിസ്മയത്തോടെ)\nഅത്ഭുതം തന്നെ! Is this really happening?\n\nഅവർ ഒന്നിച്ചു നടന്നു."
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            inst.characters = ['രാമൻ'];
            const text = arguments[0];
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """, malayalam_text)
        elems = payload.get('elements', [])
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'രാമൻ'), None)
        self.assertIsNotNone(char)
        self.assertEqual(char['content'], 'രാമൻ')
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'Is this really happening?' in e['content']), None)
        self.assertIsNotNone(dia)
        self.assertEqual(dia['content'], 'അത്ഭുതം തന്നെ! Is this really happening?')
        act = next((e for e in elems if e['element_type'] == 'action' and 'നടന്നു' in e['content']), None)
        self.assertIsNotNone(act)

    def test_09_unsafe_html_handling_and_xss_protection(self):
        """9. Unsafe HTML, scripts, and event handlers are neutralized during paste."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            window._xssTriggered = false;
            const unsafeHtml = `
                <script>window._xssTriggered = true;</script>
                <img src="invalid-img.jpg" onerror="window._xssTriggered = true;">
                <b onclick="window._xssTriggered = true;">SURESH</b>
                <p>Dangerous dialogue</p>
            `;
            const plainText = 'SURESH\\nDangerous dialogue';

            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/html') return unsafeHtml;
                    if (format === 'text/plain') return plainText;
                    return '';
                }
            };
            inst.handlePaste(event);
            return {
                xss: window._xssTriggered,
                payload: inst.extractScenePayload()
            };
        """)
        self.assertFalse(payload['xss'], "XSS script or onerror must never execute during paste!")
        elems = payload['payload'].get('elements', [])
        for e in elems:
            self.assertNotIn('<script>', e['content'])
            self.assertNotIn('onerror', e['content'])

    def test_10_undo_redo_after_pasting(self):
        """10. Undo restores pre-paste canvas state and redo re-applies pasted blocks."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            // Record pre-paste count
            const beforeCount = inst.pageContainer.querySelectorAll('.script-element-block').length;

            // Paste new block
            const text = 'VIPIN\\nHello world.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            const afterPasteCount = inst.pageContainer.querySelectorAll('.script-element-block').length;

            // Undo
            if (typeof inst.undo === 'function') {
                inst.undo();
            }
            const afterUndoCount = inst.pageContainer.querySelectorAll('.script-element-block').length;

            // Redo
            if (typeof inst.redo === 'function') {
                inst.redo();
            }
            const afterRedoCount = inst.pageContainer.querySelectorAll('.script-element-block').length;

            return {
                before: beforeCount,
                afterPaste: afterPasteCount,
                afterUndo: afterUndoCount,
                afterRedo: afterRedoCount
            };
        """)
        self.assertGreater(res['afterPaste'], res['before'])
        self.assertEqual(res['afterUndo'], res['before'])
        self.assertEqual(res['afterRedo'], res['afterPaste'])

    def test_11_save_and_reload_after_pasting(self):
        """11. Save and reload after pasting accurately persists and restores elements from database."""
        # Paste elements
        self.driver.execute_script("""
            const inst = window.editorInstance;
            const text = 'VARUN\\nThis text will be saved and reloaded.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);
            // Save current scene
            inst.saveCurrentScene();
        """)
        time.sleep(1.0)

        # Reload page
        self.driver.get(f"{self.live_server_url}/scripts/{self.script.id}/editor/")
        WebDriverWait(self.driver, 10).until(
            lambda drv: drv.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId;
            """)
        )

        persisted_payload = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        elems = persisted_payload.get('elements', [])
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'VARUN'), None)
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'saved and reloaded' in e['content']), None)
        self.assertIsNotNone(char, "Character VARUN must persist after reload")
        self.assertIsNotNone(dia, "Dialogue must persist after reload")

    def test_12_no_unintended_duplicate_blocks(self):
        """12. A single paste does not create unintended duplicate blocks."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const initialCount = inst.pageContainer.querySelectorAll('.script-element-block').length;

            // Single paste with two elements (Character + Dialogue)
            const text = 'ACTOR\\nSingle dialogue line.';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            inst.handlePaste(event);

            const finalCount = inst.pageContainer.querySelectorAll('.script-element-block').length;
            const actorBlocks = Array.from(inst.pageContainer.querySelectorAll('.script-element-block[data-type="character"]'))
                .filter(b => b.querySelector('.element-content').innerText.trim() === 'ACTOR');

            return {
                diff: finalCount - initialCount,
                actorCount: actorBlocks.length
            };
        """)
        # Exactly 1 character block named ACTOR should exist, not duplicates
        self.assertEqual(res['actorCount'], 1, f"Expected exactly 1 ACTOR block, found {res['actorCount']}")
