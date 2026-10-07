import os
import sys
import time
from django.test import LiveServerTestCase
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.models import Script, Scene, ScriptElement

ARTIFACTS_DIR = r"C:\Users\rasiz\.gemini\antigravity-ide\brain\d61e8d4b-7e73-4dab-8ca8-62e78c38bb51"
CHROMEDRIVER_PATH = r"C:\Users\rasiz\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"


class KadhaScriptBrowserUXVerification(LiveServerTestCase):
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
        User = get_user_model()
        cls.user = User.objects.create_user(username="ux_client_user", password="password123")

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
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,800")
        if os.path.exists(CHROMEDRIVER_PATH):
            service = Service(executable_path=CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
        return driver

    def login_user(self, driver):
        driver.get(f"{self.live_server_url}/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        driver.find_element(By.NAME, "username").send_keys("ux_client_user")
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
            self.assertIn("This action cannot be undone", del_modal.text)

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

            # Confirm item removed from DOM and deleted from DB
            del_items = driver.find_elements(By.ID, f"project-item-{self.script2_to_delete.id}")
            self.assertEqual(len(del_items), 0)
            self.assertFalse(Script.objects.filter(id=self.script2_to_delete.id).exists())

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
                self.assertIn("Move Up", menu_text)
                self.assertIn("Move Down", menu_text)
                self.assertIn("Delete", menu_text)

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
                self.assertIn("Move Up", sub_menu_text)
                self.assertIn("Move Down", sub_menu_text)
                self.assertIn("Delete", sub_menu_text)

                # Save Screenshot for this viewport
                screenshot_path = os.path.join(ARTIFACTS_DIR, f"browser_verify_{vp_name}.png")
                driver.save_screenshot(screenshot_path)

        finally:
            driver.quit()
