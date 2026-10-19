import time
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from scripts.models import Script, Scene, ScriptElement

CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"
User = get_user_model()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class SequenceDropdownRegressionTests(StaticLiveServerTestCase):
    """
    Batch 3 Step 4: Sequence Dropdown Visibility, Layering & Alignment Regression Tests.
    Tests across mobile, tablet, and desktop viewports.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def create_driver(self, viewport_type="mobile"):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        if viewport_type == "mobile":
            options.add_argument("--window-size=390,844")
            mobile_emulation = {"deviceName": "iPhone 12 Pro"}
            options.add_experimental_option("mobileEmulation", mobile_emulation)
        elif viewport_type == "tablet":
            options.add_argument("--window-size=768,1024")
        else:  # desktop
            options.add_argument("--window-size=1366,768")

        service = Service(executable_path=CHROMEDRIVER_PATH)
        return webdriver.Chrome(service=service, options=options)

    def _login_and_open_editor(self, driver, username="seq_tester"):
        user = User.objects.create_user(username=username, password="password123")
        script = Script.objects.create(title="Sequence Script", user=user)
        scene = Scene.objects.create(script=script, scene_number=1, heading="INT. TEST CAFE - DAY", order=1)
        for i in range(1, 25):
            ScriptElement.objects.create(
                scene=scene, element_type="action", content=f"Action line {i} to create scrollable space.", order=i
            )

        d = driver
        d.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(d, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        d.find_element(By.NAME, "username").send_keys(username)
        d.find_element(By.NAME, "password").send_keys("password123")
        d.find_element(By.NAME, "password").submit()
        WebDriverWait(d, 10).until(EC.url_contains("/dashboard/"))

        d.get(f"{self.live_server_url}/scripts/{script.id}/editor/")
        WebDriverWait(d, 10).until(EC.presence_of_element_located((By.ID, "btnEnterEditMode")))
        WebDriverWait(d, 10).until(
            lambda drv: drv.execute_script("""
                return window.editorInstance &&
                       window.editorInstance.pageContainer &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId &&
                       window.editorInstance.pageContainer.dataset.loadedSceneId.length > 0;
            """)
        )
        d.execute_script("window.editorInstance.setEditorMode('edit');")
        time.sleep(0.8)
        return script, scene

    def test_mobile_sequence_dropdown_lifecycle_layering_and_actions(self):
        """
        Validates mobile layout (iPhone 12 Pro emulation):
        1. Dropdown opens, unclips overflow, elevates z-index above formatting toolbar.
        2. Drops down properly without clipping.
        3. Canvas scrolling maintains alignment or dismisses.
        4. Dismissal via outside click and Escape restores toolbar overflow and classes.
        5. Sequence actions execute properly.
        """
        driver = self.create_driver("mobile")
        try:
            self._login_and_open_editor(driver, "mobile_tester")
            d = driver

            btn = WebDriverWait(d, 10).until(EC.presence_of_element_located((By.ID, "btnSequenceDropdown")))
            menu = d.find_element(By.CSS_SELECTOR, "#sequenceDropdownContainer .dropdown-menu")
            formattingToolbar = d.find_element(By.ID, "editorFormattingToolbar")
            pinned = d.find_element(By.ID, "editorTopToolbarsPinned")

            # 1. Open dropdown
            d.execute_script("arguments[0].click();", btn)
            time.sleep(0.4)

            metrics = d.execute_script("""
                const btn = document.getElementById('btnSequenceDropdown');
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                const formattingToolbar = document.getElementById('editorFormattingToolbar');
                const toolbarLeft = document.querySelector('.editor-scene-toolbar-left');
                const pinned = document.getElementById('editorTopToolbarsPinned');

                const btnRect = btn.getBoundingClientRect();
                const menuRect = menu.getBoundingClientRect();
                const formatRect = formattingToolbar.getBoundingClientRect();

                return {
                    isOpen: menu.classList.contains('show'),
                    pinnedHasClass: pinned.classList.contains('has-dropdown-open'),
                    toolbarLeftOverflowX: window.getComputedStyle(toolbarLeft).overflowX,
                    toolbarLeftOverflowY: window.getComputedStyle(toolbarLeft).overflowY,
                    menuZIndex: parseInt(window.getComputedStyle(menu).zIndex) || 0,
                    formatZIndex: parseInt(window.getComputedStyle(formattingToolbar).zIndex) || 0,
                    btnRect: { top: btnRect.top, bottom: btnRect.bottom, left: btnRect.left, right: btnRect.right },
                    menuRect: { top: menuRect.top, bottom: menuRect.bottom, left: menuRect.left, right: menuRect.right },
                    formatRect: { top: formatRect.top, bottom: formatRect.bottom }
                };
            """)

            self.assertTrue(metrics['isOpen'], "Dropdown menu should have .show class")
            self.assertTrue(metrics['pinnedHasClass'], "Pinned toolbars container should have .has-dropdown-open class")
            self.assertEqual(metrics['toolbarLeftOverflowX'], "visible", "Left toolbar overflow-x must be visible when open")
            self.assertEqual(metrics['toolbarLeftOverflowY'], "visible", "Left toolbar overflow-y must be visible when open")
            self.assertGreater(metrics['menuZIndex'], metrics['formatZIndex'], "Dropdown menu z-index must be higher than formatting toolbar")
            self.assertGreaterEqual(metrics['menuRect']['top'], metrics['btnRect']['top'], "Menu should position below the button")

            # 2. Canvas scrolling while open
            d.execute_script("document.getElementById('editorCanvasContainer').scrollTop = 350;")
            time.sleep(0.3)
            still_open = d.execute_script("""
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                return menu && menu.classList.contains('show');
            """)
            self.assertTrue(still_open, "Dropdown remains open while canvas scrolls")

            # 3. Dismissal via outside click
            d.execute_script("document.getElementById('editorCanvasContainer').click();")
            time.sleep(0.4)
            closed_outside = d.execute_script("""
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                const pinned = document.getElementById('editorTopToolbarsPinned');
                const toolbarLeft = document.querySelector('.editor-scene-toolbar-left');
                return {
                    isClosed: !menu.classList.contains('show'),
                    pinnedHasClass: pinned.classList.contains('has-dropdown-open'),
                    overflowRestored: window.getComputedStyle(toolbarLeft).overflowX === 'auto'
                };
            """)
            self.assertTrue(closed_outside['isClosed'], "Dropdown should close on outside click")
            self.assertFalse(closed_outside['pinnedHasClass'], "has-dropdown-open should be removed on outside click")
            self.assertTrue(closed_outside['overflowRestored'], "Toolbar overflow-x should be restored to auto")

            # 4. Open and Dismissal via Escape
            d.execute_script("arguments[0].click();", btn)
            time.sleep(0.4)
            ActionChains(d).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.4)
            closed_escape = d.execute_script("""
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                const pinned = document.getElementById('editorTopToolbarsPinned');
                return {
                    isClosed: !menu.classList.contains('show'),
                    pinnedHasClass: pinned.classList.contains('has-dropdown-open')
                };
            """)
            self.assertTrue(closed_escape['isClosed'], "Dropdown should close on Escape key")
            self.assertFalse(closed_escape['pinnedHasClass'], "has-dropdown-open should be removed on Escape")

            # 5. Open and click "Song Sequence"
            d.execute_script("arguments[0].click();", btn)
            time.sleep(0.4)
            d.execute_script("document.getElementById('btnStartSongSequence').click();")

            WebDriverWait(d, 10).until(
                lambda drv: drv.execute_script("""
                    return window.editorInstance &&
                           !window.editorInstance.isSwitchingScene &&
                           window.editorInstance.currentFullHeading &&
                           window.editorInstance.currentFullHeading.includes('SONG BEGINS');
                """)
            )

            # Check sequence state updated and dropdown closed
            seq_state = d.execute_script("""
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                const editor = window.editorInstance;
                const state = editor ? editor.detectCurrentSequenceState() : null;
                return {
                    isClosed: !menu.classList.contains('show'),
                    isSequenceScene: Boolean(state && state.isSequenceScene),
                    seqType: state ? state.type : null
                };
            """)
            self.assertTrue(seq_state['isClosed'], "Dropdown should close after selecting Song Sequence")
            self.assertTrue(seq_state['isSequenceScene'], "Current scene should now be recognized as a sequence scene")
            self.assertEqual(seq_state['seqType'], "song", "Sequence type should be song")

            # 6. Open again, Next Sequence Shot & End Sequence should now be enabled
            btn = d.find_element(By.ID, "btnSequenceDropdown")
            d.execute_script("arguments[0].click();", btn)
            time.sleep(0.4)
            controls_state = d.execute_script("""
                const btnNext = document.getElementById('btnNextSequenceShot');
                const btnEnd = document.getElementById('btnEndSequence');
                return {
                    nextDisabled: btnNext.disabled,
                    endDisabled: btnEnd.disabled
                };
            """)
            self.assertFalse(controls_state['nextDisabled'], "Next Sequence Shot should be enabled in song sequence")
            self.assertFalse(controls_state['endDisabled'], "End Sequence should be enabled in song sequence")

            # 7. Click Next Sequence Shot
            d.execute_script("document.getElementById('btnNextSequenceShot').click();")
            time.sleep(0.5)

            # 8. Open again and click End Sequence
            d.execute_script("arguments[0].click();", btn)
            time.sleep(0.4)
            d.execute_script("document.getElementById('btnEndSequence').click();")
            time.sleep(0.5)

            # Confirm sequence ended and dropdown closed
            end_state = d.execute_script("""
                const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                const editor = window.editorInstance;
                const state = editor ? editor.detectCurrentSequenceState() : null;
                return {
                    isClosed: !menu.classList.contains('show'),
                    hasEnded: Boolean(state && state.hasEnded)
                };
            """)
            self.assertTrue(end_state['isClosed'], "Dropdown should close after clicking End Sequence")
            self.assertTrue(end_state['hasEnded'], "Sequence should be marked as ended")

        finally:
            driver.quit()

    def test_tablet_and_desktop_dropdown_visibility(self):
        """
        Validates tablet (768x1024) and desktop (1366x768) layouts.
        """
        for viewport in ["tablet", "desktop"]:
            driver = self.create_driver(viewport)
            try:
                self._login_and_open_editor(driver, f"{viewport}_tester")
                d = driver

                btn = WebDriverWait(d, 10).until(EC.presence_of_element_located((By.ID, "btnSequenceDropdown")))
                d.execute_script("arguments[0].click();", btn)
                time.sleep(0.4)

                res = d.execute_script("""
                    const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                    const pinned = document.getElementById('editorTopToolbarsPinned');
                    const toolbarLeft = document.querySelector('.editor-scene-toolbar-left');
                    return {
                        isOpen: menu.classList.contains('show'),
                        pinnedHasClass: pinned.classList.contains('has-dropdown-open'),
                        toolbarLeftOverflowX: window.getComputedStyle(toolbarLeft).overflowX,
                        menuZIndex: parseInt(window.getComputedStyle(menu).zIndex) || 0
                    };
                """)
                self.assertTrue(res['isOpen'], f"[{viewport}] Dropdown should open")
                self.assertTrue(res['pinnedHasClass'], f"[{viewport}] Pinned container should have has-dropdown-open")
                self.assertEqual(res['toolbarLeftOverflowX'], "visible", f"[{viewport}] Overflow-x should be visible")
                self.assertGreaterEqual(res['menuZIndex'], 1050, f"[{viewport}] Menu z-index should be >= 1050")

                # Close it
                d.execute_script("arguments[0].click();", btn)
                time.sleep(0.3)
                is_closed = d.execute_script("""
                    const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                    return !menu.classList.contains('show');
                """)
                self.assertTrue(is_closed, f"[{viewport}] Dropdown should close")
            finally:
                driver.quit()
