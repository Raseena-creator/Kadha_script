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

    def test_21_android_simulation_beforeinput_insert_from_paste_exact_types(self):
        """21. [Simulation] Android beforeinput with inputType='insertFromPaste' does not dump screenplay into one Action element."""
        raw_text = (
            "INT. HOUSE - DAY\n"
            "RAHUL\n"
            "Are you sure you checked everything carefully before making this decision?\n"
            "ANJALI\n"
            "(quietly)\n"
            "I don't know what else I can tell you.\n"
            "HE TURNS AND WALKS TOWARD THE DOOR."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', null);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

            const text = arguments[0];
            const targetEditable = emptyAction.querySelector('.element-content');

            // Dispatch simulated Android beforeinput event
            const event = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: text
            });
            targetEditable.dispatchEvent(event);

            return inst.extractScenePayload();
        """, raw_text)

        elems = payload.get('elements', [])
        self.assertGreater(len(elems), 1, "Android paste must not be dumped into a single element")
        types = [e['element_type'] for e in elems]
        expected_types = [
            'scene_heading',
            'character',
            'dialogue',
            'character',
            'parenthetical',
            'dialogue',
            'action'
        ]
        self.assertEqual(types, expected_types, f"Expected types {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'INT. HOUSE - DAY')
        self.assertEqual(elems[1]['content'], 'RAHUL')
        self.assertEqual(elems[2]['content'], 'Are you sure you checked everything carefully before making this decision?')
        self.assertEqual(elems[3]['content'], 'ANJALI')
        self.assertEqual(elems[4]['content'], '(quietly)')
        self.assertEqual(elems[5]['content'], "I don't know what else I can tell you.")
        self.assertEqual(elems[6]['content'], 'HE TURNS AND WALKS TOWARD THE DOOR.')

    def test_22_android_simulation_beforeinput_gboard_insert_text_multiline(self):
        """22. [Simulation] Android Gboard multiline insertText inputType correctly parsed and typed."""
        raw_text = (
            "EXT. ROOFTOP - NIGHT\n"
            "VIKRAM\n"
            "The helicopter is approaching.\n"
            "(checking watch)\n"
            "We have two minutes."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', null);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

            const text = arguments[0];
            const targetEditable = emptyAction.querySelector('.element-content');

            // Android Gboard / virtual keyboard clipboard bar often uses InputConnection.commitText() -> insertText
            const event = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text
            });
            targetEditable.dispatchEvent(event);

            return inst.extractScenePayload();
        """, raw_text)

        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        expected_types = ['scene_heading', 'character', 'dialogue', 'parenthetical', 'dialogue']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'EXT. ROOFTOP - NIGHT')
        self.assertEqual(elems[1]['content'], 'VIKRAM')
        self.assertEqual(elems[2]['content'], 'The helicopter is approaching.')
        self.assertEqual(elems[3]['content'], '(checking watch)')
        self.assertEqual(elems[4]['content'], 'We have two minutes.')

    def test_23_android_simulation_malayalam_unicode_preserved(self):
        """23. [Simulation] Android keyboard paste preserves Malayalam Unicode, chillu, and complex scripts."""
        raw_text = (
            "INT. വീട് - DAY\n"
            "രാഹുൽ\n"
            "നീ എന്താണ് ഇവിടെ ചെയ്യുന്നത്?\n"
            "അഞ്ജലി\n"
            "(പതുക്കെ)\n"
            "എനിക്ക് ഒന്നും പറയാനില്ല.\n"
            "അവൻ വാതിലിലേക്ക് നടക്കുന്നു."
        )
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', '', null);
            emptyAction.querySelector('.element-content').focus();
            inst.activeElementBlock = emptyAction;

            inst.characters = ['രാഹുൽ', 'അഞ്ജലി'];
            const text = arguments[0];
            const targetEditable = emptyAction.querySelector('.element-content');

            const event = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: text
            });
            targetEditable.dispatchEvent(event);

            return inst.extractScenePayload();
        """, raw_text)

        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        expected_types = [
            'scene_heading',
            'character',
            'dialogue',
            'character',
            'parenthetical',
            'dialogue',
            'action'
        ]
        self.assertEqual(types, expected_types, f"Expected {expected_types}, got {types}")
        self.assertEqual(elems[0]['content'], 'INT. വീട് - DAY')
        self.assertEqual(elems[1]['content'], 'രാഹുൽ')
        self.assertEqual(elems[2]['content'], 'നീ എന്താണ് ഇവിടെ ചെയ്യുന്നത്?')
        self.assertEqual(elems[3]['content'], 'അഞ്ജലി')
        self.assertEqual(elems[4]['content'], '(പതുക്കെ)')
        self.assertEqual(elems[5]['content'], 'എനിക്ക് ഒന്നും പറയാനില്ല.')
        self.assertEqual(elems[6]['content'], 'അവൻ വാതിലിലേക്ക് നടക്കുന്നു.')

    def test_24_android_simulation_typing_and_enter_non_interference(self):
        """24. [Simulation] Ordinary single-character typing, words, Enter, and Shift-Enter are not intercepted."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const block = page.querySelector('.script-element-block') || inst.createElementBlock('action', '', null);
            const ed = block.querySelector('.element-content');

            // 1. Single character typing 'a'
            const evChar = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: 'a'
            });
            ed.dispatchEvent(evChar);
            const charPrevented = evChar.defaultPrevented;

            // 2. Word typing 'hello world'
            const evWord = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: 'hello world'
            });
            ed.dispatchEvent(evWord);
            const wordPrevented = evWord.defaultPrevented;

            // 3. Enter key (insertParagraph)
            let enterHandled = false;
            const origExecuteEnter = inst.executeEnter;
            inst.executeEnter = function() { enterHandled = true; };
            const evEnter = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertParagraph'
            });
            ed.dispatchEvent(evEnter);
            inst.executeEnter = origExecuteEnter;

            // 4. Line break (insertLineBreak)
            let lineBreakHandled = false;
            const origExecuteLineBreak = inst.executeLineBreak;
            inst.executeLineBreak = function() { lineBreakHandled = true; };
            const evBreak = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertLineBreak'
            });
            ed.dispatchEvent(evBreak);
            inst.executeLineBreak = origExecuteLineBreak;

            return {
                charPrevented,
                wordPrevented,
                enterHandled,
                lineBreakHandled
            };
        """)
        self.assertFalse(res['charPrevented'], "Single-character typing must not be intercepted")
        self.assertFalse(res['wordPrevented'], "Normal word typing must not be intercepted")
        self.assertTrue(res['enterHandled'], "insertParagraph must trigger executeEnter")
        self.assertTrue(res['lineBreakHandled'], "insertLineBreak must trigger executeLineBreak")

    def test_25_android_simulation_deduplication_and_missing_data_safety(self):
        """25. [Simulation] Companion events deduplicated in both orders; missing data leaves event unprevented."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const block = inst.createElementBlock('action', '', null);
            const ed = block.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = block;

            const textA = 'KABIR\\nWe cannot stay here any longer.';

            // Case A: paste event fires first, followed immediately by matching beforeinput companion
            const pasteEvent = new Event('paste', { bubbles: true, cancelable: true });
            pasteEvent.clipboardData = {
                getData: (f) => f === 'text/plain' ? textA : ''
            };
            document.dispatchEvent(pasteEvent);

            const beforeInputEvent = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: textA
            });
            ed.dispatchEvent(beforeInputEvent);

            const blocksAfterA = page.querySelectorAll('.script-element-block').length;
            const biPreventedA = beforeInputEvent.defaultPrevented;

            // Case B: beforeinput event fires first, followed immediately by matching paste companion
            const textB = 'TARA\\nI will get the keys.';
            const beforeInputEventB = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: textB
            });
            const lastEd = page.lastElementChild.querySelector('.element-content');
            lastEd.dispatchEvent(beforeInputEventB);

            const pasteEventB = new Event('paste', { bubbles: true, cancelable: true });
            pasteEventB.clipboardData = {
                getData: (f) => f === 'text/plain' ? textB : ''
            };
            document.dispatchEvent(pasteEventB);

            const blocksAfterB = page.querySelectorAll('.script-element-block').length;
            const pastePreventedB = pasteEventB.defaultPrevented;

            // Case C: missing/empty data in beforeinput without matching payload
            const evEmpty = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: null
            });
            lastEd.dispatchEvent(evEmpty);
            const emptyPrevented = evEmpty.defaultPrevented;
            const blocksAfterC = page.querySelectorAll('.script-element-block').length;

            return {
                blocksAfterA,
                biPreventedA,
                blocksAfterB,
                pastePreventedB,
                blocksAfterC,
                emptyPrevented
            };
        """)
        self.assertEqual(res['blocksAfterA'], 2, "paste followed by companion beforeinput must insert once (2 elements)")
        self.assertTrue(res['biPreventedA'], "companion beforeinput must be defaultPrevented")
        self.assertEqual(res['blocksAfterB'], 4, "beforeinput followed by companion paste must insert once (total 4 elements)")
        self.assertTrue(res['pastePreventedB'], "companion paste must be defaultPrevented")
        self.assertEqual(res['blocksAfterC'], 4, "Missing data in beforeinput must not insert duplicate or empty blocks")
        self.assertFalse(res['emptyPrevented'], "Missing data beforeinput must not prevent default or take responsibility")

    def test_26_android_simulation_undo_redo_and_save_pipeline(self):
        """26. [Simulation] Undo restores pre-paste state, redo restores typed elements, and saveCurrentScene succeeds."""
        res = self.driver.execute_async_script("""
            const callback = arguments[arguments.length - 1];
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());

            const headingBlock = inst.createElementBlock('scene_heading', 'INT. OFFICE - DAY', null);
            const actionBlock = inst.createElementBlock('action', 'Initial pre-paste text.', headingBlock);
            const ed = actionBlock.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = actionBlock;
            inst.pushUndoSnapshot();

            const text = 'MAYOR\\nWe need immediate answers.\\n\\nPOLICE CHIEF\\nOur officers are on the scene.';

            // Dispatch Android beforeinput paste
            const event = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: text
            });
            ed.dispatchEvent(event);

            const postPasteCount = page.querySelectorAll('.script-element-block').length;
            const postPasteTypes = Array.from(page.querySelectorAll('.script-element-block')).map(b => b.dataset.type);

            // Undo
            inst.undo();
            const postUndoCount = page.querySelectorAll('.script-element-block').length;
            const postUndoTypes = Array.from(page.querySelectorAll('.script-element-block')).map(b => b.dataset.type);

            // Redo
            inst.redo();
            const postRedoCount = page.querySelectorAll('.script-element-block').length;
            const postRedoTypes = Array.from(page.querySelectorAll('.script-element-block')).map(b => b.dataset.type);

            // Save
            inst.saveCurrentScene(true).then(() => {
                callback({
                    success: true,
                    postPasteCount,
                    postPasteTypes,
                    postUndoCount,
                    postUndoTypes,
                    postRedoCount,
                    postRedoTypes,
                    isDirty: inst.isDirty
                });
            }).catch(err => {
                callback({
                    success: false,
                    error: err.toString()
                });
            });
        """)

        self.assertTrue(res['success'], f"Save failed: {res.get('error')}")
        self.assertFalse(res['isDirty'], "Editor must not be dirty after successful saveCurrentScene")
        self.assertEqual(res['postPasteTypes'], ['scene_heading', 'action', 'character', 'dialogue', 'character', 'dialogue'])
        self.assertEqual(res['postUndoTypes'], ['scene_heading', 'action'], "Undo must restore exact pre-paste state")
        self.assertEqual(res['postRedoTypes'], ['scene_heading', 'action', 'character', 'dialogue', 'character', 'dialogue'], "Redo must restore exact typed elements")

    def test_27_android_simulation_heading_location_input_preserved(self):
        """27. [Simulation] Pasting into scene location input does not redirect text into screenplay body."""
        payload = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = inst.createElementBlock('action', 'Body text remains untouched.', heading);

            const locInput = heading.querySelector('.heading-location-input');
            locInput.focus();
            locInput.value = '';

            const pasteText = 'AIRPORT HANGAR\\nEXTRA LINE';
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: (f) => f === 'text/plain' ? pasteText : ''
            };
            locInput.dispatchEvent(event);

            return {
                locValue: locInput.value,
                scenePayload: inst.extractScenePayload()
            };
        """)

        self.assertIn('AIRPORT HANGAR', payload['locValue'])
        elems = payload['scenePayload'].get('elements', [])
        # The body element should remain 'action' with 'Body text remains untouched.'
        body_elems = [e for e in elems if e['element_type'] != 'scene_heading']
        self.assertEqual(len(body_elems), 1, "Location input paste must not spawn new blocks in the screenplay body")
        self.assertEqual(body_elems[0]['content'], 'Body text remains untouched.')

    def test_28_consecutive_intentional_pastes_identical_text(self):
        """28. [Simulation] Two consecutive intentional pastes of identical text through same event path both insert."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const block = inst.createElementBlock('action', '', null);
            const ed = block.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = block;

            const text = 'RAHUL\\nAre you sure about this?';

            // 1. Two consecutive pastes via paste event path
            const p1 = new Event('paste', { bubbles: true, cancelable: true });
            p1.clipboardData = { getData: (f) => f === 'text/plain' ? text : '' };
            document.dispatchEvent(p1);

            const blocksAfterPaste1 = page.querySelectorAll('.script-element-block').length;

            const p2 = new Event('paste', { bubbles: true, cancelable: true });
            p2.clipboardData = { getData: (f) => f === 'text/plain' ? text : '' };
            document.dispatchEvent(p2);

            const blocksAfterPaste2 = page.querySelectorAll('.script-element-block').length;

            // 2. Two consecutive pastes via beforeinput event path
            const biText = 'PRIYA\\nI have never been more certain.';
            const bi1 = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: biText
            });
            const lastEd1 = page.lastElementChild.querySelector('.element-content');
            lastEd1.dispatchEvent(bi1);
            const blocksAfterBi1 = page.querySelectorAll('.script-element-block').length;

            const bi2 = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: biText
            });
            const lastEd2 = page.lastElementChild.querySelector('.element-content');
            lastEd2.dispatchEvent(bi2);
            const blocksAfterBi2 = page.querySelectorAll('.script-element-block').length;

            const allTypes = Array.from(page.querySelectorAll('.script-element-block')).map(b => b.dataset.type);

            return {
                blocksAfterPaste1,
                blocksAfterPaste2,
                blocksAfterBi1,
                blocksAfterBi2,
                allTypes
            };
        """)
        self.assertEqual(res['blocksAfterPaste1'], 2, "First paste must create 2 blocks (character + dialogue)")
        self.assertEqual(res['blocksAfterPaste2'], 4, "Second identical paste via paste event path must ALSO insert (total 4 blocks)")
        self.assertEqual(res['blocksAfterBi1'], 6, "First beforeinput paste must append 2 blocks (total 6 blocks)")
        self.assertEqual(res['blocksAfterBi2'], 8, "Second identical beforeinput paste must ALSO append (total 8 blocks)")
        expected_types = ['character', 'dialogue', 'character', 'dialogue', 'character', 'dialogue', 'character', 'dialogue']
        self.assertEqual(res['allTypes'], expected_types)

    def test_29_consecutive_intentional_pastes_different_text(self):
        """29. [Simulation] Two consecutive intentional pastes of different text are both processed."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());
            const block = inst.createElementBlock('action', '', null);
            const ed = block.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = block;

            const text1 = 'ALICE\\nHello.';
            const text2 = 'BOB\\nGoodbye.';

            const p1 = new Event('paste', { bubbles: true, cancelable: true });
            p1.clipboardData = { getData: (f) => f === 'text/plain' ? text1 : '' };
            document.dispatchEvent(p1);

            const p2 = new Event('paste', { bubbles: true, cancelable: true });
            p2.clipboardData = { getData: (f) => f === 'text/plain' ? text2 : '' };
            document.dispatchEvent(p2);

            const allElements = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content') || {}).innerText || ''
            }));

            return { allElements };
        """)
        elems = res['allElements']
        self.assertEqual(len(elems), 4)
        self.assertEqual(elems[0]['type'], 'character')
        self.assertEqual(elems[0]['content'], 'ALICE')
        self.assertEqual(elems[1]['type'], 'dialogue')
        self.assertEqual(elems[1]['content'], 'Hello.')
        self.assertEqual(elems[2]['type'], 'character')
        self.assertEqual(elems[2]['content'], 'BOB')
        self.assertEqual(elems[3]['type'], 'dialogue')
        self.assertEqual(elems[3]['content'], 'Goodbye.')

    def test_30_stale_internal_payload_not_substituted_on_missing_data(self):
        """30. [Simulation] Stale internal payload is not substituted when current event data is missing or empty."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());

            // Set a stale lastCopiedPayload from a prior session/scene
            inst.lastCopiedPayload = {
                version: "1.0",
                source: "kadhascript",
                elements: [
                    { type: "character", content: "OLD_STALE_CHARACTER" },
                    { type: "dialogue", content: "Old stale dialogue line." }
                ]
            };

            const block = inst.createElementBlock('action', 'Original editor text remains untouched.', null);
            const ed = block.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = block;

            // Dispatch beforeinput with null/missing data
            const ev = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: null
            });
            ed.dispatchEvent(ev);

            const blocks = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content') || {}).innerText || ''
            }));

            return {
                prevented: ev.defaultPrevented,
                blocks
            };
        """)
        self.assertFalse(res['prevented'], "Missing data beforeinput must NOT preventDefault")
        self.assertEqual(len(res['blocks']), 1, "Must not insert stale elements into editor")
        self.assertEqual(res['blocks'][0]['type'], 'action')
        self.assertIn('Original editor text remains untouched.', res['blocks'][0]['content'])
        self.assertNotIn('OLD_STALE_CHARACTER', str(res['blocks']))

    def test_31_structured_insertion_failure_rollback_and_no_action_dump(self):
        """31. [Simulation] Structured insertion failure rolls back cleanly and does NOT dump screenplay into Action element."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());

            const heading = inst.createElementBlock('scene_heading', 'INT. LABORATORY - NIGHT', null);
            const initialAction = inst.createElementBlock('action', 'Initial stable action paragraph.', heading);
            const ed = initialAction.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = initialAction;

            const textToPaste = 'PROFESSOR\\nThe experiment was successful!\\n\\nASSISTANT\\nAre you certain?';

            // Simulate DOM error midway through element insertion (after 1st element created)
            const origCreateElementBlock = inst.createElementBlock;
            let callCount = 0;
            inst.createElementBlock = function(type, content, insertAfter) {
                callCount++;
                if (callCount === 2) {
                    throw new Error('Simulated DOM allocation or layout failure');
                }
                return origCreateElementBlock.call(this, type, content, insertAfter);
            };

            const pasteEv = new Event('paste', { bubbles: true, cancelable: true });
            pasteEv.clipboardData = { getData: (f) => f === 'text/plain' ? textToPaste : '' };

            try {
                document.dispatchEvent(pasteEv);
            } finally {
                inst.createElementBlock = origCreateElementBlock;
            }

            const resultingBlocks = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content') || {}).innerText || ''
            }));

            return {
                blockCount: resultingBlocks.length,
                resultingBlocks
            };
        """)
        self.assertEqual(res['blockCount'], 2, "Failed insertion must roll back partial blocks to original 2 blocks")
        self.assertEqual(res['resultingBlocks'][0]['type'], 'scene_heading')
        self.assertEqual(res['resultingBlocks'][1]['type'], 'action')
        self.assertEqual(res['resultingBlocks'][1]['content'], 'Initial stable action paragraph.')
        # CRITICAL: Verify multiline screenplay was NOT dumped as plain text into the single Action element
        self.assertNotIn('PROFESSOR', res['resultingBlocks'][1]['content'], "Screenplay must not be dumped into Action element on failure")
        self.assertNotIn('The experiment was successful!', res['resultingBlocks'][1]['content'])

    def test_32_android_beforeinput_null_data_unavailable_datatransfer_stale_payload_safety(self):
        """32. [Simulation] beforeinput with inputType='insertFromPaste', data=null, dataTransfer=unavailable does not insert stale payload."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());

            // 1. Establish an older, stale lastCopiedPayload from a prior copy/cut action
            inst.lastCopiedPayload = {
                version: "1.0",
                source: "kadhascript",
                elements: [
                    { type: "character", content: "STALE_DETECTIVE" },
                    { type: "dialogue", content: "This is a stale cached line that must NEVER appear." }
                ]
            };

            // 2. Set up initial editor content
            const heading = inst.createElementBlock('scene_heading', 'INT. DETECTIVE OFFICE - NIGHT', null);
            const initialAction = inst.createElementBlock('action', 'Detective sits at the desk in silence.', heading);
            const ed = initialAction.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = initialAction;

            const initialBlockCount = page.querySelectorAll('.script-element-block').length;
            const initialContent = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content:not(.d-none)') || b.querySelector('.element-content') || {}).innerText || ''
            }));

            // 3. Create real InputEvent with inputType='insertFromPaste', data=null, and verify dataTransfer is unavailable
            let threwException = false;
            let exceptionMessage = null;
            let defaultPreventedState = null;

            try {
                const ev = new InputEvent('beforeinput', {
                    bubbles: true,
                    cancelable: true,
                    inputType: 'insertFromPaste',
                    data: null
                });

                // Ensure dataTransfer is unavailable on the event object
                if ('dataTransfer' in ev && ev.dataTransfer !== null && ev.dataTransfer !== undefined) {
                    try {
                        delete ev.dataTransfer;
                    } catch (e) {
                        // If non-configurable, leave as is
                    }
                }

                // Dispatch event through the real DOM listener on the editable element
                ed.dispatchEvent(ev);
                defaultPreventedState = ev.defaultPrevented;
            } catch (err) {
                threwException = true;
                exceptionMessage = err.toString();
            }

            const postBlockCount = page.querySelectorAll('.script-element-block').length;
            const postContent = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content:not(.d-none)') || b.querySelector('.element-content') || {}).innerText || ''
            }));

            const fullPageText = page.innerText || '';

            return {
                threwException,
                exceptionMessage,
                defaultPreventedState,
                initialBlockCount,
                postBlockCount,
                initialContent,
                postContent,
                fullPageText
            };
        """)

        # 6. No exception is thrown
        self.assertFalse(res['threwException'], f"Dispatching beforeinput threw an unexpected exception: {res['exceptionMessage']}")

        # 4. defaultPrevented remains false when handler cannot safely take responsibility
        self.assertFalse(res['defaultPreventedState'], "beforeinput defaultPrevented must remain false when data is missing/unavailable")

        # 2. No new screenplay elements are created (count unchanged)
        self.assertEqual(res['postBlockCount'], res['initialBlockCount'], "Element count must not change when paste data is missing")

        # 3. Existing editor content remains unchanged
        self.assertEqual(res['postContent'], res['initialContent'], "Existing editor element types and text content must remain strictly identical")

        # 1. The old lastCopiedPayload is NOT inserted
        self.assertNotIn('STALE_DETECTIVE', res['fullPageText'], "Old lastCopiedPayload character must NOT be inserted into editor")
        self.assertNotIn('This is a stale cached line that must NEVER appear.', res['fullPageText'], "Old lastCopiedPayload dialogue must NOT be inserted into editor")

        # 5. No duplicate insertion occurs
        action_elements = [el for el in res['postContent'] if el['type'] == 'action']
        self.assertEqual(len(action_elements), 1, "Must contain exactly the single original action block without duplicates")
        self.assertEqual(action_elements[0]['content'], 'Detective sits at the desk in silence.')

    def test_33_android_companion_beforeinput_null_data_deduplication(self):
        """33. [Regression] Handled paste event followed by Android companion beforeinput (data=null) is prevented with no duplicate insertion; insertText unaffected."""
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block').forEach(b => b.remove());

            const block = inst.createElementBlock('action', '', null);
            const ed = block.querySelector('.element-content');
            ed.focus();
            inst.activeElementBlock = block;

            const text = 'VIKRAM\\nI am ready.';

            // 1. Dispatch successful paste event
            const pasteEvent = new Event('paste', { bubbles: true, cancelable: true });
            pasteEvent.clipboardData = {
                getData: (f) => f === 'text/plain' ? text : ''
            };
            document.dispatchEvent(pasteEvent);

            const blocksAfterPaste = page.querySelectorAll('.script-element-block').length;
            const pastePrevented = pasteEvent.defaultPrevented;

            // 2. Dispatch Android companion beforeinput with null data and unavailable dataTransfer
            const companionEvent = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertFromPaste',
                data: null
            });
            if ('dataTransfer' in companionEvent && companionEvent.dataTransfer !== null && companionEvent.dataTransfer !== undefined) {
                try { delete companionEvent.dataTransfer; } catch (e) {}
            }
            const activeEd = (inst.activeElementBlock || page.lastElementChild).querySelector('.element-content');
            activeEd.dispatchEvent(companionEvent);

            const companionPrevented = companionEvent.defaultPrevented;
            const blocksAfterCompanion = page.querySelectorAll('.script-element-block').length;

            // 3. Dispatch ordinary insertText (normal typing) to ensure it is not blocked
            const typingEvent = new InputEvent('beforeinput', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: 'A'
            });
            activeEd.dispatchEvent(typingEvent);
            const typingPrevented = typingEvent.defaultPrevented;

            const contentAfter = Array.from(page.querySelectorAll('.script-element-block')).map(b => ({
                type: b.dataset.type,
                content: (b.querySelector('.element-content:not(.d-none)') || b.querySelector('.element-content') || {}).innerText || ''
            }));

            return {
                pastePrevented,
                blocksAfterPaste,
                companionPrevented,
                blocksAfterCompanion,
                typingPrevented,
                contentAfter
            };
        """)

        # Test A: Handled paste + companion beforeinput (data=null) calls preventDefault()
        self.assertTrue(res['companionPrevented'], "Companion beforeinput with null data must be defaultPrevented")

        # Test B: Deduplication remains safe, exactly one set of blocks inserted (2 elements: VIKRAM + dialogue)
        self.assertEqual(res['blocksAfterPaste'], 2, "Paste event must create exactly 2 blocks (character + dialogue)")
        self.assertEqual(res['blocksAfterCompanion'], 2, "Companion beforeinput must not create duplicate blocks")
        self.assertEqual(res['contentAfter'][0]['type'], 'character')
        self.assertEqual(res['contentAfter'][0]['content'], 'VIKRAM')
        self.assertEqual(res['contentAfter'][1]['type'], 'dialogue')
        self.assertEqual(res['contentAfter'][1]['content'], 'I am ready.')

        # Test C: Normal insertText typing is NOT prevented
        self.assertFalse(res['typingPrevented'], "Normal insertText typing must NOT be prevented")

    def test_34_malayalam_parser_classification_batch_a(self):
        """34. [Batch A] Malayalam screenplay text classification: Action & Stage Directions vs Character & Dialogue."""
        # Test Case 1: Jyothi as character followed by dialogue
        raw_char_jyothi = "ജ്യോതി\nഞാൻ ഉടൻ തിരികെ വരാം."
        elems_char_jyothi = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_char_jyothi
        )
        self.assertEqual(len(elems_char_jyothi), 2)
        self.assertEqual(elems_char_jyothi[0]['type'], 'character')
        self.assertEqual(elems_char_jyothi[0]['content'], 'ജ്യോതി')
        self.assertEqual(elems_char_jyothi[1]['type'], 'dialogue')
        self.assertEqual(elems_char_jyothi[1]['content'], 'ഞാൻ ഉടൻ തിരികെ വരാം.')

        # Test Case 2: Dasan as character followed by dialogue
        raw_char_dasan = "ദാസൻ\nനമുക്ക് ഇപ്പോൾ തന്നെ ഇറങ്ങാം."
        elems_char_dasan = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_char_dasan
        )
        self.assertEqual(len(elems_char_dasan), 2)
        self.assertEqual(elems_char_dasan[0]['type'], 'character')
        self.assertEqual(elems_char_dasan[0]['content'], 'ദാസൻ')
        self.assertEqual(elems_char_dasan[1]['type'], 'dialogue')
        self.assertEqual(elems_char_dasan[1]['content'], 'നമുക്ക് ഇപ്പോൾ തന്നെ ഇറങ്ങാം.')

        # Test Case 3: Action with negative verb - "ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല"
        # Must be Action, NOT Character + Dialogue
        raw_neg_action = "ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല\nകുഞ്ഞു വീണ്ടും നിഷ്കളങ്കമായി കുത്തി കുത്തി ചോദിക്കുകയാണ്"
        elems_neg_action = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_neg_action
        )
        for el in elems_neg_action:
            self.assertNotEqual(el['type'], 'character', "Negative action line must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action', "Consecutive narrative action lines must be classified as Action")
        self.assertIn('ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല', elems_neg_action[0]['content'])
        self.assertIn('കുഞ്ഞു വീണ്ടും നിഷ്കളങ്കമായി കുത്തി കുത്തി ചോദിക്കുകയാണ്', elems_neg_action[0]['content'])

        # Test Case 4: Action with participial - "കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്"
        # Must be Action, followed by character Dasan + dialogue
        raw_participle = "കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്\n\nദാസൻ\nഞാൻ പോയി വരാം മോളേ."
        elems_participle = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_participle
        )
        self.assertEqual(len(elems_participle), 3)
        self.assertEqual(elems_participle[0]['type'], 'action')
        self.assertEqual(elems_participle[0]['content'], 'കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്')
        self.assertEqual(elems_participle[1]['type'], 'character')
        self.assertEqual(elems_participle[1]['content'], 'ദാസൻ')
        self.assertEqual(elems_participle[2]['type'], 'dialogue')
        self.assertEqual(elems_participle[2]['content'], 'ഞാൻ പോയി വരാം മോളേ.')

        # Test Case 5: Stage direction / Parenthetical context - "അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ"
        # When following Character cue, correctly becomes Parenthetical; never Character
        raw_paren_manner = "ദാസൻ\nഅൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ\nനീ എന്താണ് ഉദ്ദേശിക്കുന്നത്?"
        elems_paren_manner = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_paren_manner
        )
        self.assertEqual(len(elems_paren_manner), 3)
        self.assertEqual(elems_paren_manner[0]['type'], 'character')
        self.assertEqual(elems_paren_manner[0]['content'], 'ദാസൻ')
        self.assertEqual(elems_paren_manner[1]['type'], 'parenthetical')
        self.assertEqual(elems_paren_manner[1]['content'], '(അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ)')
        self.assertEqual(elems_paren_manner[2]['type'], 'dialogue')
        self.assertEqual(elems_paren_manner[2]['content'], 'നീ എന്താണ് ഉദ്ദേശിക്കുന്നത്?')

        # When standalone / surrounded by action, correctly remains Action; never Character
        raw_action_manner = "അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ\nഅയാൾ കസേരയിൽ വന്നിരിക്കുന്നു."
        elems_action_manner = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_action_manner
        )
        for el in elems_action_manner:
            self.assertNotEqual(el['type'], 'character', "Manner phrase must NEVER be classified as Character cue")
            self.assertEqual(el['type'], 'action')

        # Test Case 6: Stage direction / Parenthetical context - "ഇതിനിടയിൽ പരിഭ്രമത്തോടെ"
        # Following character cue -> parenthetical
        raw_paren_paribhramam = "ജ്യോതി\nഇതിനിടയിൽ പരിഭ്രമത്തോടെ\nഎനിക്ക് ഒന്നും അറിയില്ല!"
        elems_paren_paribhramam = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_paren_paribhramam
        )
        self.assertEqual(len(elems_paren_paribhramam), 3)
        self.assertEqual(elems_paren_paribhramam[0]['type'], 'character')
        self.assertEqual(elems_paren_paribhramam[0]['content'], 'ജ്യോതി')
        self.assertEqual(elems_paren_paribhramam[1]['type'], 'parenthetical')
        self.assertEqual(elems_paren_paribhramam[1]['content'], '(ഇതിനിടയിൽ പരിഭ്രമത്തോടെ)')
        self.assertEqual(elems_paren_paribhramam[2]['type'], 'dialogue')
        self.assertEqual(elems_paren_paribhramam[2]['content'], 'എനിക്ക് ഒന്നും അറിയില്ല!')

        # Standalone before action -> Action, never Character
        raw_action_paribhramam = "ഇതിനിടയിൽ പരിഭ്രമത്തോടെ\nഅവൾ ചുറ്റും നോക്കുകയാണ്."
        elems_action_paribhramam = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_action_paribhramam
        )
        for el in elems_action_paribhramam:
            self.assertNotEqual(el['type'], 'character', "Stage direction phrase must NEVER be classified as Character cue")
            self.assertEqual(el['type'], 'action')

        # Test Case 7: Full scene paste via handlePaste simulation
        full_paste_text = (
            "ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല\n\n"
            "കുഞ്ഞു വീണ്ടും നിഷ്കളങ്കമായി കുത്തി കുത്തി ചോദിക്കുകയാണ്\n\n"
            "കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്\n\n"
            "ദാസൻ\n"
            "അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ\n"
            "നീ ഇപ്പോൾ ഉറങ്ങാൻ നോക്ക്.\n\n"
            "ഇതിനിടയിൽ പരിഭ്രമത്തോടെ\n"
            "ജ്യോതി വാതിലിലേക്ക് നോക്കുകയാണ്."
        )
        res = self.driver.execute_script("""
            const inst = window.editorInstance;
            const page = inst.pageContainer;
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            const anchor = inst.createElementBlock('action', '', heading);
            anchor.querySelector('.element-content').focus();
            inst.activeElementBlock = anchor;

            const text = arguments[0];
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: (f) => f === 'text/plain' ? text : ''
            };
            inst.handlePaste(event);
            return inst.extractScenePayload();
        """, full_paste_text)

        elements = [e for e in res.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elements]
        # Expected sequence:
        # 1. Action: ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല
        # 2. Action: കുഞ്ഞു വീണ്ടും നിഷ്കളങ്കമായി കുത്തി കുത്തി ചോദിക്കുകയാണ്
        # 3. Action: കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്
        # 4. Character: ദാസൻ
        # 5. Parenthetical: (അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ)
        # 6. Dialogue: നീ ഇപ്പോൾ ഉറങ്ങാൻ നോക്ക്.
        # 7. Action: ഇതിനിടയിൽ പരിഭ്രമത്തോടെ\nജ്യോതി വാതിലിലേക്ക് നോക്കുകയാണ്.
        expected_types = ['action', 'action', 'action', 'character', 'parenthetical', 'dialogue', 'action']
        self.assertEqual(types, expected_types, f"Expected {expected_types}, but got {types}")
        self.assertEqual(elements[3]['content'], 'ദാസൻ')
        self.assertEqual(elements[4]['content'], '(അൽപ്പം ഇറിറ്റേറ്റഡ് ആയ മട്ടിൽ)')
        self.assertEqual(elements[5]['content'], 'നീ ഇപ്പോൾ ഉറങ്ങാൻ നോക്ക്.')

        # -------------------------------------------------------------------------
        # Batch A1 Dialogue Regression Tests
        # -------------------------------------------------------------------------

        # Test A: Dialogue ending in പോകുന്നു
        raw_test_a = "രാഹുൽ\nഞാൻ ഇപ്പോൾ വീട്ടിലേക്ക് പോകുന്നു."
        elems_test_a = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_test_a
        )
        self.assertEqual(len(elems_test_a), 2)
        self.assertEqual(elems_test_a[0]['type'], 'character')
        self.assertEqual(elems_test_a[0]['content'], 'രാഹുൽ')
        self.assertEqual(elems_test_a[1]['type'], 'dialogue')
        self.assertEqual(elems_test_a[1]['content'], 'ഞാൻ ഇപ്പോൾ വീട്ടിലേക്ക് പോകുന്നു.')

        # Test B: Dialogue ending in പറയുന്നില്ല (negative verb form)
        raw_test_b = "ജ്യോതി\nഅവൻ എന്നോട് ഒന്നും പറയുന്നില്ല."
        elems_test_b = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_test_b
        )
        self.assertEqual(len(elems_test_b), 2)
        self.assertEqual(elems_test_b[0]['type'], 'character')
        self.assertEqual(elems_test_b[0]['content'], 'ജ്യോതി')
        self.assertEqual(elems_test_b[1]['type'], 'dialogue')
        self.assertEqual(elems_test_b[1]['content'], 'അവൻ എന്നോട് ഒന്നും പറയുന്നില്ല.')

        # Test C: Dialogue ending in ചോദിക്കുകയാണ് (continuous verb form)
        raw_test_c = "കുഞ്ഞു\nഞാൻ നിങ്ങളോട് ചോദിക്കുകയാണ്."
        elems_test_c = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_test_c
        )
        self.assertEqual(len(elems_test_c), 2)
        self.assertEqual(elems_test_c[0]['type'], 'character')
        self.assertEqual(elems_test_c[0]['content'], 'കുഞ്ഞു')
        self.assertEqual(elems_test_c[1]['type'], 'dialogue')
        self.assertEqual(elems_test_c[1]['content'], 'ഞാൻ നിങ്ങളോട് ചോദിക്കുകയാണ്.')

        # Test D: Multi-line dialogue vs narrative action boundary
        # Sub-case D1: Multiple lines of spoken dialogue without narrative action starter
        raw_test_d1 = "ദാസൻ\nഎനിക്ക് പേടിയാകുന്നു.\nനമുക്ക് ഇവിടെ നിന്ന് പോകാം."
        elems_test_d1 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_test_d1
        )
        self.assertEqual(len(elems_test_d1), 2)
        self.assertEqual(elems_test_d1[0]['type'], 'character')
        self.assertEqual(elems_test_d1[0]['content'], 'ദാസൻ')
        self.assertEqual(elems_test_d1[1]['type'], 'dialogue')
        self.assertEqual(elems_test_d1[1]['content'], 'എനിക്ക് പേടിയാകുന്നു.\nനമുക്ക് ഇവിടെ നിന്ന് പോകാം.')

        # Sub-case D2: Spoken dialogue followed by narrative action line starting with narrative starter അവൻ
        raw_test_d2 = "ദാസൻ\nഎനിക്ക് പേടിയാകുന്നു.\nഅവൻ വാതിലിലേക്ക് നോക്കുന്നു."
        elems_test_d2 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_test_d2
        )
        self.assertEqual(len(elems_test_d2), 3)
        self.assertEqual(elems_test_d2[0]['type'], 'character')
        self.assertEqual(elems_test_d2[0]['content'], 'ദാസൻ')
        self.assertEqual(elems_test_d2[1]['type'], 'dialogue')
        self.assertEqual(elems_test_d2[1]['content'], 'എനിക്ക് പേടിയാകുന്നു.')
        self.assertEqual(elems_test_d2[2]['type'], 'action')
        self.assertEqual(elems_test_d2[2]['content'], 'അവൻ വാതിലിലേക്ക് നോക്കുന്നു.')

        # -------------------------------------------------------------------------
        # Batch A2 Regression Tests: Negative, Continuous, Manner & Parenthetical Actions
        # -------------------------------------------------------------------------

        # 1. Past negative verb action: "ജ്യോതി ഒന്നും പറഞ്ഞില്ല"
        raw_a2_1 = "ജ്യോതി ഒന്നും പറഞ്ഞില്ല\nഅവൾ മുറിയിൽ നിന്ന് പുറത്തേക്ക് നടന്നു."
        elems_a2_1 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_1
        )
        for el in elems_a2_1:
            self.assertNotEqual(el['type'], 'character', "'ജ്യോതി ഒന്നും പറഞ്ഞില്ല' must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('ജ്യോതി ഒന്നും പറഞ്ഞില്ല', elems_a2_1[0]['content'])

        # 2. Past negative verb action: "കുഞ്ഞു ഒന്നും മിണ്ടിയില്ല"
        raw_a2_2 = "കുഞ്ഞു ഒന്നും മിണ്ടിയില്ല\nഅവൻ ജനലിലൂടെ പുറത്തേക്ക് നോക്കുന്നു."
        elems_a2_2 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_2
        )
        for el in elems_a2_2:
            self.assertNotEqual(el['type'], 'character', "'കുഞ്ഞു ഒന്നും മിണ്ടിയില്ല' must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('കുഞ്ഞു ഒന്നും മിണ്ടിയില്ല', elems_a2_2[0]['content'])

        # 3. Continuous action: "നടന്നുകൊണ്ടിരിക്കുന്നു"
        raw_a2_3 = "അയാൾ മുന്നോട്ട് നടന്നുകൊണ്ടിരിക്കുന്നു\nമഴ പെയ്യുന്നുണ്ട്."
        elems_a2_3 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_3
        )
        for el in elems_a2_3:
            self.assertNotEqual(el['type'], 'character', "Continuous verb phrase must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('നടന്നുകൊണ്ടിരിക്കുന്നു', elems_a2_3[0]['content'])

        # 4. Continuous action: "സംസാരിച്ചുകൊണ്ടിരുന്നു"
        raw_a2_4 = "അവർ പരസ്പരം സംസാരിച്ചുകൊണ്ടിരുന്നു\nസമയം കടന്നുപോയി."
        elems_a2_4 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_4
        )
        for el in elems_a2_4:
            self.assertNotEqual(el['type'], 'character', "Continuous verb phrase must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('സംസാരിച്ചുകൊണ്ടിരുന്നു', elems_a2_4[0]['content'])

        # 5. Manner phrase: "കളിയാക്കുന്ന രീതിയിൽ"
        raw_a2_5 = "കളിയാക്കുന്ന രീതിയിൽ\nഅയാൾ ചിരിച്ചു."
        elems_a2_5 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_5
        )
        for el in elems_a2_5:
            self.assertNotEqual(el['type'], 'character', "Manner phrase ending in രീതിയിൽ must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('കളിയാക്കുന്ന രീതിയിൽ', elems_a2_5[0]['content'])

        # 6. Manner phrase: "വിനയപൂർവ്വം"
        raw_a2_6 = "വിനയപൂർവ്വം\nഅവൻ തലകുനിച്ചു."
        elems_a2_6 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_6
        )
        for el in elems_a2_6:
            self.assertNotEqual(el['type'], 'character', "Manner phrase ending in പൂർവ്വം must NOT be classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('വിനയപൂർവ്വം', elems_a2_6[0]['content'])

        # 7. Action with bracketed manner note: "അയാൾ കസേരയിൽ ഇരുന്നു (ക്ഷീണത്തോടെ)"
        raw_a2_7 = "അയാൾ കസേരയിൽ ഇരുന്നു (ക്ഷീണത്തോടെ)\nമുറിയിൽ വലിയ നിശബ്ദത."
        elems_a2_7 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_7
        )
        for el in elems_a2_7:
            self.assertNotEqual(el['type'], 'character', "Action ending in parenthetical must NOT have action part classified as Character cue")
            self.assertEqual(el['type'], 'action')
        self.assertIn('അയാൾ കസേരയിൽ ഇരുന്നു', elems_a2_7[0]['content'])

        # 8. Genuine character with character extension: "ദാസൻ (V.O.)"
        raw_a2_8 = "ദാസൻ (V.O.)\nഎനിക്ക് എല്ലാം ഓർമ്മയുണ്ട്."
        elems_a2_8 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_8
        )
        self.assertEqual(len(elems_a2_8), 2)
        self.assertEqual(elems_a2_8[0]['type'], 'character')
        self.assertEqual(elems_a2_8[0]['content'], 'ദാസൻ (V.O.)')
        self.assertEqual(elems_a2_8[1]['type'], 'dialogue')
        self.assertEqual(elems_a2_8[1]['content'], 'എനിക്ക് എല്ലാം ഓർമ്മയുണ്ട്.')

        # 9. Genuine character with inline parenthetical: "ജ്യോതി (ചിരിച്ചുകൊണ്ട്)"
        raw_a2_9 = "ജ്യോതി (ചിരിച്ചുകൊണ്ട്)\nനമുക്ക് തുടങ്ങാം."
        elems_a2_9 = self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0]);",
            raw_a2_9
        )
        self.assertEqual(len(elems_a2_9), 3)
        self.assertEqual(elems_a2_9[0]['type'], 'character')
        self.assertEqual(elems_a2_9[0]['content'], 'ജ്യോതി')
        self.assertEqual(elems_a2_9[1]['type'], 'parenthetical')
        self.assertEqual(elems_a2_9[1]['content'], '(ചിരിച്ചുകൊണ്ട്)')
        self.assertEqual(elems_a2_9[2]['type'], 'dialogue')
        self.assertEqual(elems_a2_9[2]['content'], 'നമുക്ക് തുടങ്ങാം.')
