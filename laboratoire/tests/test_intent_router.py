import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from intent_router import decode


class IntentBoundary(unittest.TestCase):
    def test_reject_unknown_actions_and_wrong_types(self):
        for raw in ['{"kind":"shell","value":"calc.exe","reply":"oui"}',
                    '{"kind":"volume","value":true,"reply":"oui"}',
                    '{"kind":"volume","value":101,"reply":"oui"}',
                    '{"kind":"open","value":"file:///C:/Windows","reply":"oui"}',
                    '{"kind":"status","value":null,"reply":"ok","command":"evil"}']:
            with self.assertRaises(ValueError):
                decode(raw)

    def test_readonly_status_and_bounded_change(self):
        self.assertEqual(decode('{"kind":"status","value":null,"reply":""}')[0].kind, 'status')
        self.assertEqual(decode('{"kind":"volume","value":30,"reply":"Proposition"}')[0].value, 30)


if __name__ == '__main__':
    unittest.main()
