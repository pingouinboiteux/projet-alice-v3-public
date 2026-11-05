"""Process-local ablation: reconnect retrieved dialogue without admitting proof.

Only the benchmark imports this module. Production source stays unchanged.
There is no summary, additional inference, or new personality instruction.
"""
import ast
import hashlib
import inspect
import textwrap


class _Candidate(ast.NodeTransformer):
    def __init__(self):
        self.changed = dict(history=0, payload=0, prebudget=0, final_budget=0, result=0)

    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'history_view'
                and ast.unparse(node.value) == 'list(history[-12:])'):
            self.changed['history'] += 1
            return [node, *ast.parse(
                "_context_dialogue = self.query_kind == 'general_discussion'\n"
                "_conversation_sources = list(selected) if _context_dialogue else []\n"
                "if _context_dialogue and not callable(getattr(self.session, 'count_response_tokens', None)):\n"
                "    raise ValueError('Experimental context requires native schema token counting')\n"
            ).body]
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'payload'
                and ast.unparse(node.value) == "{'archives': shown}"):
            self.changed['payload'] += 1
            return [node, *ast.parse(
                "if _context_dialogue:\n"
                "    conversation = archives_for(_conversation_sources)\n"
                "    if self.compact_dialogue:\n"
                "        from dialogue_context_dedup import compact_recent_archives\n"
                "        conversation = compact_recent_archives(conversation, history_view, getattr(self.episodes, 'current_episode_id', None))\n"
                "    conversation = [item for item in conversation if item.get('messages')]\n"
                "    if conversation:\n"
                "        payload['paroles_passees_non_preuves'] = conversation\n"
            ).body]
        return self.generic_visit(node)

    def visit_If(self, node):
        if (ast.unparse(node.test) == 'callable(counter)'
                and len(node.body) == 1 and isinstance(node.body[0], ast.While)
                and 'evidence_messages(archives, question)' in ast.unparse(node.body[0].test)):
            self.changed['prebudget'] += 1
            node.test = ast.parse('callable(counter) and not _context_dialogue', mode='eval').body
        return self.generic_visit(node)

    def visit_While(self, node):
        if ast.unparse(node.test) == 'final_count(messages) > 5500':
            self.changed['final_budget'] += 1
            branch = node.body[0]
            if not isinstance(branch, ast.If):
                raise RuntimeError('Final budget loop changed; review the candidate')
            while len(branch.orelse) == 1 and isinstance(branch.orelse[0], ast.If):
                branch = branch.orelse[0]
            if len(branch.orelse) != 1 or not isinstance(branch.orelse[0], ast.Raise):
                raise RuntimeError('Final budget refusal changed; review the candidate')
            trim = ast.parse(
                'if _context_dialogue and _conversation_sources:\n'
                '    _conversation_sources.pop()\n'
            ).body[0]
            trim.orelse = branch.orelse
            branch.orelse = [trim]
        return self.generic_visit(node)

    def visit_Return(self, node):
        if (isinstance(node.value, ast.Dict)
                and any(isinstance(key, ast.Constant) and key.value == 'source_provenance'
                        for key in node.value.keys)):
            self.changed['result'] += 1
            node.value.keys.append(None)
            node.value.values.append(ast.parse(
                "({'conversation_context_omitted': len(selected) - len(_conversation_sources)} "
                "if _context_dialogue else {})", mode='eval').body)
        return self.generic_visit(node)


def install():
    """Install in this process only; return a callable restoring Reader.answer."""
    from episodic_memory import Reader

    original = Reader.answer
    if (getattr(original, '_adaptive_context_candidate', False)
            or getattr(original, '_adaptive_history_candidate', False)):
        raise RuntimeError('Use only one adaptive reader candidate at a time')
    source = textwrap.dedent(inspect.getsource(original))
    transform = _Candidate()
    tree = transform.visit(ast.parse(source))
    if transform.changed != dict(history=1, payload=1, prebudget=1, final_budget=1, result=1):
        raise RuntimeError('Reader changed; review the candidate transformation')
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__)
    exec(compile(tree, '<adaptive_context_candidate>', 'exec'), namespace)
    candidate = namespace['answer']
    candidate._adaptive_context_candidate = True
    candidate._baseline_source_sha256 = hashlib.sha256(source.encode('utf-8')).hexdigest()
    Reader.answer = candidate

    def restore():
        if Reader.answer is not candidate:
            raise RuntimeError('Reader was changed again; refusing an unsafe restore')
        Reader.answer = original

    return restore
