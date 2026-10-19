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

    def test_13_character_with_long_dialogue_over_40_chars(self):
        """13. Regression: Character followed by dialogue over 40 chars is not misclassified as Action."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const text = 'RAHUL\\nWe need to secure the northern gate before the monsoon flood reaches the courtyard.';
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
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'RAHUL'), None)
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'northern gate' in e['content']), None)
        self.assertIsNotNone(char, "RAHUL must be classified as character, not action")
        self.assertIsNotNone(dia, "Dialogue >40 chars must be classified as dialogue, not action")
        self.assertEqual(char['content'], 'RAHUL')
        self.assertEqual(dia['content'], 'We need to secure the northern gate before the monsoon flood reaches the courtyard.')

    def test_14_multiple_character_dialogue_exchanges_with_no_blank_lines(self):
        """14. Multiple character/dialogue exchanges with long dialogue and no blank lines are parsed correctly."""
        raw_text = (
            "JOHN\n"
            "I have been waiting here for over two hours and nobody has arrived yet.\n"
            "MARY\n"
            "The train was delayed at the central terminal because of heavy rain.\n"
            "JOHN\n"
            "We must leave before the security guards lock the main entrance gate."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', heading);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

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
        """, raw_text)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        expected_types = ['character', 'dialogue', 'character', 'dialogue', 'character', 'dialogue']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'JOHN')
        self.assertEqual(elems[1]['content'], 'I have been waiting here for over two hours and nobody has arrived yet.')
        self.assertEqual(elems[2]['content'], 'MARY')
        self.assertEqual(elems[3]['content'], 'The train was delayed at the central terminal because of heavy rain.')
        self.assertEqual(elems[4]['content'], 'JOHN')
        self.assertEqual(elems[5]['content'], 'We must leave before the security guards lock the main entrance gate.')

    def test_15_parentheticals_before_and_within_dialogue_and_action(self):
        """15. Parentheticals at start of paste, within dialogue, and around action are preserved."""
        raw_text = (
            "The heavy wooden door swings slowly open.\n\n"
            "PETER\n"
            "(turning to face the window)\n"
            "I knew you would come back before midnight.\n"
            "(softly)\n"
            "Even when everyone else doubted your innocence.\n\n"
            "A loud thunderclap rattles the entire room."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', heading);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

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
        """, raw_text)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        expected_types = ['action', 'character', 'parenthetical', 'dialogue', 'parenthetical', 'dialogue', 'action']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'The heavy wooden door swings slowly open.')
        self.assertEqual(elems[1]['content'], 'PETER')
        self.assertEqual(elems[2]['content'], '(turning to face the window)')
        self.assertEqual(elems[3]['content'], 'I knew you would come back before midnight.')
        self.assertEqual(elems[4]['content'], '(softly)')
        self.assertEqual(elems[5]['content'], 'Even when everyone else doubted your innocence.')
        self.assertEqual(elems[6]['content'], 'A loud thunderclap rattles the entire room.')

    def test_16_uppercase_action_lines_resembling_characters(self):
        """16. Uppercase action phrases (e.g. HE TURNS, SUDDENLY) are not misclassified as characters."""
        raw_text = (
            "HE TURNS\n\n"
            "DAVID\n"
            "Did you hear the footsteps in the corridor?\n\n"
            "SUDDENLY\n\n"
            "The hallway lights flicker and extinguish completely."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', heading);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

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
        """, raw_text)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        expected_types = ['action', 'character', 'dialogue', 'action', 'action']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'HE TURNS')
        self.assertEqual(elems[1]['content'], 'DAVID')
        self.assertEqual(elems[2]['content'], 'Did you hear the footsteps in the corridor?')
        self.assertEqual(elems[3]['content'], 'SUDDENLY')
        self.assertEqual(elems[4]['content'], 'The hallway lights flicker and extinguish completely.')

    def test_17_google_docs_mobile_html_payload_with_nbsp_and_crlf(self):
        """17. Google Docs mobile HTML payload with &nbsp;, spans, and CRLF is cleanly parsed."""
        docs_html = (
            '<meta charset="utf-8">'
            '<p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">'
            '<span style="font-size:12pt;font-family:Courier New;color:#000000;background-color:transparent;font-weight:700;">'
            'SARAH</span></p>'
            '<p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">'
            '<span style="font-size:12pt;font-family:Courier New;color:#000000;background-color:transparent;font-style:italic;">'
            '(whispering)&nbsp;</span></p>'
            '<p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">'
            '<span style="font-size:12pt;font-family:Courier New;color:#000000;background-color:transparent;">'
            'Do&nbsp;not&nbsp;make&nbsp;a&nbsp;sound&nbsp;until&nbsp;the&nbsp;guards&nbsp;leave&nbsp;the&nbsp;area.</span></p>'
        )
        plain_text = "SARAH\r\n(whispering)\u00A0\r\nDo\u00A0not\u00A0make\u00A0a\u00A0sound\u00A0until\u00A0the\u00A0guards\u00A0leave\u00A0the\u00A0area."

        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const htmlContent = arguments[0];
            const plainText = arguments[1];
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
        """, docs_html, plain_text)
        elems = payload.get('elements', [])
        char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'SARAH'), None)
        paren = next((e for e in elems if e['element_type'] == 'parenthetical' and '(whispering)' in e['content']), None)
        dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'Do not make a sound' in e['content']), None)
        self.assertIsNotNone(char, "SARAH must be character")
        self.assertIsNotNone(paren, "(whispering) must be parenthetical")
        self.assertIsNotNone(dia, "Dialogue must be dialogue")
        self.assertNotIn('\u00A0', dia['content'], "Non-breaking spaces should be normalized")
        self.assertNotIn('<span', dia['content'], "HTML spans must be stripped")

    def test_18_malayalam_character_and_long_dialogue_and_mixed(self):
        """18. Malayalam character with dialogue > 40 chars and mixed English preserves element types."""
        raw_text = (
            "മമ്മൂട്ടി\n"
            "നമ്മൾ ഉദ്ദേശിച്ചതുപോലെ കാര്യങ്ങൾ മുന്നോട്ട് പോകുന്നില്ലെന്ന് എനിക്ക് വ്യക്തമായി തോന്നുന്നു.\n"
            "(ചിരിച്ചുകൊണ്ട്)\n"
            "Don't worry about the consequences, everything is planned carefully."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', heading);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

            inst.characters = ['മമ്മൂട്ടി'];
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
        """, raw_text)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        expected_types = ['character', 'dialogue', 'parenthetical', 'dialogue']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'മമ്മൂട്ടി')
        self.assertEqual(elems[1]['content'], 'നമ്മൾ ഉദ്ദേശിച്ചതുപോലെ കാര്യങ്ങൾ മുന്നോട്ട് പോകുന്നില്ലെന്ന് എനിക്ക് വ്യക്തമായി തോന്നുന്നു.')
        self.assertEqual(elems[2]['content'], '(ചിരിച്ചുകൊണ്ട്)')
        self.assertEqual(elems[3]['content'], "Don't worry about the consequences, everything is planned carefully.")

    def test_19_internal_multiblock_touch_selection_and_safari_fallback(self):
        """19. Simulates mobile touch copy where custom MIME is stripped and iOS Safari HTML fallback is used."""
        safari_sanitized_html = (
            '<div class="kadhascript-element element-type-action" data-element-type="action">A gentle morning breeze.</div>'
            '<div class="kadhascript-element element-type-character" data-element-type="character">KAVYA</div>'
            '<div class="kadhascript-element element-type-dialogue" data-element-type="dialogue">Are we ready to begin the shoot today?</div>'
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', heading);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

            const htmlContent = arguments[0];
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/html') return htmlContent;
                    return '';
                }
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """, safari_sanitized_html)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        expected_types = ['action', 'character', 'dialogue']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'A gentle morning breeze.')
        self.assertEqual(elems[1]['content'], 'KAVYA')
        self.assertEqual(elems[2]['content'], 'Are we ready to begin the shoot today?')

    def test_20_mobile_viewports_responsiveness_and_paste(self):
        """20. Mobile viewports at 320px, 375px, and 414px handle copy/paste correctly without UI breakage."""
        viewports = [(320, 568), (375, 667), (414, 896)]
        for width, height in viewports:
            self.driver.set_window_size(width, height)
            time.sleep(0.2)
            payload = self.driver.execute_script("""
                const inst = window.editorInstance;
                const text = 'ALEX\\nTesting mobile viewport paste at current resolution.';
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
            char = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'ALEX'), None)
            dia = next((e for e in elems if e['element_type'] == 'dialogue' and 'mobile viewport' in e['content']), None)
            self.assertIsNotNone(char, f"Character ALEX must be created at viewport {width}x{height}")
            self.assertIsNotNone(dia, f"Dialogue must be created at viewport {width}x{height}")
        # Reset window size to standard test size
        self.driver.set_window_size(1280, 900)
