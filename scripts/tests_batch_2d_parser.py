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
class ScreenplayParserIsolatedTests(StaticLiveServerTestCase):
    """
    Focused unit/integration tests for the Batch 2D Screenplay Parser.
    Tests the isolated parseScreenplayText() method across:
    1. Standard English screenplay
    2. Multiple action paragraphs
    3. Character/dialogue sequences
    4. Parentheticals
    5. Transitions
    6. Multiple scene headings
    7. Malayalam character names and dialogue
    8. Mixed Malayalam and English
    9. Ambiguous multiline text (falls back safely to action)
    10. Empty input and whitespace-only input
    11. Single-line input
    12. Preservation of punctuation and Unicode
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
            cls.driver = webdriver.Chrome(service=service, options=opts)
        else:
            cls.driver = webdriver.Chrome(options=opts)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.driver.quit()
        except Exception:
            pass
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.username = f"parser_tester_{int(time.time() * 1000) % 100000}"
        self.user = User.objects.create_user(username=self.username, password="password123")
        self.script = Script.objects.create(
            user=self.user,
            title="പാഴ്സർ പരിശോധന (Parser Test)",
            script_type="Feature Film",
            language="Malayalam"
        )
        self.scene = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading="INT. TEST STUDIO - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type="scene_heading",
            content="INT. TEST STUDIO - DAY",
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene,
            element_type="action",
            content="Initial action block.",
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

    def call_parser(self, text, custom_characters=None):
        return self.driver.execute_script(
            "return window.editorInstance.parseScreenplayText(arguments[0], arguments[1]);",
            text,
            custom_characters
        )

    def simulate_external_paste(self, text):
        return self.driver.execute_script("""
            const text = arguments[0];
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return text;
                    return '';
                }
            };
            window.editorInstance.handlePaste(event);
            return window.editorInstance.extractScenePayload();
        """, text)

    def simulate_internal_paste(self, elements):
        return self.driver.execute_script("""
            const elements = arguments[0];
            const payload = {
                version: "1.0",
                source: "kadhascript",
                elements: elements
            };
            const jsonStr = JSON.stringify(payload);
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'application/x-kadhascript-elements') return jsonStr;
                    return '';
                }
            };
            window.editorInstance.handlePaste(event);
            return window.editorInstance.extractScenePayload();
        """, elements)

    # -------------------------------------------------------------------------
    # 1. Standard English screenplay
    # -------------------------------------------------------------------------
    def test_01_standard_english_screenplay(self):
        raw = """INT. COFFEE SHOP - DAY

John sits alone, sipping espresso.

JOHN
I didn't expect you to come.

MARY
(smiling)
Neither did I.

CUT TO:"""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 8)
        self.assertEqual(elements[0], {'type': 'scene_heading', 'content': 'INT. COFFEE SHOP - DAY'})
        self.assertEqual(elements[1], {'type': 'action', 'content': 'John sits alone, sipping espresso.'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'JOHN'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': "I didn't expect you to come."})
        self.assertEqual(elements[4], {'type': 'character', 'content': 'MARY'})
        self.assertEqual(elements[5], {'type': 'parenthetical', 'content': '(smiling)'})
        self.assertEqual(elements[6], {'type': 'dialogue', 'content': 'Neither did I.'})
        self.assertEqual(elements[7], {'type': 'transition', 'content': 'CUT TO:'})

    # -------------------------------------------------------------------------
    # 2. Multiple action paragraphs
    # -------------------------------------------------------------------------
    def test_02_multiple_action_paragraphs(self):
        raw = """The rain pours relentlessly on the pavement.
Wind howls through the narrow alley.

Inside, the clock ticks loudly on the wall."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 2)
        self.assertEqual(elements[0]['type'], 'action')
        self.assertIn('The rain pours relentlessly on the pavement.', elements[0]['content'])
        self.assertIn('Wind howls through the narrow alley.', elements[0]['content'])
        self.assertEqual(elements[1]['type'], 'action')
        self.assertEqual(elements[1]['content'], 'Inside, the clock ticks loudly on the wall.')

    # -------------------------------------------------------------------------
    # 3. Character/dialogue sequences
    # -------------------------------------------------------------------------
    def test_03_character_dialogue_sequences(self):
        raw = """RAHUL
Where are you going?

PRIYA
Far away. Across the border."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'RAHUL'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'Where are you going?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'PRIYA'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': 'Far away. Across the border.'})

    # -------------------------------------------------------------------------
    # 4. Parentheticals
    # -------------------------------------------------------------------------
    def test_04_parentheticals(self):
        raw = """RAHUL
(whispering)
Don't make any noise."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 3)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'RAHUL'})
        self.assertEqual(elements[1], {'type': 'parenthetical', 'content': '(whispering)'})
        self.assertEqual(elements[2], {'type': 'dialogue', 'content': "Don't make any noise."})

    # -------------------------------------------------------------------------
    # 5. Transitions
    # -------------------------------------------------------------------------
    def test_05_transitions(self):
        raw = """FADE IN:

EXT. PARK - DAWN

Birds chirp in the cool morning air.

DISSOLVE TO:

INT. OFFICE - DAY

Papers cover the desk.

FADE OUT."""
        elements = self.call_parser(raw)
        self.assertEqual(elements[0], {'type': 'transition', 'content': 'FADE IN:'})
        self.assertEqual(elements[1], {'type': 'scene_heading', 'content': 'EXT. PARK - DAWN'})
        self.assertEqual(elements[2], {'type': 'action', 'content': 'Birds chirp in the cool morning air.'})
        self.assertEqual(elements[3], {'type': 'transition', 'content': 'DISSOLVE TO:'})
        self.assertEqual(elements[4], {'type': 'scene_heading', 'content': 'INT. OFFICE - DAY'})
        self.assertEqual(elements[5], {'type': 'action', 'content': 'Papers cover the desk.'})
        self.assertEqual(elements[6], {'type': 'transition', 'content': 'FADE OUT.'})

    # -------------------------------------------------------------------------
    # 6. Multiple scene headings
    # -------------------------------------------------------------------------
    def test_06_multiple_scene_headings(self):
        raw = """INT. BEDROOM - NIGHT

Rahul sleeps peacefully.

EXT. GARDEN - MORNING

Sunlight filters through the leaves."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0], {'type': 'scene_heading', 'content': 'INT. BEDROOM - NIGHT'})
        self.assertEqual(elements[1], {'type': 'action', 'content': 'Rahul sleeps peacefully.'})
        self.assertEqual(elements[2], {'type': 'scene_heading', 'content': 'EXT. GARDEN - MORNING'})
        self.assertEqual(elements[3], {'type': 'action', 'content': 'Sunlight filters through the leaves.'})

    # -------------------------------------------------------------------------
    # 7. Malayalam character names and dialogue
    # -------------------------------------------------------------------------
    def test_07_malayalam_character_names_and_dialogue(self):
        raw = """രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
