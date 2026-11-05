"""No OAuth, network, memory or posting: account identity is untrusted data."""
import ast
from pathlib import Path
from types import SimpleNamespace


def test_authenticated_account_is_forwarded_like_any_other_viewer():
    # Isolate credential imports: the test must never open a real vault.
    path=Path(__file__).resolve().parents[1]/'scripts/twitch_reader.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='chat_message')
    scope={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    event=SimpleNamespace(chatter_user_id='validation_owner',
        chatter_user_name='validation_owner',message=SimpleNamespace(text='Alice bonjour'))
    assert scope['chat_message'](event)=={'kind':'chat','author':'validation_owner',
        'display_name':'validation_owner','text':'Alice bonjour'}
