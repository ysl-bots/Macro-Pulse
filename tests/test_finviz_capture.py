import io
import os
import sys
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from macro_pulse.reporting import screenshots


class FinvizCaptureTests(unittest.TestCase):
    @patch.object(screenshots.time, "sleep")
    @patch.object(screenshots, "WebDriverWait")
    @patch.object(screenshots, "prepare_finviz_capture")
    @patch.object(screenshots, "get_chrome_driver")
    def test_popups_are_handled_after_navigation_and_before_capture(
        self, get_driver, prepare, wait, sleep
    ):
        driver = get_driver.return_value
        element = wait.return_value.until.return_value
        events = []
        driver.get.side_effect = lambda _: events.append("navigate")
        prepare.side_effect = lambda _: events.append("prepare")
        sleep.side_effect = lambda _: events.append("render")
        element.screenshot.side_effect = lambda _: events.append("capture")

        self.assertEqual(screenshots.take_finviz_screenshot("map.png"), "map.png")
        self.assertEqual(
            events, ["navigate", "prepare", "render", "prepare", "capture"]
        )
        driver.quit.assert_called_once()

    @patch.object(screenshots, "get_chrome_driver")
    def test_cleanup_failure_does_not_return_obscured_capture(self, get_driver):
        driver = get_driver.return_value
        driver.execute_script.side_effect = RuntimeError("script failed")
        with self.assertLogs(screenshots.logger, level="ERROR"):
            self.assertIsNone(screenshots.take_finviz_screenshot("map.png"))
        driver.quit.assert_called_once()


@unittest.skipUnless(
    os.environ.get("RUN_SCREENSHOT_BROWSER_TESTS") == "1",
    "Set RUN_SCREENSHOT_BROWSER_TESTS=1 for offline Chromium popup regressions.",
)
class FinvizPopupBrowserTests(unittest.TestCase):
    """Offline fixtures matching the selectors in Finviz's HTML/JS bundles."""

    @classmethod
    def setUpClass(cls):
        cls.driver = screenshots.get_chrome_driver()
        if cls.driver is None:
            raise RuntimeError("Chromium is required for popup regression tests")

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def setUp(self):
        html = """<!doctype html><html><head><style>
            body { margin: 0; }
            #canvas-wrapper { width: 1200px; height: 800px; background: #00aa00; }
            .cover { position: fixed; inset: 0; width: 100%; height: 100%;
                     background: red; backdrop-filter: blur(6px); }
        </style></head><body>
        <div id="canvas-wrapper">NVDA +1.0%</div>
        <div role="dialog" id="unrelated">Keep unrelated UI</div>
        <script>
        window.addPopups = () => {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = `
                <div id="modal-elite-ad" class="cover">
                    <button id="modal-elite-ad-close">×</button>
                </div>
                <dialog data-testid="elite-features-dialog" class="cover">
                    <button data-testid="elite-features-dialog-close">×</button>
                </dialog>
                <div role="dialog" aria-label="Map Layouts" class="cover">
                    <button aria-label="Close">×</button>
                </div>`;
            document.body.appendChild(wrapper);
            wrapper.querySelector('dialog').showModal();
        };
        </script></body></html>"""
        self.driver.get("data:text/html;charset=utf-8," + quote(html))

    def assert_clear_map(self):
        from PIL import Image

        # Pixel assertions detect both the red overlay and native dialog backdrop.
        element = self.driver.find_element(screenshots.By.ID, "canvas-wrapper")
        image = Image.open(io.BytesIO(element.screenshot_as_png)).convert("RGB")
        self.assertEqual(image.getpixel((600, 400)), (0, 170, 0))
        for selector in (
            "#modal-elite-ad",
            '[data-testid="elite-features-dialog"]',
            '[aria-label="Map Layouts"]',
        ):
            for popup in self.driver.find_elements(
                screenshots.By.CSS_SELECTOR, selector
            ):
                self.assertFalse(popup.is_displayed())
        self.assertTrue(
            self.driver.find_element(screenshots.By.ID, "unrelated").is_displayed()
        )

    def test_existing_popups_and_blurred_backdrop_are_hidden(self):
        self.driver.execute_script("addPopups()")
        screenshots.prepare_finviz_capture(self.driver)
        self.assert_clear_map()

    def test_popups_inserted_after_cleanup_are_still_hidden(self):
        screenshots.prepare_finviz_capture(self.driver)
        self.driver.execute_script("addPopups()")
        self.assert_clear_map()

    def test_no_popups_and_repeated_cleanup(self):
        screenshots.prepare_finviz_capture(self.driver)
        screenshots.prepare_finviz_capture(self.driver)
        self.assert_clear_map()
        self.assertEqual(
            len(
                self.driver.find_elements(
                    screenshots.By.ID, "macro-pulse-finviz-capture-style"
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