(ചിരിച്ചുകൊണ്ട്)
ഞാൻ ഉടൻ വരാം."""
        elements = self.call_parser(raw, ['രാഹുൽ', 'അമ്മ'])
        self.assertEqual(len(elements), 5)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'രാഹുൽ'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'നീ എവിടെ പോകുന്നു?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[3], {'type': 'parenthetical', 'content': '(ചിരിച്ചുകൊണ്ട്)'})
        self.assertEqual(elements[4], {'type': 'dialogue', 'content': 'ഞാൻ ഉടൻ വരാം.'})

    # -------------------------------------------------------------------------
    # 8. Mixed Malayalam and English
    # -------------------------------------------------------------------------
    def test_08_mixed_malayalam_and_english(self):
        raw = """INT. KITCHEN - DAY

അമ്മ അടുക്കളയിൽ ചായ ഉണ്ടാക്കുന്നു.

AMMA
(looking back)
ചായ കുടിക്കൂ മോനേ."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 5)
        self.assertEqual(elements[0], {'type': 'scene_heading', 'content': 'INT. KITCHEN - DAY'})
        self.assertEqual(elements[1], {'type': 'action', 'content': 'അമ്മ അടുക്കളയിൽ ചായ ഉണ്ടാക്കുന്നു.'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'AMMA'})
        self.assertEqual(elements[3], {'type': 'parenthetical', 'content': '(looking back)'})
        self.assertEqual(elements[4], {'type': 'dialogue', 'content': 'ചായ കുടിക്കൂ മോനേ.'})

    # -------------------------------------------------------------------------
    # 9. Ambiguous multiline text
    # -------------------------------------------------------------------------
    def test_09_ambiguous_multiline_text(self):
        raw = """This is an ordinary article paragraph.
It describes an event in general narrative style.

The second paragraph continues the description without any screenplay formatting.
Nothing here resembles dialogue or characters."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 2)
        self.assertEqual(elements[0]['type'], 'action')
        self.assertIn('This is an ordinary article paragraph.', elements[0]['content'])
        self.assertEqual(elements[1]['type'], 'action')
        self.assertIn('The second paragraph continues the description', elements[1]['content'])

    # -------------------------------------------------------------------------
    # 10. Empty input and whitespace-only input
    # -------------------------------------------------------------------------
    def test_10_empty_and_whitespace_input(self):
        self.assertEqual(self.call_parser(""), [])
        self.assertEqual(self.call_parser("   \n\t  \n   "), [])
        self.assertEqual(self.call_parser(None), [])

    # -------------------------------------------------------------------------
    # 11. Single-line input
    # -------------------------------------------------------------------------
    def test_11_single_line_input(self):
        res1 = self.call_parser("The quick brown fox jumps over the lazy dog.")
        self.assertEqual(res1, [{'type': 'action', 'content': 'The quick brown fox jumps over the lazy dog.'}])

        res2 = self.call_parser("INT. CORRIDOR - NIGHT")
        self.assertEqual(res2, [{'type': 'scene_heading', 'content': 'INT. CORRIDOR - NIGHT'}])

        res3 = self.call_parser("CUT TO:")
        self.assertEqual(res3, [{'type': 'transition', 'content': 'CUT TO:'}])

    # -------------------------------------------------------------------------
    # 12. Preservation of punctuation and Unicode
    # -------------------------------------------------------------------------
    def test_12_preservation_of_punctuation_and_unicode(self):
        raw = """അമ്മ ചോദിച്ചു: "നീ എന്താണ് ചെയ്യുന്നത്?"
രാഹുൽ പറഞ്ഞു: 'ഒന്നുമില്ല!' — അവൻ ചിരിച്ചു."""
        elements = self.call_parser(raw)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]['type'], 'action')
        self.assertIn('അമ്മ ചോദിച്ചു: "നീ എന്താണ് ചെയ്യുന്നത്?"', elements[0]['content'])
        self.assertIn("രാഹുൽ പറഞ്ഞു: 'ഒന്നുമില്ല!' — അവൻ ചിരിച്ചു.", elements[0]['content'])

    # -------------------------------------------------------------------------
    # 13. Numbered shots vs ordinary numbered lists
    # -------------------------------------------------------------------------
    def test_13_numbered_shots_and_ordinary_numbered_lists(self):
        # 1. Valid sequence numbered shots
        raw_shots = """1. INT. ROOM - DAY

John looks around.

2. EXT. STREET - NIGHT"""
        res_shots = self.call_parser(raw_shots)
        self.assertEqual(len(res_shots), 3)
        self.assertEqual(res_shots[0], {'type': 'shot', 'content': '1. INT. ROOM - DAY'})
        self.assertEqual(res_shots[1], {'type': 'action', 'content': 'John looks around.'})
        self.assertEqual(res_shots[2], {'type': 'shot', 'content': '2. EXT. STREET - NIGHT'})

        # 2. Ordinary numbered list (contiguous) - must remain pure action
        raw_list = """1. Buy groceries
2. Call the bank
3. Review notes"""
        res_list = self.call_parser(raw_list)
        self.assertEqual(len(res_list), 1)
        self.assertEqual(res_list[0]['type'], 'action')
        self.assertIn('1. Buy groceries', res_list[0]['content'])
        self.assertIn('2. Call the bank', res_list[0]['content'])
        self.assertIn('3. Review notes', res_list[0]['content'])

        # 3. Ordinary numbered list with blank lines - each item is an action paragraph
        raw_spaced_list = """1. Buy groceries

