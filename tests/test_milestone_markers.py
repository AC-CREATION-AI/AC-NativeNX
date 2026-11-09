"""Placement statique synthétique, sans exécution Android ni contenu de jeu."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'engine/ports/shared-android'


class MilestoneMarkers(unittest.TestCase):
    def test_app_open(self):
        paths = [ROOT / 'shell/src/android/app/src/main/java/org/yuzu/yuzu_emu/ui/main/MainActivity.kt',
                 PORT / 'apk/app/src/main/java/com/lasrecomp/android/SharedLauncherActivity.java']
        for path in paths:
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn('"APP_OPEN"', text)
                self.assertNotIn('GAME_FIRST_FRAME', text)

    def test_reservation_result_and_size(self):
        text = (PORT / 'runtime/gamelib.c').read_text()
        body = text.split('static int reserve_window(', 1)[1].split('bool shared_session_prepare', 1)[0]
        self.assertIn('MEM_RESERVE_FAIL(%llu)', body)
        self.assertIn('MEM_RESERVE_OK(%llu)', body)
        self.assertIn('layout->window.hi - layout->window.lo', body)
        self.assertLess(body.index('plat_reserve_guest('), body.index('MEM_RESERVE_OK'))

    def test_both_vulkan_creation_paths(self):
        text = (PORT / 'runtime/nvn/vulkan/device.c').read_text()
        self.assertEqual(text.count('VK_DEVICE_FAIL(%s)'), 2)
        self.assertEqual(text.count('VK_DEVICE_OK(%s)'), 2)
        self.assertEqual(text.count('VkResult device_result = vkCreateDevice('), 2)
        self.assertEqual(text.count('VK_CHECK(device_result);'), 2)
        self.assertIn('g_vk.props.deviceName', text)

    def test_first_guest_present_only(self):
        text = (PORT / 'runtime/nvn/vulkan/device.c').read_text()
        body = text.split('static void present_hooks(void) {', 1)[1].split('void backend_present(', 1)[0]
        self.assertIn('if (total_frames == 1) LOG("GAME_FIRST_FRAME', body)
        self.assertEqual(text.count('"GAME_FIRST_FRAME'), 1)
        present = text.split('void backend_present(NvnTexture *t) {', 1)[1].split('// ===', 1)[0]
        self.assertLess(present.index('rq_present('), present.index('present_hooks();'))
        self.assertLess(present.index('backend_present_now('), present.index('present_hooks();'))

    def test_runtime_overlay_wiring(self):
        builder = (ROOT / 'engine/tools/build_shared_android.py').read_text()
        self.assertIn('PORT / "runtime"', builder)
        self.assertIn('target = temporary / "runtime" / path.relative_to(PORT / "runtime")', builder)


if __name__ == '__main__':
    unittest.main()
