import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
APPS = (
    "solar_sentinel",
    "climate_balancer",
    "energy_troubleshooter",
    "home_architect",
)
S6_RULES = (
    "/init ix,",
    "/bin/** ix,",
    "/usr/bin/** ix,",
    "/run/{s6,s6-rc*,service}/** ix,",
    "/package/** ix,",
    "/command/** ix,",
    "/run/{,**} rwk,",
    "/run.sh rix,",
)


class AppPackagingTests(unittest.TestCase):
    def test_all_apps_include_s6_apparmor_runtime(self):
        for app in APPS:
            profile = (ROOT / app / "apparmor.txt").read_text()
            for rule in S6_RULES:
                with self.subTest(app=app, rule=rule):
                    self.assertIn(rule, profile)

    def test_all_apps_use_packaged_alpine_python(self):
        for app in APPS:
            run_script = (ROOT / app / "run.sh").read_text()
            with self.subTest(app=app):
                self.assertIn("exec /usr/bin/python3 /app/app.py", run_script)

    def test_all_apps_disable_docker_init_for_s6(self):
        for app in APPS:
            config = (ROOT / app / "config.yaml").read_text()
            with self.subTest(app=app):
                self.assertIn("init: false", config)


if __name__ == "__main__":
    unittest.main()