2. Call the bank"""
        res_spaced_list = self.call_parser(raw_spaced_list)
        self.assertEqual(len(res_spaced_list), 2)
        self.assertEqual(res_spaced_list[0], {'type': 'action', 'content': '1. Buy groceries'})
        self.assertEqual(res_spaced_list[1], {'type': 'action', 'content': '2. Call the bank'})

    # -------------------------------------------------------------------------
    # 14. All four Song/Montage sequence markers
    # -------------------------------------------------------------------------
    def test_14_all_sequence_markers(self):
        # Song sequence markers
        raw_song = """SONG BEGINS

1. INT. AUDITORIUM - DAY

Singers perform.

SONG ENDS"""
        res_song = self.call_parser(raw_song)
        self.assertEqual(len(res_song), 4)
        self.assertEqual(res_song[0], {'type': 'shot', 'content': 'SONG BEGINS'})
        self.assertEqual(res_song[1], {'type': 'shot', 'content': '1. INT. AUDITORIUM - DAY'})
        self.assertEqual(res_song[2], {'type': 'action', 'content': 'Singers perform.'})
        self.assertEqual(res_song[3], {'type': 'shot', 'content': 'SONG ENDS'})

        # Montage sequence markers with colons
        raw_montage = """MONTAGE BEGINS:

1. EXT. CITY - DAWN

Cars speed through morning fog.

MONTAGE ENDS:"""
        res_montage = self.call_parser(raw_montage)
        self.assertEqual(len(res_montage), 4)
        self.assertEqual(res_montage[0], {'type': 'shot', 'content': 'MONTAGE BEGINS'})
        self.assertEqual(res_montage[1], {'type': 'shot', 'content': '1. EXT. CITY - DAWN'})
        self.assertEqual(res_montage[2], {'type': 'action', 'content': 'Cars speed through morning fog.'})
        self.assertEqual(res_montage[3], {'type': 'shot', 'content': 'MONTAGE ENDS'})

    # -------------------------------------------------------------------------
    # 15. Inline notes
    # -------------------------------------------------------------------------
    def test_15_inline_notes(self):
        raw_notes = """[[ Need reference track for background music ]]

INT. CAFE - DAY

[[ Verify shoot permissions ]]

Rahul drinks coffee."""
        res_notes = self.call_parser(raw_notes)
        self.assertEqual(len(res_notes), 4)
        self.assertEqual(res_notes[0], {'type': 'note', 'content': 'Need reference track for background music'})
        self.assertEqual(res_notes[1], {'type': 'scene_heading', 'content': 'INT. CAFE - DAY'})
        self.assertEqual(res_notes[2], {'type': 'note', 'content': 'Verify shoot permissions'})
        self.assertEqual(res_notes[3], {'type': 'action', 'content': 'Rahul drinks coffee.'})

    # -------------------------------------------------------------------------
    # 16. External paste: multiline screenplay blocks
    # -------------------------------------------------------------------------
    def test_16_external_paste_screenplay_blocks(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw = """JOHN
I didn't expect you.

