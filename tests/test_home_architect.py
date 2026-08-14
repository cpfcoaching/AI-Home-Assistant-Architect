import importlib.util, shutil, subprocess, unittest
from pathlib import Path

try:
    spec=importlib.util.spec_from_file_location("architect",Path(__file__).parents[1]/"home_architect"/"app.py")
    app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
except ModuleNotFoundError: app=None

@unittest.skipIf(app is None,"aiohttp not installed")
class ArchitectTests(unittest.TestCase):
    def test_energy_question_selects_smarthub_context(self):
        states=[{"entity_id":"sensor.smarthub_usage","state":"10","attributes":{"friendly_name":"NOVEC usage","unit_of_measurement":"kWh"}},{"entity_id":"light.kitchen","state":"on","attributes":{}}]
        selected=app.select_context(states,"Why is my electricity cost missing?",50)
        self.assertEqual([x["entity_id"] for x in selected],["sensor.smarthub_usage"])
    def test_context_limit(self):
        states=[{"entity_id":"sensor.solar_%s"%i,"state":"1","attributes":{}} for i in range(10)]
        self.assertEqual(len(app.select_context(states,"solar",3)),3)
    def test_change_request_is_queued(self):
        self.assertTrue(app.change_request("create an automation for the upstairs fan"))
        self.assertFalse(app.change_request("why is solar production low?"))
    def test_account_like_numbers_are_redacted(self):
        self.assertEqual(app.redact("NOVEC 6555863001"),"NOVEC [redacted]")

    def test_browser_uses_explicit_dom_references_and_ingress_path(self):
        self.assertIn("document.getElementById('form')",app.PAGE)
        self.assertIn("formEl.addEventListener('submit'",app.PAGE)
        self.assertIn("basePath+'api/'+name",app.PAGE)
        self.assertNotIn("form.onsubmit",app.PAGE)

    @unittest.skipUnless(shutil.which("node"),"node is not installed")
    def test_generated_browser_script_has_valid_javascript(self):
        script=app.PAGE.split("<script>",1)[1].split("</script>",1)[0]
        result=subprocess.run(["node","--check"],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_root_ingress_api_routes_are_registered(self):
        resources=[resource.canonical for resource in app.app.router.resources()]
        self.assertIn("/api/history",resources)
        self.assertIn("/api/issues",resources)
        self.assertIn("/api/chat",resources)
