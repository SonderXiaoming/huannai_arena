"""无需启动机器人或连接真实 API 的公开版配置与首次识图检查。"""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "_arena_public_setup_test"


def package(name, path):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    return module


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PublicSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "resources/data"
        self.data.mkdir(parents=True)
        constants = types.ModuleType(f"{PACKAGE}.constants")
        constants.DATA_PATH = self.data
        constants.UNIT_PATTERN = r"^icon_unit_(\d{6}).png$"
        modules = {
            PACKAGE: package(PACKAGE, ROOT),
            f"{PACKAGE}.constants": constants,
            f"{PACKAGE}.pic_recognize": package(
                f"{PACKAGE}.pic_recognize", ROOT / "pic_recognize"
            ),
        }
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings_path = self.root / "setting.py"
        self.settings_path.write_bytes((ROOT / "setting.py").read_bytes())

    def load_settings(self):
        return load_module(f"{PACKAGE}.setting", self.settings_path)

    def test_clean_install_defaults_to_sqlite_without_api_credentials(self):
        settings = self.load_settings()
        self.assertEqual(settings.mzq_config.api, [])
        self.assertEqual(settings.mzq_config.client_key, "")
        self.assertFalse(settings.db_config.use_pgsql)
        self.assertEqual(settings.db_config.arena_pgsql_url, "")
        self.assertEqual(
            settings.db_config.effective_arena_url,
            f"sqlite+aiosqlite:///{self.data / 'arena.db'}",
        )

    def test_local_config_overrides_api_and_postgresql_selection(self):
        config = {
            "mzq": {"api": ["http://127.0.0.1:8888"], "client_key": "test-only"},
            "database": {
                "use_pgsql": True,
                "arena_pgsql_url": "postgresql+asyncpg://localhost/test_only",
                "arena_pool_size": 4,
            },
        }
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        settings = self.load_settings()
        self.assertEqual(settings.mzq_config.client_key, "test-only")
        self.assertEqual(settings.db_config.arena_pool_size, 4)
        self.assertEqual(
            settings.db_config.effective_arena_url,
            config["database"]["arena_pgsql_url"],
        )

    def test_example_config_loads(self):
        (self.root / "config.json").write_bytes(
            (ROOT / "config.example.json").read_bytes()
        )
        settings = self.load_settings()
        self.assertFalse(settings.db_config.use_pgsql)
        self.assertEqual(settings.mzq_config.api, ["http://127.0.0.1:8888"])

    def test_unknown_config_key_is_reported_without_its_value(self):
        settings = self.load_settings()
        config_path = self.root / "invalid.json"
        config_path.write_text(
            json.dumps({"mzq": {"client_keey": "do-not-log-this"}}), encoding="utf-8"
        )
        with self.assertRaises(ValueError) as caught:
            settings.load_local_config(config_path)
        self.assertIn("mzq.client_keey", str(caught.exception))
        self.assertNotIn("do-not-log-this", str(caught.exception))

    def test_first_icon_update_populates_existing_recognizer_reference(self):
        icons = self.root / "icons"
        icons.mkdir()
        Image.new("RGB", (128, 128), "white").save(icons / "icon_unit_100131.png")

        async def get_all_units():
            return {100101: (100, 1)}

        hoshino = types.ModuleType("hoshino")
        hoshino.R = types.SimpleNamespace(
            get=lambda path: types.SimpleNamespace(path=str(icons))
        )
        sqla = types.ModuleType(f"{PACKAGE}.database.sqla")
        sqla.pcr_sqla = types.SimpleNamespace(get_all_units=get_all_units)
        with patch.dict(sys.modules, {
            "hoshino": hoshino,
            f"{PACKAGE}.database": package(f"{PACKAGE}.database", ROOT / "database"),
            f"{PACKAGE}.database.sqla": sqla,
        }):
            dic = load_module(
                f"{PACKAGE}.pic_recognize.dic", ROOT / "pic_recognize/dic.py"
            )
            recognizer_reference = dic.data_processed
            self.assertEqual(recognizer_reference, {})
            asyncio.run(dic.update_dic())
            self.assertIs(dic.data_processed, recognizer_reference)
            self.assertIn(100131, recognizer_reference)
            self.assertTrue(dic.DIC_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