MARY
(smiling)
Neither did I."""
        payload = self.simulate_external_paste(raw)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('character', types)
        self.assertIn('dialogue', types)
        self.assertIn('parenthetical', types)
        char_john = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'JOHN'), None)
        self.assertIsNotNone(char_john)
        paren = next((e for e in elems if e['element_type'] == 'parenthetical'), None)
        self.assertEqual(paren['content'], '(smiling)')

    # -------------------------------------------------------------------------
    # 17. External paste: Malayalam action and dialogue preservation
    # -------------------------------------------------------------------------
    def test_17_external_paste_malayalam_screenplay(self):
        self.driver.execute_script("""
            window.editorInstance.characters = ['രാഹുൽ', 'അമ്മ'];
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw = """രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
(ചിരിച്ചുകൊണ്ട്)
ഞാൻ ഉടൻ വരാം."""
        payload = self.simulate_external_paste(raw)
        elems = payload.get('elements', [])
        types = [e['element_type'] for e in elems]
        self.assertIn('character', types)
        self.assertIn('dialogue', types)
        self.assertIn('parenthetical', types)
        char_rahul = next((e for e in elems if e['element_type'] == 'character' and e['content'] == 'രാഹുൽ'), None)
        self.assertIsNotNone(char_rahul)
        dia_rahul = next((e for e in elems if e['element_type'] == 'dialogue' and e['content'] == 'നീ എവിടെ പോകുന്നു?'), None)
        self.assertIsNotNone(dia_rahul)
        paren = next((e for e in elems if e['element_type'] == 'parenthetical' and e['content'] == '(ചിരിച്ചുകൊണ്ട്)'), None)
        self.assertIsNotNone(paren)

    # -------------------------------------------------------------------------
    # 18. External paste: single-line plain text inline preservation
    # -------------------------------------------------------------------------
    def test_18_external_paste_single_line_inline(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const action = window.editorInstance.createElementBlock('action', 'Initial line.', heading);
            const ed = action.querySelector('.element-content');
            ed.focus();
            window.editorInstance.setCursorToEnd(ed);
            window.editorInstance.activeElementBlock = action;
        """)
        initial_count = self.driver.execute_script("return window.editorInstance.pageContainer.querySelectorAll('.script-element-block').length;")
        payload = self.simulate_external_paste(" Appended snippet.")
        after_count = self.driver.execute_script("return window.editorInstance.pageContainer.querySelectorAll('.script-element-block').length;")
        self.assertEqual(initial_count, after_count)
        self.assertIn("Initial line. Appended snippet.", [e['content'] for e in payload.get('elements', [])])

    # -------------------------------------------------------------------------
    # 19. External paste: ambiguous multiline prose fallback
    # -------------------------------------------------------------------------
    def test_19_external_paste_ambiguous_multiline_fallback(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const action = window.editorInstance.createElementBlock('action', 'Starting paragraph.', heading);
            const ed = action.querySelector('.element-content');
            ed.focus();
            window.editorInstance.setCursorToEnd(ed);
            window.editorInstance.activeElementBlock = action;
        """)
        initial_block_count = self.driver.execute_script("return window.editorInstance.pageContainer.querySelectorAll('.script-element-block').length;")
        raw_prose = """First ordinary prose paragraph.

Second ordinary prose paragraph without screenplay elements."""
        self.simulate_external_paste(raw_prose)
        after_block_count = self.driver.execute_script("return window.editorInstance.pageContainer.querySelectorAll('.script-element-block').length;")
        self.assertEqual(initial_block_count, after_block_count)

    # -------------------------------------------------------------------------
    # 20. External paste: empty block replacement
    # -------------------------------------------------------------------------
    def test_20_external_paste_empty_block_replacement(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw = """JOHN
Dialogue line."""
        payload = self.simulate_external_paste(raw)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(elems[0]['element_type'], 'character')
        self.assertEqual(elems[0]['content'], 'JOHN')

    # -------------------------------------------------------------------------
    # 21. External paste: existing destination text not discarded
    # -------------------------------------------------------------------------
    def test_21_external_paste_existing_text_preservation(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const populatedAction = window.editorInstance.createElementBlock('action', 'Important existing action.', heading);
            const ed = populatedAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = populatedAction;
        """)
        raw = """JOHN
Dialogue line."""
        payload = self.simulate_external_paste(raw)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(elems[0]['element_type'], 'action')
        self.assertEqual(elems[0]['content'], 'Important existing action.')
        self.assertEqual(elems[1]['element_type'], 'character')
        self.assertEqual(elems[1]['content'], 'JOHN')

    # -------------------------------------------------------------------------
    # 22. External paste: multiple scene headings safety
    # -------------------------------------------------------------------------
    def test_22_external_paste_multiple_scene_headings_safety(self):
        self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw = """INT. ROOM - DAY

John sits down.

EXT. STREET - NIGHT

Mary runs away."""
        payload = self.simulate_external_paste(raw)
        heading_count = sum(1 for e in payload.get('elements', []) if e['element_type'] == 'scene_heading')
        self.assertEqual(heading_count, 1)
        action_contents = [e['content'] for e in payload.get('elements', []) if e['element_type'] == 'action']
        self.assertTrue(any('EXT. STREET - NIGHT' in c for c in action_contents))

    # -------------------------------------------------------------------------
    # 23. External paste: sequence markers safety in ordinary vs sequence scenes
    # -------------------------------------------------------------------------
    def test_23_sequence_markers_safety_in_ordinary_and_sequence_scenes(self):
        # Ordinary scene: sequence markers are converted to action
        self.driver.execute_script("""
            window.editorInstance.currentSceneIsSequence = false;
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw_song = """SONG BEGINS

1. INT. AUDITORIUM - DAY

Singers perform.

SONG ENDS"""
        payload_ord = self.simulate_external_paste(raw_song)
        has_seq_marker = self.driver.execute_script("return window.editorInstance.pageContainer.querySelectorAll('.sequence-marker').length > 0;")
        self.assertFalse(has_seq_marker)
        actions = [e['content'] for e in payload_ord.get('elements', []) if e['element_type'] == 'action']
        self.assertTrue(any('SONG BEGINS' in a for a in actions))

        # Sequence scene: sequence markers work as shots
        self.driver.execute_script("""
            window.editorInstance.currentSceneIsSequence = true;
            window.editorInstance.currentSceneSequenceType = 'song';
            const page = window.editorInstance.pageContainer;
            page.innerHTML = '';
            const startMarker = window.editorInstance.createElementBlock('shot', 'SONG BEGINS');
            const emptyAction = window.editorInstance.createElementBlock('action', '', startMarker);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        raw_seq_input = """SONG ENDS"""
        payload_seq = self.simulate_external_paste(raw_seq_input)
        types = [e['element_type'] for e in payload_seq.get('elements', [])]
        self.assertIn('shot', types)

    # -------------------------------------------------------------------------
    # 24. External paste: Undo and Redo operations
    # -------------------------------------------------------------------------
    def test_24_external_paste_undo_redo(self):
        self.driver.execute_script("""
            window.editorInstance.currentSceneIsSequence = false;
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const baselineAction = window.editorInstance.createElementBlock('action', 'Baseline sentence.', heading);
            const ed = baselineAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = baselineAction;
        """)
        pre_payload = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        pre_elements = pre_payload.get('elements', [])

        raw = """JOHN
I arrived safely."""
        pasted_payload = self.simulate_external_paste(raw)
        pasted_elements = pasted_payload.get('elements', [])
        self.assertNotEqual(len(pre_elements), len(pasted_elements))

        # Undo
        self.driver.execute_script("window.editorInstance.undo();")
        after_undo = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        self.assertEqual(len(pre_elements), len(after_undo.get('elements', [])))
        self.assertEqual(pre_elements[0]['content'], after_undo['elements'][0]['content'])

        # Redo
        self.driver.execute_script("window.editorInstance.redo();")
        after_redo = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        self.assertEqual(len(pasted_elements), len(after_redo.get('elements', [])))

    # -------------------------------------------------------------------------
    # 25. Internal semantic copy/paste preservation
    # -------------------------------------------------------------------------
    def test_25_internal_semantic_paste_preservation(self):
        self.driver.execute_script("""
            window.editorInstance.currentSceneIsSequence = false;
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)
        internal_elements = [
            {'type': 'character', 'content': 'VIKRAM'},
            {'type': 'dialogue', 'content': 'Internal clipboard preserved.'}
        ]
        payload = self.simulate_internal_paste(internal_elements)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(len(elems), 2)
        self.assertEqual(elems[0]['element_type'], 'character')
        self.assertEqual(elems[0]['content'], 'VIKRAM')
        self.assertEqual(elems[1]['element_type'], 'dialogue')
        self.assertEqual(elems[1]['content'], 'Internal clipboard preserved.')

    # -------------------------------------------------------------------------
    # 26. External paste autosave persistence and HTTP verification
    # -------------------------------------------------------------------------
    def test_26_external_paste_autosave_persistence(self):
        # 1. Ensure initial editor state is completely settled
        WebDriverWait(self.driver, 10).until(
            lambda drv: drv.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isDirty &&
                       !window.editorInstance.isSaving;
            """),
            message="Initial editor state did not settle before starting autosave test."
        )

        # 2. Configure Malayalam characters and spy on real HTTP fetch saves
        self.driver.execute_script("""
            window.__saveNetworkResponses = [];
            if (!window.__origFetchForTest) {
                window.__origFetchForTest = window.fetch;
                window.fetch = async function(...args) {
                    const response = await window.__origFetchForTest.apply(this, args);
                    const url = args[0] || '';
                    if (typeof url === 'string' && url.includes('/save/')) {
                        try {
                            const clone = response.clone();
                            const data = await clone.json();
                            window.__saveNetworkResponses.push({
                                status: response.status,
                                ok: response.ok,
                                data: data
                            });
                        } catch (err) {
                            window.__saveNetworkResponses.push({
                                status: response.status,
                                ok: response.ok,
                                error: String(err)
                            });
                        }
                    }
                    return response;
                };
            }
            window.editorInstance.characters = ['രാഹുൽ', 'അമ്മ'];

            // Prepare destination: clear non-heading elements and create active empty action
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)

        # 3. Paste representative multiline screenplay text containing Malayalam Unicode
        raw_screenplay = """രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
(ചിരിച്ചുകൊണ്ട്)
ഞാൻ ഉടൻ തിരികെ വരാം."""

        self.simulate_external_paste(raw_screenplay)

        # Confirm paste immediately marked the editor dirty
        is_dirty_immediately = self.driver.execute_script("return window.editorInstance.isDirty;")
        self.assertTrue(is_dirty_immediately, "Editor should be dirty immediately after external paste.")

        # 4. Wait for real autosave HTTP request to complete and editor state to settle
        WebDriverWait(self.driver, 15).until(
            lambda drv: drv.execute_script("""
                return window.__saveNetworkResponses &&
                       window.__saveNetworkResponses.length > 0 &&
                       window.editorInstance &&
                       !window.editorInstance.isDirty &&
                       !window.editorInstance.isSaving;
            """),
            message="Timed out waiting for autosave HTTP request to complete and editor state to settle."
        )

        # 5. Verify the HTTP response indicates success according to the API contract
        responses = self.driver.execute_script("return window.__saveNetworkResponses;")
        self.assertTrue(len(responses) >= 1, "At least one save HTTP response should have been recorded.")
        last_save = responses[-1]
        self.assertEqual(last_save.get('status'), 200, f"Autosave HTTP status should be 200, got {last_save.get('status')}")
        self.assertTrue(last_save.get('ok'), "Autosave response.ok should be True")
        self.assertEqual(last_save.get('data', {}).get('status'), 'ok', "API response status must be 'ok'")
        self.assertEqual(last_save.get('data', {}).get('scene_id'), self.scene.id, "API response scene_id must match")

        # 6. Verify editor dirty/saving state and save badge
        is_dirty = self.driver.execute_script("return window.editorInstance.isDirty;")
        is_saving = self.driver.execute_script("return window.editorInstance.isSaving;")
        save_badge_class = self.driver.execute_script("return window.editorInstance.saveBadge ? window.editorInstance.saveBadge.className : '';")
        save_badge_text = self.driver.execute_script("return window.editorInstance.saveBadge ? window.editorInstance.saveBadge.innerText : '';")

        self.assertFalse(is_dirty, "Editor isDirty should be false after autosave completes.")
        self.assertFalse(is_saving, "Editor isSaving should be false after autosave completes.")
        self.assertIn("saved", save_badge_class, "Save badge should have 'saved' class.")
        self.assertIn("Saved", save_badge_text, "Save badge should show 'Saved' text.")

        # 7. Query saved ScriptElement records from isolated test database
        db_elements = list(ScriptElement.objects.filter(scene=self.scene).order_by('order'))
        editor_payload = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        editor_elements = editor_payload.get('elements', [])

        # 8. Confirm exact element types, content, and order match between DB and editor
        self.assertEqual(len(db_elements), len(editor_elements), "Database element count must match editor element count.")
        self.assertEqual(len(db_elements), 6, "Expected 6 elements: scene_heading + 5 pasted screenplay blocks.")

        for db_elem, ed_elem in zip(db_elements, editor_elements):
            self.assertEqual(db_elem.element_type, ed_elem['element_type'])
            self.assertEqual(db_elem.content, ed_elem['content'])
            self.assertEqual(db_elem.order, ed_elem['order'])

        # Detailed assertions on the persisted content
        self.assertEqual(db_elements[0].element_type, 'scene_heading')
        self.assertEqual(db_elements[0].content, 'INT. TEST STUDIO - DAY')

        self.assertEqual(db_elements[1].element_type, 'character')
        self.assertEqual(db_elements[1].content, 'രാഹുൽ')

        self.assertEqual(db_elements[2].element_type, 'dialogue')
        self.assertEqual(db_elements[2].content, 'നീ എവിടെ പോകുന്നു?')

        self.assertEqual(db_elements[3].element_type, 'character')
        self.assertEqual(db_elements[3].content, 'അമ്മ')

        self.assertEqual(db_elements[4].element_type, 'parenthetical')
        self.assertEqual(db_elements[4].content, '(ചിരിച്ചുകൊണ്ട്)')

        self.assertEqual(db_elements[5].element_type, 'dialogue')
        self.assertEqual(db_elements[5].content, 'ഞാൻ ഉടൻ തിരികെ വരാം.')

        # 9. Verify Malayalam Unicode preservation
        self.assertEqual(db_elements[1].content, 'രാഹുൽ')
        self.assertEqual(db_elements[2].content, 'നീ എവിടെ പോകുന്നു?')
        self.assertEqual(db_elements[4].content, '(ചിരിച്ചുകൊണ്ട്)')
        self.assertEqual(db_elements[5].content, 'ഞാൻ ഉടൻ തിരികെ വരാം.')

    # -------------------------------------------------------------------------
    # 27. Malayalam character names not registered in known-character list
    # -------------------------------------------------------------------------
    def test_27_unregistered_malayalam_character_names(self):
        raw = """രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
ഞാൻ ഉടൻ തിരികെ വരാം."""
        # Explicitly pass empty list for custom characters to ensure no pre-registered lookup
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'രാഹുൽ'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'നീ എവിടെ പോകുന്നു?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': 'ഞാൻ ഉടൻ തിരികെ വരാം.'})

    # -------------------------------------------------------------------------
    # 28. English character names (Title Case & ALL-CAPS without pre-registration)
    # -------------------------------------------------------------------------
    def test_28_english_character_names_unregistered(self):
        raw = """John
Are you ready?

MARY
Almost ready."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'John'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'Are you ready?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'MARY'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': 'Almost ready.'})

    # -------------------------------------------------------------------------
    # 29. Dialogue with inconsistent blank lines
    # -------------------------------------------------------------------------
    def test_29_dialogue_with_inconsistent_blank_lines(self):
        raw = """രാഹുൽ

