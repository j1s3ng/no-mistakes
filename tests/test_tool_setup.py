import contextlib
from copy import deepcopy
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from no_mistakes.cli import main
from no_mistakes.tool_catalog import get_tool
from no_mistakes.tool_setup import setup_workflow
from no_mistakes.toolbox import HOSTS, build_proposal


TODAY = date(2026, 10, 8)


class ForbiddenEnvironment(dict):
    def __getitem__(self, key):
        raise AssertionError("Setup must not resolve credential values")

    def get(self, key, default=None):
        raise AssertionError("Setup must not resolve credential values")


class ToolSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.saved = self.root / "browser plan.json"

    def proposal(self, tools=None, host="codex"):
        return build_proposal(tools or [get_tool("playwright")], host, self.project,
                              "Verify the local checkout interaction",
                              "Only the approved project and local fixture", today=TODAY)

    def render(self, proposal):
        return setup_workflow(proposal, self.saved, today=TODAY)

    def test_setup_is_inert_even_with_launch_recipes_and_credential_names(self):
        proposal = self.proposal([get_tool("playwright"), get_tool("context7"),
                                  get_tool("brave-search")])
        before = deepcopy(proposal)
        forbidden = AssertionError("Inert setup must not execute, connect, or open files")
        with contextlib.ExitStack() as stack:
            for name in ("subprocess.run", "subprocess.Popen", "os.system", "os.open",
                         "socket.socket", "urllib.request.urlopen", "pathlib.Path.open"):
                stack.enter_context(patch(name, side_effect=forbidden))
            stack.enter_context(patch.object(os, "environ", ForbiddenEnvironment()))
            result = self.render(proposal)
        self.assertEqual(proposal, before)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(result["digest"], proposal["digest"])
        self.assertIn("no downloads", result["notice"].lower())
        self.assertIn("not trusted instructions", result["notice"].lower())
        for unsupported_claim in ("installed", "authenticated", "available", "tested", "ready"):
            self.assertNotIn(unsupported_claim, result)

    def test_setup_keeps_the_exact_reviewed_launch_and_existing_config_boundary(self):
        proposal = self.proposal()
        result = self.render(proposal)
        launch = result["tools"][0]["installation"]
        connection = proposal["tools"][0]["connection"]
        self.assertEqual(launch["launch_argv"], [connection["command"], *connection["args"]])
        self.assertIn("download and execute", launch["action"])
        steps = {step["id"]: step for step in result["steps"]}
        self.assertEqual(steps["review"]["argv"][-1], str(self.saved))
        self.assertEqual(steps["approve_configure"]["argv"],
                         ["no-mistakes", "toolbox", "apply", str(self.saved)])
        self.assertIn("explicit user decision", steps["approve_configure"]["action"])
        self.assertIn("manual merge", steps["approve_configure"]["action"])
        self.assertIn("before", steps["approve_configure"]["action"])

    def test_http_recipe_has_endpoint_and_no_fictitious_download_or_launch(self):
        proposal = self.proposal([get_tool("context7"), get_tool("openai-docs")])
        tools = self.render(proposal)["tools"]
        for tool, reviewed in zip(tools, proposal["tools"]):
            with self.subTest(tool=tool["id"]):
                self.assertEqual(tool["installation"]["method"], "remote_http")
                self.assertEqual(tool["installation"]["endpoint"], reviewed["connection"]["url"])
                self.assertNotIn("launch_argv", tool["installation"])
                self.assertNotIn("browser_repair", tool)
                self.assertIn("no local server download", tool["installation"]["action"])
        self.assertEqual(tools[0]["credential_names"], ["CONTEXT7_API_KEY"])
        self.assertEqual(tools[1]["credential_names"], [])

    def test_multiple_tools_keep_their_own_prerequisites_credentials_and_checks(self):
        selected = [get_tool("brave-search"), get_tool("context7"), get_tool("github")]
        result = self.render(self.proposal(selected))
        for rendered, reviewed in zip(result["tools"], selected):
            with self.subTest(tool=reviewed["id"]):
                self.assertEqual(rendered["prerequisites"], reviewed["prerequisites"])
                self.assertEqual(rendered["verification"], reviewed["verification"])
                self.assertEqual(rendered["removal"], reviewed["removal"])
        self.assertEqual([tool["credential_names"] for tool in result["tools"]],
                         [["BRAVE_API_KEY"], ["CONTEXT7_API_KEY"], ["GITHUB_PAT_TOKEN"]])

    def test_custom_playwright_identifier_does_not_inherit_another_recipe(self):
        for change in ("package", "version", "flags"):
            with self.subTest(change=change):
                custom = get_tool("playwright")
                if change == "package":
                    custom["connection"]["args"][1] = "@synthetic/browser@0.0.83"
                elif change == "version":
                    custom["review"]["version"] = "1.2.3"
                    custom["connection"]["args"][1] = "@playwright/mcp@1.2.3"
                else:
                    custom["connection"]["args"].remove("--isolated")
                rendered = self.render(self.proposal([custom]))["tools"][0]
                self.assertEqual(rendered["installation"]["launch_argv"],
                                 [custom["connection"]["command"], *custom["connection"]["args"]])
                for inherited in ("browser_repair", "smoke_prompt", "fixture"):
                    self.assertNotIn(inherited, rendered)

    def test_custom_stdio_executable_has_no_invented_package_installer(self):
        custom = get_tool("playwright")
        custom["id"] = "synthetic-browser"
        custom["connection"] = {"transport": "stdio", "command": "synthetic-mcp",
                                "args": ["--readonly"], "env": {}, "env_vars": ["SYNTHETIC_KEY"]}
        rendered = self.render(self.proposal([custom]))["tools"][0]
        self.assertEqual(rendered["installation"]["method"], "reviewed_stdio")
        self.assertEqual(rendered["installation"]["launch_argv"], ["synthetic-mcp", "--readonly"])
        self.assertEqual(rendered["credential_names"], ["SYNTHETIC_KEY"])
        self.assertIn("No universal installer", rendered["installation"]["action"])
        self.assertNotIn("browser_repair", rendered)

    def test_generic_host_has_manual_connection_and_no_native_apply_command(self):
        result = self.render(self.proposal(host="generic"))
        self.assertIsNone(result["target"])
        approval = next(step for step in result["steps"] if step["id"] == "approve_configure")
        self.assertIsNone(approval["argv"])
        self.assertIn("generic hosts need manual setup", approval["action"])
        self.assertIn("no universal status command", result["host_guide"]["status"])

    def test_each_supported_host_has_reviewable_manual_status_and_connection_guidance(self):
        for host in HOSTS:
            with self.subTest(host=host):
                guide = self.render(self.proposal(host=host))["host_guide"]
                for field in ("connect", "status", "authentication"):
                    self.assertIsInstance(guide[field], str)
                    self.assertTrue(guide[field].strip())
                self.assertNotIn("argv", guide)
                if host != "generic":
                    self.assertTrue(guide["sources"])
                    self.assertTrue(all(source.startswith("https://") for source in guide["sources"]))

    def test_browser_repair_is_separate_conditional_and_requires_additional_approval(self):
        tool = self.render(self.proposal())["tools"][0]
        repair = tool["browser_repair"]
        self.assertIn("Only if actual launch reports missing Chrome", repair["condition"])
        self.assertIn("explicit approval", repair["condition"])
        self.assertIn("system Chrome", repair["limits"])
        self.assertIn("elevated privileges", repair["limits"])
        self.assertEqual(repair["argv"],
                         ["npx", "-y", "@playwright/mcp@0.0.83", "install-browser", "chrome"])
        self.assertNotEqual(repair["argv"], tool["installation"]["launch_argv"])

    def test_browser_smoke_requires_observed_interaction_and_owned_loopback_fixture(self):
        tool = self.render(self.proposal())["tools"][0]
        smoke = tool["smoke_prompt"]
        for expected in ("No Mistakes MCP smoke", "Pending", "Verify browser",
                         "Verified: browser interaction worked.", "console errors", "close the browser"):
            self.assertIn(expected, smoke)
        self.assertIn("navigation alone does not pass", smoke)
        self.assertIn("Stop if", smoke)
        server = tool["fixture"]["serve_argv"]
        self.assertEqual(server[server.index("--bind") + 1], "127.0.0.1")
        self.assertEqual(server[server.index("--directory") + 1], "examples")
        self.assertIn("unused loopback port", tool["fixture"]["instructions"])
        self.assertIn("stop that server", tool["fixture"]["instructions"])

    def test_tampered_and_stale_proposals_are_rejected_instead_of_emitting_install_steps(self):
        proposal = self.proposal()
        tampered = deepcopy(proposal)
        tampered["config"] += "# unreviewed change\n"
        with self.assertRaises(ValueError):
            self.render(tampered)
        with self.assertRaisesRegex(ValueError, "stale"):
            setup_workflow(proposal, self.saved, today=TODAY + timedelta(days=31))

    def test_unusable_proposal_paths_are_rejected_before_emitting_commands(self):
        proposal = self.proposal()
        for candidate in (None, 7, [], "", " ", "plan\n.json", "plan\x00.json", "plan\ud800.json"):
            with self.subTest(kind=type(candidate).__name__):
                with self.assertRaises(ValueError):
                    setup_workflow(proposal, candidate, today=TODAY)

    def test_relative_proposal_path_is_made_absolute_for_later_host_sessions(self):
        supplied = Path("plans") / "approved browser plan.json"
        result = setup_workflow(self.proposal(), supplied, today=TODAY)
        expected = str(supplied.absolute())
        for step in result["steps"]:
            if step.get("argv"):
                self.assertEqual(step["argv"][-1], expected)

    def test_generated_output_does_not_mutate_the_review_or_future_workflows(self):
        proposal = self.proposal([get_tool("brave-search")])
        before = deepcopy(proposal)
        first = self.render(proposal)
        first["host_guide"]["status"] = "synthetic mutation"
        first["tools"][0]["credential_names"].append("UNREVIEWED_KEY")
        first["tools"][0]["prerequisites"].append("unreviewed prerequisite")
        self.assertEqual(proposal, before)
        second = self.render(proposal)
        self.assertNotEqual(second["host_guide"]["status"], "synthetic mutation")
        self.assertEqual(second["tools"][0]["credential_names"], ["BRAVE_API_KEY"])
        self.assertNotIn("unreviewed prerequisite", second["tools"][0]["prerequisites"])

    def test_task_use_requires_acceptance_evidence_big_picture_review_and_stall_stop(self):
        steps = {step["id"]: step for step in self.render(self.proposal())["steps"]}
        self.assertIn("acceptance criteria", steps["use"]["action"])
        self.assertIn("original intent and overall project", steps["use"]["action"])
        self.assertIn("untrusted", steps["use"]["action"])
        self.assertIn("minimize PII and context", steps["use"]["action"])
        self.assertIn("ask for the missing decision", steps["stop_or_remove"]["action"])
        self.assertIn("do not loop through installs", steps["stop_or_remove"]["action"])


class ToolSetupCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.proposal = build_proposal([get_tool("playwright")], "claude", self.project,
                                       "Check an approved local interaction",
                                       "Only the synthetic local fixture", today=TODAY)
        self.saved = self.root / "plan with spaces.json"
        self.saved.write_text(json.dumps(self.proposal), encoding="utf-8")

    def invoke(self, command):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with patch("sys.stdin", io.StringIO()), patch("builtins.input", side_effect=AssertionError("No consent prompt for inert commands")):
                with patch("no_mistakes.toolbox._today", return_value=TODAY):
                    status = main(["toolbox", command, str(self.saved)])
        return status, output.getvalue(), errors.getvalue()

    def test_setup_cli_outputs_digest_bound_inert_workflow_without_prompt_or_config(self):
        status, output, errors = self.invoke("setup")
        self.assertEqual(status, 0, errors)
        self.assertEqual(errors, "")
        result = json.loads(output)
        self.assertEqual(result["digest"], self.proposal["digest"])
        self.assertEqual(result["host"], "claude")
        self.assertEqual(result["steps"][0]["argv"][-1], str(self.saved))
        self.assertEqual(list(self.project.iterdir()), [])

    def test_doctor_cli_missing_config_returns_one_without_enabling_anything(self):
        with patch("no_mistakes.tool_readiness.shutil.which", return_value="/synthetic/bin/launcher"):
            status, output, errors = self.invoke("doctor")
        self.assertEqual(status, 1, errors)
        self.assertEqual(errors, "")
        result = json.loads(output)
        self.assertFalse(result["local_ready"])
        self.assertEqual(result["config"]["status"], "missing")
        self.assertEqual(result["tools"][0]["runtime_status"], "not_checked")
        self.assertEqual(result["tools"][0]["smoke_status"], "not_run")
        self.assertEqual(list(self.project.iterdir()), [])

    def test_doctor_cli_local_match_returns_zero_without_claiming_connection_or_smoke(self):
        target = self.project / self.proposal["target"]
        target.write_text(self.proposal["config"], encoding="utf-8")
        before = target.read_bytes()
        with patch("no_mistakes.tool_readiness.shutil.which", return_value="/synthetic/bin/launcher"):
            status, output, errors = self.invoke("doctor")
        self.assertEqual(status, 0, errors)
        result = json.loads(output)
        self.assertTrue(result["local_ready"])
        self.assertEqual(result["config"]["status"], "matches_proposal")
        self.assertEqual(result["tools"][0]["runtime_status"], "not_checked")
        self.assertEqual(result["tools"][0]["authentication_status"], "not_checked")
        self.assertEqual(result["tools"][0]["smoke_status"], "not_run")
        self.assertEqual(target.read_bytes(), before)
        self.assertNotIn("/synthetic/bin/launcher", output)

    def test_setup_and_doctor_cli_reject_tampered_input_with_exit_two_and_no_partial_json(self):
        self.proposal["config"] += "# unreviewed config\n"
        self.saved.write_text(json.dumps(self.proposal), encoding="utf-8")
        for command in ("setup", "doctor"):
            with self.subTest(command=command):
                status, output, errors = self.invoke(command)
                self.assertEqual(status, 2)
                self.assertEqual(output, "")
                self.assertIn("Proposal changed", errors)
                self.assertNotIn("Traceback", errors)
                self.assertEqual(list(self.project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
