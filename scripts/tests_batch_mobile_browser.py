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

from scripts.models import Script, Scene, ScriptElement

CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"
User = get_user_model()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class MobileBrowserVerificationTests(StaticLiveServerTestCase):
    """
    Browser verification for:
    - Requirement 1: Mobile dropdown alignment & viewport safety (320px, 375px, 414px)
    - Requirement 2: Navbar responsive spacing & brand text
    - Requirement 3: Registration page 3 fields & password eye toggle
    """

    def create_driver(self, width=375, height=812):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument(f"--window-size={width},{height}")

        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True if width < 768 else False}
        )
        return driver

    def test_navbar_viewports_320_375_414_768_desktop(self):
        """Verifies navbar brand and buttons across 320px, 375px, 414px, 768px, and 1280px."""
        viewports = [
            (320, 568, "mobile_320"),
            (375, 667, "mobile_375"),
            (414, 896, "mobile_414"),
            (768, 1024, "tablet_768"),
            (1280, 800, "desktop_1280"),
        ]

        for width, height, label in viewports:
            driver = self.create_driver(width, height)
            try:
                driver.get(f"{self.live_server_url}/")
                time.sleep(0.3)

                res = driver.execute_script("""
                    const nav = document.querySelector('nav.ks-navbar') || document.querySelector('nav');
                    const brand = document.querySelector('.ks-brand');
                    const malayalamSpan = brand ? brand.querySelector('span:first-of-type') : null;
                    const subtitleSpan = brand ? brand.querySelector('.ks-brand-subtitle') : null;
                    const signInBtn = document.querySelector('a.btn-outline-ks');
                    const getStartedBtn = document.querySelector('a.btn-primary-ks');
                    const brandRect = brand ? brand.getBoundingClientRect() : null;
                    const signInRect = signInBtn ? signInBtn.getBoundingClientRect() : null;
                    const getStartedRect = getStartedBtn ? getStartedBtn.getBoundingClientRect() : null;

                    return {
                        malayalamVisible: malayalamSpan && window.getComputedStyle(malayalamSpan).display !== 'none',
                        subtitleDisplay: subtitleSpan ? window.getComputedStyle(subtitleSpan).display : null,
                        signInVisible: signInBtn && window.getComputedStyle(signInBtn).display !== 'none',
                        getStartedVisible: getStartedBtn && window.getComputedStyle(getStartedBtn).display !== 'none',
                        noCollision: brandRect && signInRect ? (brandRect.right <= signInRect.left + 5) : true,
                        scrollWidth: document.documentElement.scrollWidth,
                        clientWidth: document.documentElement.clientWidth,
                        noHorizontalScroll: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1
                    };
                """)

                # Malayalam logo must ALWAYS be visible
                self.assertTrue(res['malayalamVisible'], f"[{label}] Malayalam logo must be visible")
                # Buttons must be visible and accessible
                self.assertTrue(res['signInVisible'], f"[{label}] Sign in button must be visible")
                self.assertTrue(res['getStartedVisible'], f"[{label}] Get started button must be visible")
                # Buttons and brand must not collide
                self.assertTrue(res['noCollision'], f"[{label}] Brand and sign-in button must not collide")
                # No horizontal page overflow
                self.assertTrue(res['noHorizontalScroll'], f"[{label}] No horizontal overflow allowed (scroll: {res['scrollWidth']}, client: {res['clientWidth']})")

                # Subtitle must be hidden on mobile (< 768px) and visible on desktop
                if width < 768:
                    self.assertEqual(res['subtitleDisplay'], 'none', f"[{label}] Subtitle should be hidden on mobile")
                elif width >= 1280:
                    self.assertNotEqual(res['subtitleDisplay'], 'none', f"[{label}] Subtitle should be visible on desktop")
            finally:
                driver.quit()

    def test_registration_page_browser_interaction_and_eye_toggle(self):
        """Verifies 3-field registration form and eye toggle interaction via real browser."""
        driver = self.create_driver(375, 667)
        try:
            driver.get(f"{self.live_server_url}/accounts/register/")
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "id_full_name")))

            name_input = driver.find_element(By.ID, "id_full_name")
            email_input = driver.find_element(By.ID, "id_email")
            pass_input = driver.find_element(By.ID, "id_password")
            toggle_btn = driver.find_element(By.ID, "togglePassword")

            self.assertEqual(pass_input.get_attribute("type"), "password")

            # Click eye toggle
            driver.execute_script("arguments[0].click();", toggle_btn)
            self.assertEqual(pass_input.get_attribute("type"), "text")

            # Click again to hide
            driver.execute_script("arguments[0].click();", toggle_btn)
            self.assertEqual(pass_input.get_attribute("type"), "password")

            # Confirm no extra fields exist in DOM
            with self.assertRaises(Exception):
                driver.find_element(By.ID, "id_username")
            with self.assertRaises(Exception):
                driver.find_element(By.ID, "id_password2")
        finally:
            driver.quit()

    def test_mobile_dropdown_viewport_safety_320_375_414_768_1280(self):
        """Verifies that Sequence and More Tools dropdowns stay fully visible within viewport across 320px, 375px, 414px, 768px, and 1280px without horizontal overflow."""
        user = User.objects.create_user(username="mobile_dd_user", password="password123")
        script = Script.objects.create(title="Dropdown Test Script", user=user)
        scene = Scene.objects.create(script=script, scene_number=1, heading="INT. ROOM - NIGHT", order=1)
        ScriptElement.objects.create(scene=scene, element_type="action", content="Action text.", order=1)

        viewports = [
            (320, 600, "mobile_320"),
            (375, 700, "mobile_375"),
            (414, 800, "mobile_414"),
            (768, 900, "tablet_768"),
            (1280, 800, "desktop_1280"),
        ]

        for width, height, label in viewports:
            driver = self.create_driver(width, height)
            try:
                # Login
                driver.get(f"{self.live_server_url}/accounts/login/")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
                driver.find_element(By.NAME, "username").send_keys("mobile_dd_user")
                driver.find_element(By.NAME, "password").send_keys("password123")
                driver.find_element(By.NAME, "password").submit()
                WebDriverWait(driver, 10).until(EC.url_contains("/dashboard/"))

                # Open editor
                driver.get(f"{self.live_server_url}/scripts/{script.id}/editor/")
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btnSequenceDropdown")))
                time.sleep(0.4)

                # 1. Test Sequence Dropdown
                btn_seq = driver.find_element(By.ID, "btnSequenceDropdown")
                driver.execute_script("arguments[0].click();", btn_seq)
                time.sleep(0.3)

                seq_metrics = driver.execute_script("""
                    const menu = document.querySelector('#sequenceDropdownContainer .dropdown-menu');
                    const rect = menu ? menu.getBoundingClientRect() : null;
                    return {
                        exists: !!menu,
                        rect: rect ? { left: rect.left, right: rect.right, width: rect.width } : null,
                        windowWidth: window.innerWidth,
                        documentScrollWidth: document.documentElement.scrollWidth
                    };
                """)

                self.assertTrue(seq_metrics['exists'], f"[{label}] Sequence dropdown menu must exist")
                seq_rect = seq_metrics['rect']
                # Must be fully contained in viewport
                self.assertLessEqual(seq_rect['right'], seq_metrics['windowWidth'] + 2, f"[{label}] Sequence dropdown right edge exceeds viewport")
                self.assertGreaterEqual(seq_rect['left'], -2, f"[{label}] Sequence dropdown left edge pushed off-screen")
                # Must not trigger horizontal scroll
                self.assertLessEqual(seq_metrics['documentScrollWidth'], seq_metrics['windowWidth'] + 2, f"[{label}] Sequence dropdown caused horizontal scroll")

                # Close sequence dropdown
                driver.execute_script("arguments[0].click();", btn_seq)
                time.sleep(0.2)

                # 2. Test More Tools Dropdown
                more_btn = driver.find_element(By.CSS_SELECTOR, ".editor-scene-toolbar-right [data-bs-toggle='dropdown']")
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(0.3)

                more_metrics = driver.execute_script("""
                    const menu = document.querySelector('.editor-scene-toolbar-right .dropdown-menu');
                    const rect = menu ? menu.getBoundingClientRect() : null;
                    return {
                        exists: !!menu,
                        rect: rect ? { left: rect.left, right: rect.right, width: rect.width } : null,
                        windowWidth: window.innerWidth,
                        documentScrollWidth: document.documentElement.scrollWidth
                    };
                """)

                self.assertTrue(more_metrics['exists'], f"[{label}] More Tools dropdown menu must exist")
                more_rect = more_metrics['rect']
                self.assertLessEqual(more_rect['right'], more_metrics['windowWidth'] + 2, f"[{label}] More Tools dropdown right edge exceeds viewport")
                self.assertGreaterEqual(more_rect['left'], -2, f"[{label}] More Tools dropdown left edge pushed off-screen")
                self.assertLessEqual(more_metrics['documentScrollWidth'], more_metrics['windowWidth'] + 2, f"[{label}] More Tools dropdown caused horizontal scroll")

                # Close more tools dropdown
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(0.2)

                # 3. Test Scenes Offcanvas opens and is not clipped by overflow-x: hidden
                btn_scenes = driver.find_element(By.ID, "btnNavScenes")
                driver.execute_script("arguments[0].click();", btn_scenes)
                time.sleep(0.4)

                offcanvas_metrics = driver.execute_script("""
                    const oc = document.getElementById('scenesOffcanvas');
                    const rect = oc ? oc.getBoundingClientRect() : null;
                    const isShown = oc ? oc.classList.contains('show') : false;
                    return {
                        exists: !!oc,
                        isShown: isShown,
                        rect: rect ? { left: rect.left, right: rect.right, width: rect.width } : null
                    };
                """)
                self.assertTrue(offcanvas_metrics['exists'], f"[{label}] Scenes offcanvas must exist")
                self.assertTrue(offcanvas_metrics['isShown'], f"[{label}] Scenes offcanvas must open properly")
                self.assertGreater(offcanvas_metrics['rect']['width'], 0, f"[{label}] Scenes offcanvas width must be > 0")
            finally:
                driver.quit()
