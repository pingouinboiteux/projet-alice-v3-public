"""Closed local turns. Only code-owned outcomes, never model/tool prose."""
from collections import deque
import json


class ActionContext:
    def __init__(self):
        self.turns=deque(maxlen=6)

    def clear(self):
        self.turns.clear()

    def record(self,text,kind,outcome):
        if outcome not in {'processed','refused','cancelled','failed','dialogue'}:
            raise ValueError('Etat action invalide')
        self.turns.append((text[:5000],json.dumps({'turn_state':'closed','action':kind,
            'outcome':outcome,'pending_action':False},ensure_ascii=False)))

    def messages(self,system):
        result=[{'role':'system','content':system}]
        for text,state in self.turns:
            result.extend([{'role':'user','content':text},{'role':'assistant','content':state}])
        return result
