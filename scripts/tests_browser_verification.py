
import os
import sys
import time

from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.models import Script, Scene, ScriptElement


# Get the active Django user model
User = get_user_model()

ARTIFACTS_DIR = r"C:\Users\rasiz\.gemini\antigravity-ide\brain\d61e8d4b-7e73-4dab-8ca8-62e78c38bb51"
CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe"


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
class KadhaScriptBrowserUXVerification(StaticLiveServerTestCase):
    """
    Automated headless Chrome Selenium verification covering:
    1. Scene Order contrast (selected main & sub-scene text readability)
    2. Scene Order dropdown action menus for main and sub-scenes
    3. Hierarchy & click isolation (dropdown click does not navigate)
    4. Mobile viewports (390x844, 375x812, 412x915) & desktop (1280x800)
    5. Dashboard screenplay rename (modal, validation, instant DOM update)
    6. Dashboard screenplay delete (confirmation modal, cancel, delete & count update)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="ux_client_user",
            email="ux_client_user@kadhascript.com",
            password="password123"
        )

    def setUp(self):
        # Create screenplay with main scenes and sub-scenes
        self.script1 = Script.objects.create(
            user=self.user,
            title="നീലവെളിച്ചം (Blue Light)",
            script_type="Feature Film",
            language="Malayalam"
        )
        self.sc1 = Scene.objects.create(
            script=self.script1,
            scene_number=1,
            heading="INT. OLD MANSION - NIGHT",
            order=0
        )
        ScriptElement.objects.create(scene=self.sc1, element_type="scene_heading", content="INT. OLD MANSION - NIGHT", order=0)
        ScriptElement.objects.create(scene=self.sc1, element_type="action", content="ഒരു പഴയ മാളിക.", order=1)

        self.sc2 = Scene.objects.create(
            script=self.script1,
            scene_number=2,
            heading="EXT. GARDEN - NIGHT",
            order=1
        )
        ScriptElement.objects.create(scene=self.sc2, element_type="scene_heading", content="EXT. GARDEN - NIGHT", order=0)

        self.sub2a = Scene.objects.create(
            script=self.script1,
            parent_scene=self.sc2,
            scene_number=2,
            heading="WELL AREA",
            order=2
        )
        ScriptElement.objects.create(scene=self.sub2a, element_type="scene_heading", content="WELL AREA", order=0)

        self.script2_to_delete = Script.objects.create(
            user=self.user,
            title="കളിത്തീവണ്ടി (Toy Train)",
            script_type="Short Film",
            language="Malayalam"
        )
        Scene.objects.create(script=self.script2_to_delete, scene_number=1, heading="INT. ROOM - DAY", order=0)

    def get_driver(self):
        opts = ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-cache")
        opts.add_argument("--incognito")
        opts.add_argument("--window-size=1280,800")
        if os.path.exists(CHROMEDRIVER_PATH):
            service = ChromeService(executable_path=CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
        return driver

    def login_user(self, driver):
        driver.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "email")))
        driver.find_element(By.NAME, "email").send_keys("ux_client_user@kadhascript.com")
        driver.find_element(By.NAME, "password").send_keys("password123")
        driver.find_element(By.NAME, "password").submit()
        WebDriverWait(driver, 10).until(EC.url_contains("/dashboard/"))

    def test_browser_ux_verification(self):
        driver = self.get_driver()
        try:
            self.login_user(driver)

            # ========================================================
            # 1. DASHBOARD VERIFICATION (Rename & Delete)
            # ========================================================
            driver.get(f"{self.live_server_url}/dashboard/")
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "renameScriptModal")))
            driver.save_screenshot(os.path.join(ARTIFACTS_DIR, "dashboard_rendered.png"))

            # Test Rename Screenplay
            rename_btn = driver.find_element(By.CSS_SELECTOR, f"button.btn-action-rename-script[data-id='{self.script1.id}']")
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", rename_btn)
            time.sleep(0.5)

            rename_input = driver.find_element(By.ID, "renameScriptTitleInput")
            rename_input.clear()
            rename_input.send_keys("നീലവെളിച്ചം - അന്തിമ പതിപ്പ് (Final Cut)")
            save_rename_btn = driver.find_element(By.ID, "btnSubmitRenameScript")
            driver.execute_script("arguments[0].click();", save_rename_btn)
            time.sleep(1)

            # Confirm immediate DOM update without full reload
            title_el = driver.find_element(By.ID, f"script-title-{self.script1.id}")
            self.assertEqual(title_el.text.strip(), "നീലവെളിച്ചം - അന്തിമ പതിപ്പ് (Final Cut)")

            # Verify database preserved new title
            self.script1.refresh_from_db()
            self.assertEqual(self.script1.title, "നീലവെളിച്ചം - അന്തിമ പതിപ്പ് (Final Cut)")

            # Test Delete Screenplay (Modal confirmation + Cancel)
            del_btn = driver.find_element(By.CSS_SELECTOR, f"button.btn-action-delete-script[data-id='{self.script2_to_delete.id}']")
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", del_btn)
            time.sleep(0.5)

            del_modal = driver.find_element(By.ID, "deleteScriptModal")
            self.assertTrue(del_modal.is_displayed())
            self.assertIn("കളിത്തീവണ്ടി (Toy Train)", del_modal.text)
            self.assertIn("This screenplay will be moved to Trash and can be restored.",del_modal.text)

            # Cancel first
            cancel_btn = driver.find_element(By.ID, "btnCancelDeleteScript")
            driver.execute_script("arguments[0].click();", cancel_btn)
            time.sleep(0.5)
            self.assertTrue(Script.objects.filter(id=self.script2_to_delete.id).exists())

            # Re-open and confirm Delete
            driver.execute_script("arguments[0].click();", del_btn)
            time.sleep(0.5)
            confirm_del_btn = driver.find_element(By.ID, "btnConfirmDeleteScript")
            driver.execute_script("arguments[0].click();", confirm_del_btn)
            time.sleep(1)

            # Confirm item removed from the active dashboard and moved to Trash.
            del_items = driver.find_elements(
            By.ID, f"project-item-{self.script2_to_delete.id}"
            )
            self.assertEqual(
            len(del_items), 0,
            "The deleted screenplay should disappear from the active dashboard."
            )

            deleted_script = Script.objects.get(id=self.script2_to_delete.id)
            self.assertTrue(
            deleted_script.is_deleted,
            "The screenplay should be moved to Trash, not permanently deleted."
             )

            # ========================================================
            # 2. EDITOR SCENE ORDER VERIFICATION ACROSS VIEWPORTS
            # ========================================================
            viewports = [
                (1280, 800, "desktop_1280x800"),
                (390, 844, "mobile_390x844"),
                (375, 812, "mobile_375x812"),
                (412, 915, "mobile_412x915"),
            ]

            for width, height, vp_name in viewports:
                driver.set_window_size(width, height)
                driver.get(f"{self.live_server_url}/scripts/{self.script1.id}/editor/")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "screenplayEditor")))
                time.sleep(1)

                is_mobile = width < 992
                list_selector = "#offcanvasScenesList" if is_mobile else "#scenesList"

                # If mobile, open the offcanvas drawer
                if is_mobile:
                    scenes_btn = driver.find_element(By.ID, "btnNavScenes")
                    driver.execute_script("arguments[0].click();", scenes_btn)
                    time.sleep(1)

                scene_list_el = driver.find_element(By.CSS_SELECTOR, list_selector)
                self.assertTrue(scene_list_el.is_displayed())

                # Select Scene 1
                scene1_item = scene_list_el.find_element(By.CSS_SELECTOR, f".scene-item[data-id='{self.sc1.id}']")
                nav1 = scene1_item.find_element(By.CLASS_NAME, "scene-nav-item")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", nav1)
                time.sleep(0.5)

                scene1_item = scene_list_el.find_element(By.CSS_SELECTOR, f".scene-item[data-id='{self.sc1.id}']")
                self.assertIn("active", scene1_item.get_attribute("class"))
                bg_color = scene1_item.value_of_css_property("background-color")
                num_el = scene1_item.find_element(By.CLASS_NAME, "scene-nav-number")
                loc_el = scene1_item.find_element(By.CLASS_NAME, "scene-nav-location")
                num_color = num_el.value_of_css_property("color")
                loc_color = loc_el.value_of_css_property("color")

                # The background must NOT be white rgb(255, 255, 255) with white text!
                self.assertNotEqual(bg_color, "rgba(255, 255, 255, 1)")
                self.assertNotEqual(num_color, "rgba(255, 255, 255, 1)")
                self.assertNotEqual(loc_color, "rgba(255, 255, 255, 1)")

                # Select Sub-Scene
                sub2a_item = scene_list_el.find_element(By.CSS_SELECTOR, f".sub-scene-item[data-id='{self.sub2a.id}']")
                sub_nav = sub2a_item.find_element(By.CLASS_NAME, "scene-nav-item")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", sub_nav)
                time.sleep(0.5)
                sub2a_item = scene_list_el.find_element(By.CSS_SELECTOR, f".sub-scene-item[data-id='{self.sub2a.id}']")
                self.assertIn("active", sub2a_item.get_attribute("class"))
                sub_bg_color = sub2a_item.value_of_css_property("background-color")
                sub_loc_color = sub2a_item.find_element(By.CLASS_NAME, "scene-nav-location").value_of_css_property("color")
                self.assertNotEqual(sub_bg_color, "rgba(255, 255, 255, 1)")
                self.assertNotEqual(sub_loc_color, "rgba(255, 255, 255, 1)")

                # Verify Action Menu for Main Scene
                s1_action_btn = scene1_item.find_element(By.CLASS_NAME, "scene-action-btn")
                btn_h = s1_action_btn.size['height']
                btn_w = s1_action_btn.size['width']
                self.assertGreaterEqual(btn_h, 30)
                self.assertGreaterEqual(btn_w, 30)

                # Click dropdown button - confirm it opens menu without navigating away
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", s1_action_btn)
                time.sleep(0.5)
                menu = scene1_item.find_element(By.CLASS_NAME, "dropdown-menu")
                self.assertIn("show", menu.get_attribute("class"))

                # Verify menu items for main scene
                menu_text = menu.get_attribute('textContent')
                self.assertIn("Insert Scene Before", menu_text)
                self.assertIn("Insert Scene After", menu_text)
                self.assertIn("Add Sub-Scene", menu_text)
                self.assertIn("Duplicate", menu_text)
                self.assertIn("Copy Full Scene", menu_text)
                self.assertIn("Move Up", menu_text)
                self.assertIn("Move Down", menu_text)
                self.assertIn("Move to Trash", menu_text)

                # Verify Sub-Scene Action Menu
                sub_action_btn = sub2a_item.find_element(By.CLASS_NAME, "scene-action-btn")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", sub_action_btn)
                time.sleep(0.5)
                sub_menu = sub2a_item.find_element(By.CLASS_NAME, "dropdown-menu")
                self.assertIn("show", sub_menu.get_attribute("class"))
                sub_menu_text = sub_menu.get_attribute('textContent')
                self.assertIn("Insert Sub-Scene Before", sub_menu_text)
                self.assertIn("Insert Sub-Scene After", sub_menu_text)
                self.assertIn("Add Sub-Scene", sub_menu_text)
                self.assertIn("Duplicate", sub_menu_text)
                self.assertIn("Copy Full Scene", sub_menu_text)
                self.assertIn("Move Up", sub_menu_text)
                self.assertIn("Move Down", sub_menu_text)
                self.assertIn("Move to Trash", sub_menu_text)


                # ========================================================
                # FEATURE 2 & 3: COPY FULL SCENE (Menu)
                # ========================================================
                copy_sub_btn = sub_menu.find_element(
                    By.CLASS_NAME, "btn-action-copy-scene"
                )
                driver.execute_script(
                    "arguments[0].click();", copy_sub_btn
                )
                time.sleep(0.5)

                # Verify scene navigation was NOT triggered.
                curr_sub = scene_list_el.find_element(
                    By.CSS_SELECTOR,
                    f".sub-scene-item[data-id='{self.sub2a.id}']"
                )
                self.assertIn(
                    "active", curr_sub.get_attribute("class")
                )

                # Verify the full-scene semantic clipboard payload.
                sub_payload = driver.execute_script("""
                    const ed = window.editorInstance;
                    return ed ? ed.lastCopiedPayload : null;
                """)

                self.assertIsNotNone(
                    sub_payload,
                    "Copy Full Scene should generate a clipboard payload."
                )
                self.assertTrue(sub_payload.get("is_full_scene"))
                self.assertEqual(sub_payload.get("version"), "1.0")
                self.assertEqual(sub_payload.get("source"), "kadhascript")
                self.assertEqual(sub_payload.get("scene_id"), self.sub2a.id)
                self.assertIn("elements", sub_payload)

                # Copy Full Scene is currently available through the
                # scene and sub-scene action menus.
                # The historical pinned toolbar button is no longer rendered.

                # Close mobile offcanvas if open.
                if is_mobile:
                    close_btn = driver.find_elements(
                        By.CSS_SELECTOR, "#scenesOffcanvas .btn-close"
                    )
                    if close_btn and close_btn[0].is_displayed():
                        driver.execute_script(
                            "arguments[0].click();", close_btn[0]
                        )
                        time.sleep(0.5)

                # ========================================================
                # FEATURE 5: REMOVE AUTOMATIC EDIT MODE FOCUS
                # ========================================================
                editor_root = driver.find_element(
                    By.ID, "screenplayEditor"
                )
                self.assertEqual(
                    editor_root.get_attribute("data-mode"), "read"
                )

                driver.execute_script(
                    "if (document.activeElement) document.activeElement.blur();"
                )
                btn_edit = driver.find_element(
                    By.ID, "btnEnterEditMode"
                )
                driver.execute_script(
                    "arguments[0].click();", btn_edit
                )
                WebDriverWait(driver, 10).until(
                    lambda d: editor_root.get_attribute("data-mode") == "edit"
                )

                self.assertEqual(
                    editor_root.get_attribute("data-mode"), "edit"
                )


                # ========================================================
                # FEATURE 1 & 2: SEMANTIC SCREENPLAY COPY & PASTE
                # ========================================================
                # Paste custom semantic blocks including Malayalam Unicode and Parenthetical
                paste_payload = {
                    "version": "1.0",
                    "source": "kadhascript",
                    "elements": [
                        {"type": "character", "content": "റഹീം (RAHEEM)"},
                        {"type": "parenthetical", "content": "(പുഞ്ചിരിയോടെ)"},
                        {"type": "dialogue", "content": "എല്ലാം ശരിയാകും."},
                        {"type": "action", "content": "റഹീം കാപ്പികുടിച്ച് പുറത്തേക്ക് നടക്കുന്നു."}
                    ]
                }
                driver.execute_script("""
                    const payload = arguments[0];
                    const jsonStr = JSON.stringify(payload);
                    const dt = new DataTransfer();
                    dt.setData('application/x-kadhascript-elements', jsonStr);
                    dt.setData('text/plain', "റഹീം (RAHEEM)\\n(പുഞ്ചിരിയോടെ)\\nഎല്ലാം ശരിയാകും.\\n\\nറഹീം കാപ്പികുടിച്ച് പുറത്തേക്ക് നടക്കുന്നു.");
                    const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                    const target = document.getElementById('screenplayPage');
                    target.dispatchEvent(pasteEvt);
                """, paste_payload)
                time.sleep(0.5)

                # Verify elements in DOM retain their semantic types
                dom_elements = driver.execute_script("""
                    return Array.from(document.querySelectorAll('#screenplayPage .script-element-block')).map(b => ({
                        type: b.getAttribute('data-type'),
                        content: (b.querySelector('.element-content') ? b.querySelector('.element-content').innerText.trim() : '')
                    }));
                """)
                types = [e['type'] for e in dom_elements]
                self.assertIn('character', types)
                self.assertIn('parenthetical', types)
                self.assertIn('dialogue', types)
                self.assertIn('action', types)

                # Verify Malayalam Unicode preservation and parenthetical single wrapping
                char_elem = next(e for e in dom_elements if e['type'] == 'character' and 'റഹീം' in e['content'])
                self.assertEqual(char_elem['content'], 'റഹീം (RAHEEM)')

                paren_elem = next(e for e in dom_elements if e['type'] == 'parenthetical')
                self.assertEqual(paren_elem['content'], '(പുഞ്ചിരിയോടെ)')
                self.assertNotIn('((', paren_elem['content'])

                diag_elem = next(
                    e for e in dom_elements
                    if e['type'] == 'dialogue'
                    and e['content'] == paste_payload["elements"][2]["content"]
                )

                self.assertEqual(
                    diag_elem['content'],
                    paste_payload["elements"][2]["content"],
                    "The pasted Malayalam dialogue should preserve its original Unicode text."
                )


                # Verify explicit click/focus on pasted contenteditable elements
                first_editable = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#screenplayPage .element-content:not(.d-none)"))
                )
                driver.execute_script("""
                    const el = arguments[0];
                    el.focus();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                """, first_editable)
                time.sleep(0.2)
                active_el_is_editable = driver.execute_script("return document.activeElement === arguments[0] || arguments[0].contains(document.activeElement);", first_editable)
                self.assertTrue(active_el_is_editable)

                # Test multi-block selection copy
                driver.execute_script("""
                    const charEl = document.querySelector('#screenplayPage .script-element-block[data-type="character"] .element-content');
                    const diagEl = document.querySelector('#screenplayPage .script-element-block[data-type="dialogue"] .element-content');
                    if (charEl && diagEl) {
                        const range = document.createRange();
                        range.setStart(charEl.firstChild || charEl, 0);
                        range.setEnd(diagEl.firstChild || diagEl, (diagEl.firstChild || diagEl).textContent.length);
                        const sel = window.getSelection();
                        sel.removeAllRanges();
                        sel.addRange(range);

                        const dt = new DataTransfer();
                        const copyEvt = new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData: dt });
                        document.dispatchEvent(copyEvt);
                    }
                """)
                time.sleep(0.3)
                copied = driver.execute_script("return (window.editor || window.editorInstance) ? (window.editor || window.editorInstance).lastCopiedPayload : null;")
                self.assertIsNotNone(copied)
                self.assertEqual(copied.get('source'), 'kadhascript')
                copied_types = [el['type'] for el in copied.get('elements', [])]
                self.assertIn('character', copied_types)
                self.assertIn('dialogue', copied_types)

                # ========================================================
                # BATCH 1 FOLLOW-UP FIX VERIFICATIONS
                # ========================================================

                # --------------------------------------------------------
                # FIX 1: EXTERNAL PASTE (CASES A, B, C)
                # --------------------------------------------------------
                # Case A1: Caret in middle of Action block with external Malayalam plain text
                action_editable = driver.find_element(By.CSS_SELECTOR, '#screenplayPage .script-element-block[data-type="action"] .element-content')
                driver.execute_script("""
                    const ed = arguments[0];
                    ed.innerText = "ഒരു പഴയ മാളിക.";
                    ed.focus();
                    // Place caret right after "ഒരു പഴയ " (index 8)
                    const range = document.createRange();
                    const textNode = ed.firstChild;
                    range.setStart(textNode, 8);
                    range.setEnd(textNode, 8);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);

                    // Paste external plain text (no KadhaScript custom MIME type)
                    const dt = new DataTransfer();
                    dt.setData('text/plain', "മനോഹരമായ ");
                    const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                    document.dispatchEvent(pasteEvt);
                """, action_editable)
                time.sleep(0.3)

                action_text = driver.execute_script("return arguments[0].innerText.trim();", action_editable)
                self.assertEqual(action_text, "ഒരു പഴയ മനോഹരമായ മാളിക.", f"Expected text inserted at caret in Action, got: {action_text}")
                action_html = driver.execute_script("return arguments[0].innerHTML;", action_editable)
                self.assertNotIn("<span", action_html)
                self.assertNotIn("font-family", action_html)

                # Case A2: Caret in middle of Malayalam Dialogue with external plain text
                diag_editable = driver.find_element(By.CSS_SELECTOR, '#screenplayPage .script-element-block[data-type="dialogue"] .element-content')
                driver.execute_script("""
                    const ed = arguments[0];
                    ed.innerText = "എല്ലാം ശരിയാകും.";
                    ed.focus();
                    // Place caret right after "എല്ലാം " (index 7)
                    const range = document.createRange();
                    const textNode = ed.firstChild;
                    range.setStart(textNode, 7);
                    range.setEnd(textNode, 7);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);

                    const dt = new DataTransfer();
                    dt.setData('text/plain', "തീർച്ചയായും ");
                    const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                    document.dispatchEvent(pasteEvt);
                """, diag_editable)
                time.sleep(0.3)

                diag_text = driver.execute_script("return arguments[0].innerText.trim();", diag_editable)
                self.assertEqual(diag_text, "എല്ലാം തീർച്ചയായും ശരിയാകും.", f"Expected text inserted at caret in Dialogue, got: {diag_text}")

                # Case B: External multiline text inserted cleanly without creating new blocks or scenes
                blocks_count_before = driver.execute_script("return document.querySelectorAll('#screenplayPage .script-element-block').length;")
                driver.execute_script("""
                    const ed = arguments[0];
                    ed.focus();
                    // Set caret to end
                    const range = document.createRange();
                    range.selectNodeContents(ed);
                    range.collapse(false);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);

                    const multilineText = "\\nരണ്ടാം വരി\\nമൂന്നാം വരി";
                    const dt = new DataTransfer();
                    dt.setData('text/plain', multilineText);
                    const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                    document.dispatchEvent(pasteEvt);
                """, action_editable)
                time.sleep(0.3)

                blocks_count_after = driver.execute_script("return document.querySelectorAll('#screenplayPage .script-element-block').length;")
                self.assertEqual(blocks_count_before, blocks_count_after, "Multiline plain text paste must not create new semantic element blocks!")
                updated_action = driver.execute_script("return arguments[0].innerText;", action_editable)
                self.assertIn("രണ്ടാം വരി", updated_action)
                self.assertIn("മൂന്നാം വരി", updated_action)
                action_block_type = driver.execute_script("return arguments[0].closest('.script-element-block').dataset.type;", action_editable)
                self.assertEqual(action_block_type, "action", "Target element must retain its action semantic element type")

                # Case C: External paste when no element is focused
                driver.execute_script("""
                    if (document.activeElement && document.activeElement.blur) {
                        document.activeElement.blur();
                    }
                    window.getSelection().removeAllRanges();
                    document.body.focus();

                    const dt = new DataTransfer();
                    dt.setData('text/plain', " (കൂട്ടിച്ചേർത്തത്)");
                    const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
                    document.dispatchEvent(pasteEvt);
                """)
                time.sleep(0.3)

                # Confirm fallback target block safely received the text
                editor_content = driver.execute_script("return document.getElementById('screenplayPage').innerText;")
                self.assertIn("(കൂട്ടിച്ചേർത്തത്)", editor_content, "Case C external paste must safely insert text into the editor target!")

                # --------------------------------------------------------
                # FIX 2: CHARACTER AUTOCOMPLETE POSITIONING & VIEWPORT
                # --------------------------------------------------------
                # Trigger Character Autocomplete
                driver.execute_script("""
                    const ed = (window.editor || window.editorInstance);
                    if (ed) {
                        ed.characters = ['റഹീം', 'വിക്രം', 'അനു', 'SIDDHARTH', 'CHANDRAN'];
                        const charBlock = document.querySelector('#screenplayPage .script-element-block[data-type="character"]');
                        if (charBlock) {
                            const editable = charBlock.querySelector('.element-content');
                            editable.innerText = "റ";
                            ed.handleCharacterInput(editable);
                        }
                    }
                """)
                time.sleep(0.3)

                ac_data = driver.execute_script("""
                    const dropdown = document.getElementById('characterAutocomplete');
                    const charBlock = document.querySelector('#screenplayPage .script-element-block[data-type="character"] .element-content');
                    if (!dropdown || !charBlock) return null;
                    const dRect = dropdown.getBoundingClientRect();
                    const cRect = charBlock.getBoundingClientRect();
                    const computed = window.getComputedStyle(dropdown);
                    return {
                        position: computed.position,
                        display: computed.display,
                        left: dRect.left,
                        top: dRect.top,
                        width: dRect.width,
                        height: dRect.height,
                        charLeft: cRect.left,
                        charBottom: cRect.bottom,
                        winWidth: window.innerWidth,
                        winHeight: window.innerHeight
                    };
                """)
                self.assertIsNotNone(ac_data)
                self.assertEqual(ac_data['position'], 'fixed', "Character autocomplete must use position: fixed!")
                self.assertEqual(ac_data['display'], 'block', "Character autocomplete must be visible!")
                self.assertGreaterEqual(ac_data['left'], 0, "Autocomplete dropdown must stay within left viewport bound!")
                self.assertLessEqual(ac_data['left'] + ac_data['width'], ac_data['winWidth'], "Autocomplete dropdown must stay within right viewport bound!")

                # Test canvas scrolling: dropdown must not stay frozen at old detached location
                driver.execute_script("""
                    const canvasContainer = document.getElementById('editorCanvasContainer');
                    if (canvasContainer) {
                        canvasContainer.scrollTop += 60;
                        canvasContainer.dispatchEvent(new Event('scroll'));
                    }
                """)
                time.sleep(0.2)

                scrolled_ac = driver.execute_script("""
                    const dropdown = document.getElementById('characterAutocomplete');
                    const charBlock = document.querySelector('#screenplayPage .script-element-block[data-type="character"] .element-content');
                    if (!dropdown || !charBlock) return null;
                    const dRect = dropdown.getBoundingClientRect();
                    const cRect = charBlock.getBoundingClientRect();
                    const computed = window.getComputedStyle(dropdown);
                    return {
                        display: computed.display,
                        top: dRect.top,
                        charBottom: cRect.bottom
                    };
                """)
                if scrolled_ac and scrolled_ac['display'] != 'none':
                    # If repositioned, must remain attached to Character field
                    self.assertAlmostEqual(scrolled_ac['top'], scrolled_ac['charBottom'] + 4, delta=20)

                # --------------------------------------------------------
                # FIX 3: CONTEXTUAL SUGGESTION POPUP SCROLL CONFLICT
                # --------------------------------------------------------
                driver.execute_script("""
                    const ed = (window.editor || window.editorInstance);
                    if (ed) {
                        const targetBlock = document.querySelector('#screenplayPage .script-element-block[data-type="action"]');
                        ed.showSuggestionPopup(targetBlock, [
                            { type: 'dialogue', label: 'Dialogue' },
                            { type: 'parenthetical', label: 'Parenthetical' }
                        ]);
                    }
                """)
                time.sleep(0.3)

                # Scroll canvas container by 25px
                driver.execute_script("""
                    const canvasContainer = document.getElementById('editorCanvasContainer');
                    if (canvasContainer) {
                        canvasContainer.scrollTop += 25;
                        canvasContainer.dispatchEvent(new Event('scroll'));
                    }
                """)
                time.sleep(0.2)

                popup_display = driver.execute_script("""
                    const popup = document.getElementById('elementSuggestionPopup');
                    return popup ? window.getComputedStyle(popup).display : 'none';
                """)
                # The conflicting listener was removed, so popup remains visible and repositioned
                self.assertIn(popup_display, ['inline-flex', 'flex', 'block'], "Suggestion popup must NOT be dismissed immediately upon scrolling canvas!")

                # Save Screenshot for this viewport
                screenshot_path = os.path.join(ARTIFACTS_DIR, f"browser_verify_{vp_name}.png")
                driver.save_screenshot(screenshot_path)

        finally:
            driver.quit()


# ==============================================================================
# MUSICAL & MONTAGE SEQUENCE BROWSER VERIFICATION
# ==============================================================================

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
class BrowserSequenceVerificationTest(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        opts = ChromeOptions()
        opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--window-size=1440,900')
        opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

        driver_path = r'C:\Users\rasiz\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
        if os.path.exists(driver_path):
            service = ChromeService(executable_path=driver_path)
            cls.driver = webdriver.Chrome(service=service, options=opts)
        else:
            cls.driver = webdriver.Chrome(options=opts)
        cls.driver.implicitly_wait(5)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'driver') and cls.driver:
            cls.driver.quit()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username='director',
            email='director@kadhascript.com',
            password='password123'
        )
        self.script = Script.objects.create(
            user=self.user,
            title='കഥാസ്ക്രിപ്റ്റ് - Cinema Script'
        )
        # Create 10 scenes
        for i in range(1, 11):
            sc = Scene.objects.create(script=self.script, scene_number=i, heading=f'INT. LOCATION {i} - DAY', order=i)
            ScriptElement.objects.create(scene=sc, element_type='scene_heading', content=f'INT. LOCATION {i} - DAY', order=0)
            ScriptElement.objects.create(scene=sc, element_type='action', content=f'Scene {i} action content.', order=1)

    def login_user(self):
        self.driver.set_window_size(1440, 900)
        login_url = reverse('login')
        self.driver.get(f"{self.live_server_url}{login_url}")
        email_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, 'email'))
        )
        email_input.send_keys('director@kadhascript.com')
        password_input = self.driver.find_element(By.NAME, 'password')
        password_input.send_keys('password123')
        submit_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'form button[type="submit"]'))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
        time.sleep(0.2)
        try:
            submit_btn.click()
        except Exception:
            password_input.submit()
        WebDriverWait(self.driver, 10).until(lambda d: '/login/' not in d.current_url)

    def test_full_sequence_browser_flow(self):
        """
        Verify the exact browser sequence workflow across desktop, tablet, and mobile:
        1. Open Scene 10.
        2. Start Song.
        3. Confirm a separate sequence scene/page is created/opened.
        4. Add multiple sequence shots.
        5. Navigate back to Scene 10.
        6. Confirm Scene 10 has not been polluted with sequence elements.
        7. Open the sequence again.
        8. End the Song.
        9. Click New Scene.
        10. Confirm ending marker is present exactly once.
        11. Confirm new normal scene is Scene 11.
        12. Repeat basic workflow for Montage.
        13. Verify desktop, tablet, and mobile scene navigation.
        """
        self.login_user()

        # Desktop Viewport
        self.driver.set_window_size(1440, 900)
        editor_url = f"{self.live_server_url}/scripts/{self.script.id}/editor/"
        self.driver.get(editor_url)

        # Wait for editor to load
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, 'screenplayPage'))
        )
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId.length > 0;
            """)
        )

        # Switch to Edit Mode first so scene navigation switches the active editing canvas
        self.driver.execute_script("window.editorInstance.setEditorMode('edit');")
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("return window.editorInstance.editorMode === 'edit';")
        )

        # 1. Open Scene 10
        sc10 = self.script.scenes.get(scene_number=10)
        # Click Scene 10 in sidebar
        scene_10_item = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'#scenesList .scene-item[data-id="{sc10.id}"]'))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", scene_10_item)
        time.sleep(0.2)
        scene_10_item.click()

        # Wait for Scene 10 to be loaded into active editor
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script(f"""
                return window.editorInstance &&
                       Number(window.editorInstance.currentSceneId) === {sc10.id} &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('Scene 10');
            """)
        )

        # Confirm Scene 10 is loaded
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('Scene 10', heading)

        # 2. Start Song
        btn_seq = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnSequenceDropdown'))
        )
        btn_seq.click()
        time.sleep(0.3)

        btn_song = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnStartSongSequence'))
        )
        btn_song.click()

        # 3. Confirm separate sequence scene/page is created/opened
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('SONG BEGINS');
            """)
        )
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('SONG BEGINS', heading)

        # Check navigation item for Song Sequence exists in sidebar
        song_nav_item = self.driver.find_element(By.CSS_SELECTOR, '.scene-item.active .scene-nav-number')
        self.assertIn('Song Sequence', song_nav_item.text)

        # 4. Add multiple sequence shots
        btn_seq.click()
        time.sleep(0.3)
        btn_next = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnNextSequenceShot'))
        )
        btn_next.click()
        time.sleep(0.5)

        # Add shot 3
        btn_seq.click()
        time.sleep(0.3)
        btn_next = self.driver.find_element(By.ID, 'btnNextSequenceShot')
        btn_next.click()
        time.sleep(0.5)

        shot_numbers = [e.text.strip() for e in self.driver.find_elements(By.CSS_SELECTOR, '.sequence-shot-number')]
        self.assertEqual(shot_numbers, ['1.', '2.', '3.'])

        # 5. Navigate back to Scene 10
        scene_10_item = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'#scenesList .scene-item[data-id="{sc10.id}"]'))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", scene_10_item)
        time.sleep(0.2)
        scene_10_item.click()

        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script(f"""
                return window.editorInstance &&
                       Number(window.editorInstance.currentSceneId) === {sc10.id} &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('Scene 10');
            """)
        )

        # 6. Confirm Scene 10 has not been polluted with sequence elements
        sc10_elements_text = [e.text for e in self.driver.find_elements(By.CSS_SELECTOR, '#screenplayPage .element-content')]
        self.assertNotIn('SONG BEGINS', sc10_elements_text)
        self.assertNotIn('1. INT. LOCATION - DAY', sc10_elements_text)
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('Scene 10', heading)

        # 7. Open sequence again
        song_nav = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//li[contains(@class, 'scene-item')][.//span[contains(text(), 'Song Sequence')]]"))
        )
        song_scene_id = song_nav.get_attribute('data-id')
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", song_nav)
        time.sleep(0.2)
        song_nav.click()

        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script(f"""
                return window.editorInstance &&
                       Number(window.editorInstance.currentSceneId) === {song_scene_id} &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('SONG BEGINS');
            """)
        )

        # 8. End the Song
        btn_seq.click()
        time.sleep(0.3)
        btn_end = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnEndSequence'))
        )
        btn_end.click()
        time.sleep(0.5)

        # 9. Click New Scene
        btn_new_scene = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnTopAddScene'))
        )
        btn_new_scene.click()

        # 11. Confirm the new normal scene is Scene 11
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('Scene 11');
            """)
        )
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('Scene 11', heading)

        # 10. Check sequence scene in DB: confirm ending marker is present exactly once
        song_scene = Scene.objects.get(id=song_scene_id)
        song_ends_count = song_scene.elements.filter(content='SONG ENDS').count()
        self.assertEqual(song_ends_count, 1)

        # 12. Repeat basic workflow for Montage
        # From Scene 11, start Montage
        btn_seq.click()
        time.sleep(0.3)
        btn_montage = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnStartMontageSequence'))
        )
        btn_montage.click()

        # Confirm Montage sequence opened
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('MONTAGE BEGINS');
            """)
        )
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('MONTAGE BEGINS', heading)

        # Add a shot
        btn_seq.click()
        time.sleep(0.3)
        WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnNextSequenceShot'))
        ).click()
        time.sleep(0.5)

        # Click New Scene directly while Montage is active (auto-close test)
        btn_new_scene = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnTopAddScene'))
        )
        btn_new_scene.click()

        # Confirm new scene is Scene 12
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("""
                return window.editorInstance &&
                       !window.editorInstance.isSwitchingScene &&
                       window.editorInstance.currentFullHeading &&
                       window.editorInstance.currentFullHeading.includes('Scene 12');
            """)
        )
        heading = self.driver.execute_script("return window.editorInstance.currentFullHeading;")
        self.assertIn('Scene 12', heading)

        # 13. Verify Tablet and Mobile Viewports
        # Tablet Viewport (768x1024)
        self.driver.set_window_size(768, 1024)
        time.sleep(0.5)
        self.assertTrue(self.driver.find_element(By.ID, 'screenplayPage').is_displayed())
        self.assertTrue(self.driver.find_element(By.ID, 'btnSequenceDropdown').is_displayed())

        # Mobile Viewport (375x667)
        self.driver.set_window_size(375, 667)
        time.sleep(0.5)
        self.assertTrue(self.driver.find_element(By.ID, 'screenplayPage').is_displayed())

        # Test mobile scenes offcanvas drawer navigation
        nav_scenes_btn = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'btnNavScenes'))
        )
        nav_scenes_btn.click()
        time.sleep(0.5)

        # Verify offcanvas scenes list is displayed with sequence scene item
        offcanvas_list = WebDriverWait(self.driver, 5).until(
            EC.visibility_of_element_located((By.ID, 'offcanvasScenesList'))
        )
        self.assertTrue(offcanvas_list.is_displayed())
        offcanvas_song = offcanvas_list.find_element(By.XPATH, ".//li[contains(@class, 'scene-item')][.//span[contains(text(), 'Song Sequence')]]")
        self.assertTrue(offcanvas_song.is_displayed())