നീ എവിടെ പോകുന്നു?

അമ്മ

(ചിരിച്ചുകൊണ്ട്)

ഞാൻ ഉടൻ തിരികെ വരാം."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 5)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'രാഹുൽ'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'നീ എവിടെ പോകുന്നു?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[3], {'type': 'parenthetical', 'content': '(ചിരിച്ചുകൊണ്ട്)'})
        self.assertEqual(elements[4], {'type': 'dialogue', 'content': 'ഞാൻ ഉടൻ തിരികെ വരാം.'})

    # -------------------------------------------------------------------------
    # 30. Parentheticals between dialogue lines & bare parentheticals
    # -------------------------------------------------------------------------
    def test_30_parentheticals_and_bare_parentheticals(self):
        raw = """അമ്മ
ചിരിച്ചുകൊണ്ട്
നീ പേടിക്കേണ്ട.
(പതുക്കെ)
ഞാൻ കൂടെയുണ്ട്."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 5)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[1], {'type': 'parenthetical', 'content': '(ചിരിച്ചുകൊണ്ട്)'})
        self.assertEqual(elements[2], {'type': 'dialogue', 'content': 'നീ പേടിക്കേണ്ട.'})
        self.assertEqual(elements[3], {'type': 'parenthetical', 'content': '(പതുക്കെ)'})
        self.assertEqual(elements[4], {'type': 'dialogue', 'content': 'ഞാൻ കൂടെയുണ്ട്.'})

    # -------------------------------------------------------------------------
    # 31. Action before and after dialogue
    # -------------------------------------------------------------------------
    def test_31_action_before_and_after_dialogue(self):
        raw = """INT. KITCHEN - DAY

