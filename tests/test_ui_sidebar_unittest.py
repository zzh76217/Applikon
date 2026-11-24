import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cell_planner.ui.main_window import MainWindow


class SidebarAndValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.win = MainWindow()
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()

    def test_navigation_buttons_and_existing_page_links_stay_in_sync(self):
        for key, button in self.win.nav_buttons.items():
            button.click()
            self.assertEqual(self.win.current_page_key(), key)
            self.assertTrue(button.isChecked())
            self.assertEqual(sum(b.isChecked() for b in self.win.nav_buttons.values()), 1)
        self.assertTrue(self.win.goto_page("mapping"))
        self.assertTrue(self.win.nav_buttons["mapping"].isChecked())

    def test_groups_contain_all_rules_and_focus_relevant_input(self):
        tree = self.win.validation_tree
        groups = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        items = {g.child(i).data(0, Qt.UserRole): g.child(i)
                 for g in groups for i in range(g.childCount())}
        self.assertEqual(set(items), {"R%02d" % i for i in range(1, 19)})
        for rule, field in (("R01", "v_work"), ("R05", "rpm"),
                            ("R10", "ph"), ("R17", "sampling_ml")):
            self.win._focus_validation_item(items[rule])
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), self.win.widgets[field])
            self.assertTrue(self.win.widgets[field].isVisible())
        self.win._focus_validation_item(items["R16"])
        self.assertEqual(self.win.current_page_key(), "hardware")

    def test_changed_input_clears_stale_groups(self):
        self.win.widgets["v_work"].setValue(self.win.widgets["v_work"].value() + 1)
        self.assertEqual(self.win.validation_tree.topLevelItemCount(), 0)
        self.assertIsNone(self.win._last)
        self.win.compute()
        self.assertEqual(self.win.validation_tree.topLevelItemCount(), 3)


if __name__ == "__main__":
    unittest.main()
