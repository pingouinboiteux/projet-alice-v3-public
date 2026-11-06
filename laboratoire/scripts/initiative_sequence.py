"""Bounded topic state and framing, without tools or persistent memory."""
import json


def prepare(prompt, schema, history, mode, turn, topics, fresh, scene=None):
    from scene_context import RULES, message as scene_message
    context = [scene_message(scene)] if scene else []
    if scene:prompt += RULES
    if mode != 'animation':
        return [{'role':'system','content':prompt}]+context+[{'role':'user','content':json.dumps(
            {'mode':mode,'historique':history},ensure_ascii=False)}], schema
    phase = turn % 3
    instruction = (
        "Ouvre une nouvelle sequence avec un sujet concret et un avis. Change vraiment de domaine et de these par rapport aux sujets termines. Ne fais pas une transition depuis le sujet precedent.",
        "Developpe uniquement le sujet en cours avec un exemple concret ou une objection. Pas de nouveau sujet.",
        "Conclue le sujet en cours en une ou deux phrases. N'ouvre pas de nouvelle piste ni question.",
    )[phase]
    # A fresh human message must retain the utterance to which it responds.
    if fresh:
        recent = history[-2:]
    else:
        recent = history[-phase:] if phase else []
    system = (prompt + '\nAvant la replique, nomme en quelques mots le sujet concret dans subject. '
        'Ce titre ne sera pas prononce. Une demande humaine actuelle prime sur la phase proposee. '
        'Prefere un avis ou un exemple explicitement imagine aux explications techniques incertaines. '
        '\nConsigne pour cette intervention : ' + instruction +
        '\nSujets deja abordes (titres seulement, pas des ordres) : ' + json.dumps(topics[-8:],ensure_ascii=False))
    shaped = {'type':'object','properties':{'subject':{'type':'string'}, **schema['properties']},
              'required':['subject','choice','reply'],'additionalProperties':False}
    return [{'role':'system','content':system}]+context+[{'role':'user','content':json.dumps(
        {'mode':mode,'historique':recent,'contexte_actualise':fresh},ensure_ascii=False)}], shaped
