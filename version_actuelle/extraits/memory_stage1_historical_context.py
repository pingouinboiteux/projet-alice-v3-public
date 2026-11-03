"""Source history without generated operational validity decisions."""
import copy
from memory_stage1_coverage import build_interaction
from memory_stage1_account import validate as validate_facts
from memory_stage1_scoped_interaction import _read
from memory_response_format import PREFIX,with_response_format

KINDS=['request','permission','preference','boundary']
CONTRACT='''
Chaque interaction rapporte une intention dans son contexte. Les mots qui
organisent ou rectifient la parole ne constituent pas automatiquement une demande
d'action. Dans kind, request signifie que l'utilisateur demande une action,
permission qu'il la permet sans l'exiger, preference ce qu'il aime ou souhaite
habituellement, boundary une limite qu'il pose. Le texte garde cette modalite.
Une simple information ou un projet rapporte va dans facts, pas dans interaction.
Dans context, rapporte l'occasion, les conditions et leur evolution explicitement
rapportee dans l'ensemble de l'echange. Conserve une fin indiquee et une portee
non precisee comme telles, sans completer ce qui n'est pas etabli.
Ce releve decrit des propos historiques : il ne decide pas de leur validite
actuelle ou future et ne les transforme pas en consignes operationnelles.'''


def build(messages):
    wire,schema=build_interaction(messages)
    schema=copy.deepcopy(schema)
    item=schema['properties']['interaction']['items']
    item['properties'].update(kind={'type':'string','enum':KINDS},
        context={'type':'string','minLength':1})
    item['required']+=['kind','context']
    prompt=wire[0]['content'].split(PREFIX,1)[0]
    old='Dans facts, formule chaque information utile en une phrase autonome.'
    new=('Dans facts, formule chaque information rapportee en une phrase autonome, '
         'y compris les informations ponctuelles et les situations terminees. '
         'La selection des souvenirs est une etape ulterieure : ici, la priorite '
         'est la conservation du contenu.')
    if prompt.count(old)!=1:raise ValueError('Unrecognized reading contract')
    wire[0]['content']=prompt.replace(old,new)+CONTRACT
    return with_response_format(wire,schema),schema


def validate(value,messages):
    if not isinstance(value,dict) or set(value)!={'facts','unresolved','interaction'}:
        raise ValueError('Invalid historical reading')
    validate_facts({k:value[k] for k in ['facts','unresolved']},messages)
    items=value['interaction']
    if not isinstance(items,list) or len(items)>12:raise ValueError('Invalid historical interactions')
    for item in items:
        if not isinstance(item,dict) or set(item)!={'text','sources','kind','context'}:
            raise ValueError('Invalid historical interaction fields')
        if item['kind'] not in KINDS or not isinstance(item['context'],str) or not item['context'].strip():
            raise ValueError('Invalid historical context')
        validate_facts({'facts':[{k:item[k] for k in ['text','sources']}],'unresolved':[]},messages)
    return value


def read(session,profile,messages):
    return _read(session,profile,messages,build,validate)