അടുക്കളയിൽ പാത്രങ്ങളുടെ ശബ്ദം കേൾക്കാം. ജനലിലൂടെ വെളിച്ചം വീഴുന്നു.

രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
ഞാൻ ഉടൻ തിരികെ വരാം.

അവൾ പതുക്കെ വാതിലടച്ച് പുറത്തേക്ക് നടന്നു."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 7)
        self.assertEqual(elements[0]['type'], 'scene_heading')
        self.assertEqual(elements[0]['content'], 'INT. KITCHEN - DAY')
        self.assertEqual(elements[1]['type'], 'action')
        self.assertIn('അടുക്കളയിൽ പാത്രങ്ങളുടെ ശബ്ദം', elements[1]['content'])
        self.assertEqual(elements[2], {'type': 'character', 'content': 'രാഹുൽ'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': 'നീ എവിടെ പോകുന്നു?'})
        self.assertEqual(elements[4], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[5], {'type': 'dialogue', 'content': 'ഞാൻ ഉടൻ തിരികെ വരാം.'})
        self.assertEqual(elements[6]['type'], 'action')
        self.assertIn('വാതിലടച്ച് പുറത്തേക്ക്', elements[6]['content'])

    # -------------------------------------------------------------------------
    # 32. Mixed Malayalam screenplay through actual handlePaste() workflow
    # -------------------------------------------------------------------------
    def test_32_handle_paste_mixed_malayalam_screenplay(self):
        # Clear canvas to empty action block and ensure characters list is empty
        self.driver.execute_script("""
            window.editorInstance.characters = [];
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)

        raw = """അയാൾ മുറിയിലേക്ക് കടന്നുവരുന്നു.

രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
(ചിരിച്ചുകൊണ്ട്)
ഞാൻ ഉടൻ തിരികെ വരാം.

അവൾ പതുക്കെ പുറത്തേക്ക് നടന്നു."""

        payload = self.simulate_external_paste(raw)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(len(elems), 7)
        self.assertEqual(elems[0]['element_type'], 'action')
        self.assertEqual(elems[0]['content'], 'അയാൾ മുറിയിലേക്ക് കടന്നുവരുന്നു.')
        self.assertEqual(elems[1]['element_type'], 'character')
        self.assertEqual(elems[1]['content'], 'രാഹുൽ')
        self.assertEqual(elems[2]['element_type'], 'dialogue')
        self.assertEqual(elems[2]['content'], 'നീ എവിടെ പോകുന്നു?')
        self.assertEqual(elems[3]['element_type'], 'character')
        self.assertEqual(elems[3]['content'], 'അമ്മ')
        self.assertEqual(elems[4]['element_type'], 'parenthetical')
        self.assertEqual(elems[4]['content'], '(ചിരിച്ചുകൊണ്ട്)')
        self.assertEqual(elems[5]['element_type'], 'dialogue')
        self.assertEqual(elems[5]['content'], 'ഞാൻ ഉടൻ തിരികെ വരാം.')
        self.assertEqual(elems[6]['element_type'], 'action')
        self.assertEqual(elems[6]['content'], 'അവൾ പതുക്കെ പുറത്തേക്ക് നടന്നു.')

    # -------------------------------------------------------------------------
    # 33. Regression: script that previously became entirely Action
    # -------------------------------------------------------------------------
    def test_33_prevents_all_action_misclassification(self):
        # When unregistered Malayalam script was pasted, previously all became 1 Action block
        self.driver.execute_script("""
            window.editorInstance.characters = [];
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)

        raw = """വിക്രം
ഇത് എപ്പോഴാണ് തുടങ്ങിയത്?

ഡോക്ടർ
കുറച്ചു ദിവസങ്ങൾക്ക് മുൻപ്."""

        payload = self.simulate_external_paste(raw)
        elems = [e for e in payload.get('elements', []) if e['element_type'] != 'scene_heading']
        types = [e['element_type'] for e in elems]
        self.assertIn('character', types, "Pasted screenplay must contain character elements, not all action.")
        self.assertIn('dialogue', types, "Pasted screenplay must contain dialogue elements, not all action.")
        self.assertEqual(len(elems), 4)

    # -------------------------------------------------------------------------
    # 34. Character elements rendered with existing bold styling
    # -------------------------------------------------------------------------
    def test_34_character_elements_have_bold_styling(self):
        self.driver.execute_script("""
            window.editorInstance.characters = [];
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)

        raw = """മോഹൻലാൽ
ഞാൻ വരുന്നു."""

        self.simulate_external_paste(raw)
        font_weight = self.driver.execute_script("""
            const charBlock = window.editorInstance.pageContainer.querySelector('.script-element-block[data-type="character"] .element-content');
            if (!charBlock) return null;
            return window.getComputedStyle(charBlock).fontWeight;
        """)
        self.assertIn(str(font_weight), ['700', 'bold'], "Character element must receive font-weight: 700 / bold styling.")

    # -------------------------------------------------------------------------
    # 35. Inline character cues with colon
    # -------------------------------------------------------------------------
    def test_35_inline_character_cue_with_colon(self):
        raw = """രാഹുൽ: നീ എവിടെ പോകുന്നു?
അമ്മ: ഞാൻ ഉടൻ തിരികെ വരാം."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 4)
        self.assertEqual(elements[0], {'type': 'character', 'content': 'രാഹുൽ'})
        self.assertEqual(elements[1], {'type': 'dialogue', 'content': 'നീ എവിടെ പോകുന്നു?'})
        self.assertEqual(elements[2], {'type': 'character', 'content': 'അമ്മ'})
        self.assertEqual(elements[3], {'type': 'dialogue', 'content': 'ഞാൻ ഉടൻ തിരികെ വരാം.'})

    # -------------------------------------------------------------------------
    # 36. Ordinary prose remains action without false character classification
    # -------------------------------------------------------------------------
    def test_36_ordinary_prose_remains_action(self):
        raw = """Meeting agenda for tomorrow:
Review script progress with director.
Prepare call sheet for shoot."""
        elements = self.call_parser(raw, [])
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]['type'], 'action')
        self.assertIn('Meeting agenda for tomorrow:', elements[0]['content'])

    # -------------------------------------------------------------------------
    # 37. Undo/redo and persistence for corrected structured paste
    # -------------------------------------------------------------------------
    def test_37_undo_redo_and_persistence_corrected_paste(self):
        self.driver.execute_script("""
            window.editorInstance.characters = [];
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            const emptyAction = window.editorInstance.createElementBlock('action', '', heading);
            const ed = emptyAction.querySelector('.element-content');
            ed.focus();
            window.editorInstance.activeElementBlock = emptyAction;
        """)

        raw = """രാഹുൽ
നീ എവിടെ പോകുന്നു?

അമ്മ
ഞാൻ ഉടൻ വരാം."""

        self.simulate_external_paste(raw)

        # 1. Undo
        self.driver.execute_script("window.editorInstance.undo();")
        payload_after_undo = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        elems_undo = [e for e in payload_after_undo.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(len(elems_undo), 1)
        self.assertEqual(elems_undo[0]['element_type'], 'action')

        # 2. Redo
        self.driver.execute_script("window.editorInstance.redo();")
        payload_after_redo = self.driver.execute_script("return window.editorInstance.extractScenePayload();")
        elems_redo = [e for e in payload_after_redo.get('elements', []) if e['element_type'] != 'scene_heading']
        self.assertEqual(len(elems_redo), 4)
        self.assertEqual(elems_redo[0]['element_type'], 'character')
        self.assertEqual(elems_redo[1]['element_type'], 'dialogue')
        self.assertEqual(elems_redo[2]['element_type'], 'character')
        self.assertEqual(elems_redo[3]['element_type'], 'dialogue')

    # -------------------------------------------------------------------------
    # 38. Batch 2D.3 Bug A: Final Action after Dialogue remains separate Action
    # -------------------------------------------------------------------------
    def test_38_final_action_after_dialogue_remains_action(self):
        # 1. English with blank line
        raw1 = "CHARACTER\n\nDialogue line.\n\nThe character walks toward the door."
        elems1 = self.call_parser(raw1, [])
        types1 = [e['type'] for e in elems1]
        self.assertEqual(types1, ['character', 'dialogue', 'action'])
        self.assertEqual(elems1[2]['content'], 'The character walks toward the door.')

        # 2. English without blank line
        raw2 = "CHARACTER\nDialogue line.\nThe character walks toward the door."
        elems2 = self.call_parser(raw2, [])
        types2 = [e['type'] for e in elems2]
        self.assertEqual(types2, ['character', 'dialogue', 'action'])
        self.assertEqual(elems2[2]['content'], 'The character walks toward the door.')

        # 3. Malayalam with blank line
        raw3 = "CHARACTER\n\nDialogue line.\n\nഅവൻ പതുക്കെ വാതിലിനടുത്തേക്ക് നടക്കുന്നു."
        elems3 = self.call_parser(raw3, [])
        types3 = [e['type'] for e in elems3]
        self.assertEqual(types3, ['character', 'dialogue', 'action'])
        self.assertEqual(elems3[2]['content'], 'അവൻ പതുക്കെ വാതിലിനടുത്തേക്ക് നടക്കുന്നു.')

        # 4. Malayalam without blank line
        raw4 = "CHARACTER\nDialogue line.\nഅവൻ പതുക്കെ വാതിലിനടുത്തേക്ക് നടക്കുന്നു."
        elems4 = self.call_parser(raw4, [])
        types4 = [e['type'] for e in elems4]
        self.assertEqual(types4, ['character', 'dialogue', 'action'])
        self.assertEqual(elems4[2]['content'], 'അവൻ പതുക്കെ വാതിലിനടുത്തേക്ക് നടക്കുന്നു.')

    # -------------------------------------------------------------------------
    # 39. Batch 2D.3 Bug B: Parenthetical bracket grouping and character extensions
    # -------------------------------------------------------------------------
    def test_39_parenthetical_bracket_grouping(self):
        # 1. English parenthetical on same line as character
        raw1 = "RAHUL (quietly)\nI don't know."
        elems1 = self.call_parser(raw1, [])
        types1 = [e['type'] for e in elems1]
        self.assertEqual(types1, ['character', 'parenthetical', 'dialogue'])
        self.assertEqual(elems1[0]['content'], 'RAHUL')
        self.assertEqual(elems1[1]['content'], '(quietly)')

        # 2. Malayalam square bracket on same line as character
        raw2 = "രാഹുൽ [പതുക്കെ]\nഎനിക്ക് അറിയില്ല."
        elems2 = self.call_parser(raw2, [])
        types2 = [e['type'] for e in elems2]
        self.assertEqual(types2, ['character', 'parenthetical', 'dialogue'])
        self.assertEqual(elems2[0]['content'], 'രാഹുൽ')
        self.assertEqual(elems2[1]['content'], '(പതുക്കെ)')

        # 3. Square bracket on separate line
        raw3 = "രാഹുൽ\n[പതുക്കെ]\n\nഎനിക്ക് അറിയില്ല."
        elems3 = self.call_parser(raw3, [])
        types3 = [e['type'] for e in elems3]
        self.assertEqual(types3, ['character', 'parenthetical', 'dialogue'])
        self.assertEqual(elems3[1]['content'], '(പതുക്കെ)')

        # 4. Character extension preserved on character element
        raw4 = "RAHUL (V.O.)\nI don't know."
        elems4 = self.call_parser(raw4, [])
        types4 = [e['type'] for e in elems4]
        self.assertEqual(types4, ['character', 'dialogue'])
        self.assertEqual(elems4[0]['content'], 'RAHUL (V.O.)')

    # -------------------------------------------------------------------------
    # 40. Batch 2D.3 Bug C: Multiple montage labels (Second Montage) and state
    # -------------------------------------------------------------------------
    def test_40_multiple_montage_labels_and_state(self):
        res = self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());
            
            const m1 = window.editorInstance.createElementBlock('shot', 'MONTAGE BEGINS', heading);
            const a1 = window.editorInstance.createElementBlock('action', 'First montage action.', m1);
            const e1 = window.editorInstance.createElementBlock('shot', 'MONTAGE ENDS', a1);
            const mid = window.editorInstance.createElementBlock('action', 'Between montages.', e1);
            const m2 = window.editorInstance.createElementBlock('shot', 'MONTAGE BEGINS', mid);
            const a2 = window.editorInstance.createElementBlock('action', 'Second montage action.', m2);
            const e2 = window.editorInstance.createElementBlock('shot', 'MONTAGE ENDS', a2);
            
            window.editorInstance.renumberSequenceShots();
            
            const stateDuringM2 = window.editorInstance.detectCurrentSequenceState(a2);
            const stateDuringMid = window.editorInstance.detectCurrentSequenceState(mid);
            
            return {
                m1Label: m1.dataset.sequenceLabel,
                m1Tag: m1.querySelector('.element-type-tag').textContent,
                m2Label: m2.dataset.sequenceLabel,
                m2Tag: m2.querySelector('.element-type-tag').textContent,
                m2InSequence: stateDuringM2.inSequence,
                m2HasEnded: stateDuringM2.hasEnded,
                midInSequence: stateDuringMid.inSequence,
                midHasEnded: stateDuringMid.hasEnded
            };
        """)
        self.assertEqual(res['m1Label'], 'First Montage')
        self.assertEqual(res['m1Tag'], 'First Montage')
        self.assertEqual(res['m2Label'], 'Second Montage')
        self.assertEqual(res['m2Tag'], 'Second Montage')
        self.assertTrue(res['m2InSequence'])
        self.assertFalse(res['m2HasEnded'])
        self.assertFalse(res['midInSequence'])
        self.assertTrue(res['midHasEnded'])

    # -------------------------------------------------------------------------
    # 41. Batch 2D.3 Bug D: Enter key cursor split behavior (12 cases)
    # -------------------------------------------------------------------------
    def test_42_external_paste_failure_recovery_preserves_destination_block(self):
        res = self.driver.execute_script("""
            const page = window.editorInstance.pageContainer;
            const heading = page.querySelector('.script-element-block[data-type="scene_heading"]');
            page.querySelectorAll('.script-element-block:not([data-type="scene_heading"])').forEach(b => b.remove());

            const act1 = window.editorInstance.createElementBlock('action', 'Action line 1.', heading);
            const emptyAction = window.editorInstance.createElementBlock('action', '', act1);
            const act2 = window.editorInstance.createElementBlock('action', 'Action line 2.', emptyAction);

            const emptyEd = emptyAction.querySelector('.element-content');
            emptyEd.focus();
            window.editorInstance.activeElementBlock = emptyAction;

            // Inject temporary fault into calculateLiveStats during paste
            let faultTriggered = false;
            let injectFault = true;
            const origLiveStats = window.editorInstance.calculateLiveStats;
            window.editorInstance.calculateLiveStats = function() {
                if (injectFault) {
                    faultTriggered = true;
                    injectFault = false;
                    throw new Error("Simulated post-removal exception during paste pipeline");
                }
                return origLiveStats.call(this);
            };

            const pasteText = "JOHN\\nHello there!\\n\\nMARY\\nGood morning.";
            const event = new Event('paste', { bubbles: true, cancelable: true });
            event.clipboardData = {
                getData: function(format) {
                    if (format === 'text/plain') return pasteText;
                    return '';
                },
                types: ['text/plain']
            };

            try {
                window.editorInstance.handlePaste(event);
            } finally {
                window.editorInstance.calculateLiveStats = origLiveStats;
            }

            const allBlocks = Array.from(page.querySelectorAll('.script-element-block'));
            const blocksData = allBlocks.map(b => ({
                type: b.dataset.type,
                text: b.querySelector('.element-content') ? b.querySelector('.element-content').innerText.trim() : ''
            }));

            return {
                faultTriggered: faultTriggered,
                blocksData: blocksData,
                destStillInDom: page.contains(emptyAction),
                destOrder: allBlocks.indexOf(emptyAction),
                activeBlockInDom: window.editorInstance.activeElementBlock ? page.contains(window.editorInstance.activeElementBlock) : false,
                activeBlockIsDest: window.editorInstance.activeElementBlock === emptyAction,
                totalCount: allBlocks.length,
                hasCharacterOrDialogue: blocksData.some(b => b.type === 'character' || b.type === 'dialogue')
            };
        """)

        self.assertTrue(res['faultTriggered'], "Injected fault must have triggered")
        self.assertTrue(res['destStillInDom'], "Original destination block must remain in DOM after recovery")
        self.assertEqual(res['destOrder'], 2, "Destination block must retain its exact position (order 2, between act1 and act2)")
        self.assertFalse(res['hasCharacterOrDialogue'], "No partially inserted screenplay blocks must remain")
        self.assertTrue(res['activeBlockInDom'], "Active block must be in DOM")
        self.assertTrue(res['activeBlockIsDest'], "Active block must be the restored destination block")
        self.assertEqual(res['totalCount'], 4, "Total blocks must be 4: heading, act1, destination block, act2")

    # -------------------------------------------------------------------------
    # 43. Dialogue selection replacement on Enter
    # -------------------------------------------------------------------------
