"""Opt-in, process-local dialogue-history ablation; never imported by Alice.

The checked AST transformation keeps the production reader on disk unchanged.
No generated summary, extra model call, or change to factual reading is added.
"""
import ast
import hashlib
import inspect
import textwrap


def _complete_pairs(history):
    if len(history) % 2 or any(
        message['role'] != ('user' if index % 2 == 0 else 'assistant')
        for index, message in enumerate(history)
    ):
        raise ValueError('Experimental dialogue history must contain complete user/assistant pairs')
    return history


class _Candidate(ast.NodeTransformer):
    def __init__(self):
        self.changed = {'history': 0, 'prebudget': 0, 'final_budget': 0}

    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'history_view'
                and ast.unparse(node.value) == 'list(history[-12:])'):
            self.changed['history'] += 1
            return ast.parse(
                "_budget_dialogue = self.query_kind == 'general_discussion'\n"
                "history_view = (_candidate_complete_pairs(list(history)) if _budget_dialogue "
                "else list(history[-12:]))\n"
                "if _budget_dialogue and not callable(getattr(self.session, 'count_response_tokens', None)):\n"
                "    raise ValueError('Experimental history requires native schema token counting')\n"
            ).body
        return self.generic_visit(node)

    def visit_If(self, node):
        if (ast.unparse(node.test) == 'callable(counter)'
                and len(node.body) == 1 and isinstance(node.body[0], ast.While)
                and 'evidence_messages(archives, question)' in ast.unparse(node.body[0].test)):
            self.changed['prebudget'] += 1
            node.test = ast.parse('callable(counter) and not _budget_dialogue', mode='eval').body
        return self.generic_visit(node)

    def visit_While(self, node):
        branches = [statement for statement in node.body if isinstance(statement, ast.If)
                    and ast.unparse(statement.test) == 'include_extras']
        if ast.unparse(node.test) == 'True' and branches:
            self.changed['final_budget'] += 1
            # Insert after extras/context removal and before the original refusal.
            # The native final loop now rebuilds schema, routing and messages on
            # each pass; preserve that body and its measurement/exit unchanged.
            exits = [statement for statement in node.body if isinstance(statement, ast.If)
                     and ast.unparse(statement.test) == 'tokens <= 5500'
                     and len(statement.body) == 1 and isinstance(statement.body[0], ast.Break)]
            if len(branches) != 1 or len(exits) != 1:
                raise RuntimeError('Final budget loop changed; review the candidate')
            branch = branches[0]
            while len(branch.orelse) == 1 and isinstance(branch.orelse[0], ast.If):
                branch = branch.orelse[0]
            if len(branch.orelse) != 1 or not isinstance(branch.orelse[0], ast.Raise):
                raise RuntimeError('Final budget refusal changed; review the candidate')
            trim = ast.parse(
                'if _budget_dialogue and history_view:\n'
                '    history_view = history_view[2:]\n'
            ).body[0]
            trim.orelse = branch.orelse
            branch.orelse = [trim]
        return self.generic_visit(node)


def install():
    """Patch only this Python process; return a callable restoring the reader."""
    from episodic_memory import Reader

    original = Reader.answer
    if getattr(original, '_adaptive_history_candidate', False):
        raise RuntimeError('Adaptive history candidate is already installed')
    source = textwrap.dedent(inspect.getsource(original))
    tree = ast.parse(source)
    transform = _Candidate()
    tree = transform.visit(tree)
    if transform.changed != {'history': 1, 'prebudget': 1, 'final_budget': 1}:
        raise RuntimeError('Reader changed; review the candidate transformation')
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__)
    namespace['_candidate_complete_pairs'] = _complete_pairs
    exec(compile(tree, '<adaptive_history_candidate>', 'exec'), namespace)
    candidate = namespace['answer']
    candidate._adaptive_history_candidate = True
    candidate._baseline_source_sha256 = hashlib.sha256(source.encode('utf-8')).hexdigest()
    Reader.answer = candidate

    def restore():
        if Reader.answer is not candidate:
            raise RuntimeError('Reader was changed again; refusing an unsafe restore')
        Reader.answer = original

    return restore
