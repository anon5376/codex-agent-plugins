from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


class WebContractTests(unittest.TestCase):
    def test_static_page_has_all_mission_inputs_and_actions(self) -> None:
        for field in (
            "title",
            "objective",
            "project_path",
            "deliverables",
            "success_criteria",
            "constraints",
            "context_files",
            "max_astra",
            "max_luna",
            "budget_mode",
            "budget_value",
            "pro_enabled",
            "pro_messages",
            "pro_project",
            "external_mode",
            "external_scope",
            "private_boundary",
        ):
            self.assertRegex(HTML, rf'\b(?:id|name)=["\']{re.escape(field)}["\']')
        self.assertIn('id="work-types"', HTML)
        self.assertIn('input.name = "work_types"', JS)
        for action in ("Review prompt", "Save mission", "Copy prompt", "Download prompt"):
            self.assertIn(action, HTML)

    def test_frontend_uses_only_relative_contract_routes_and_safe_dom_updates(self) -> None:
        self.assertIn('getJson("/api/config")', JS)
        self.assertIn('postJson("/api/preview"', JS)
        self.assertIn('postJson("/api/missions"', JS)
        self.assertIn('getJson("/api/missions")', JS)
        self.assertNotIn("innerHTML", JS)
        self.assertNotIn("eval(", JS)
        self.assertNotRegex(HTML + CSS + JS, r"https?://")

    def test_launch_surface_is_absent(self) -> None:
        combined = (HTML + "\n" + CSS + "\n" + JS).lower()
        for forbidden in (
            "allow_launch",
            "start in codex",
            "launchmission",
            "launch-button",
            "thread_url",
            "thread_id",
            "/launch",
        ):
            self.assertNotIn(forbidden, combined)

    def test_reverse_review_policy_and_accessible_responsive_floor_are_visible(self) -> None:
        normalized = " ".join(HTML.split()).lower()
        self.assertRegex(
            normalized,
            r"astra xhigh\s*(?:→|&rarr;|->)\s*sol high\s*(?:→|&rarr;|->)\s*luna max",
        )
        self.assertRegex(
            normalized,
            r"luna max\s*(?:→|&rarr;|->)\s*sol high\s*(?:→|&rarr;|->)\s*astra xhigh",
        )
        self.assertIn(":focus-visible", CSS)
        self.assertRegex(CSS, r"@media\s*\(max-width:\s*390px\)")
        self.assertRegex(CSS, r"overflow-x:\s*hidden")
        self.assertIn("aria-live", HTML)


if __name__ == "__main__":
    unittest.main()
