import unittest

try:
    from cogs.general import GeneralCog
except ModuleNotFoundError:
    GeneralCog = None


@unittest.skipUnless(GeneralCog is not None, "discord.py no esta instalado en este entorno")
class GeneralCommandTests(unittest.TestCase):
    def test_bot_info_command_is_registered(self):
        self.assertEqual(
            GeneralCog.info.name,
            "bot-info",
        )


if __name__ == "__main__":
    unittest.main()
