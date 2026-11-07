"""Expose the same trusted schema that the inference engine constrains."""
import json

PREFIX='\nFormat de sortie attendu : retourne un objet JSON conforme au schema suivant. Le schema decrit la structure et les valeurs autorisees, pas des faits a inventer.\n'

ENCODING=(
    ' Lors d une recopie exacte, conserve tous les caracteres du texte demande, '
    'y compris ses fautes, espaces, majuscules et accents. Le seul changement '
    'autorise est l echappement necessaire a l encodage JSON, pas une correction '
    'orthographique ni une normalisation du texte.'
    '\nEncodage JSON : distingue le texte d une valeur de ses delimiteurs. Un guillemet double'
    ' appartenant au texte doit etre echappe par un antislash pour ne pas terminer la valeur.'
    ' Dans le texte de reply, les citations utilisent les guillemets francais « et », sauf '
    'lorsqu une recopie exacte est demandee ; dans ce cas preserve les caracteres et echappe '
    'les guillemets doubles. Ecris le texte complet dans la valeur avant de fermer celle-ci.'
)

def with_response_format(messages,schema):
    if schema is None:return list(messages)
    instruction=(ENCODING if 'reply' in schema.get('properties',{}) else '')+PREFIX+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
    result=[dict(message) for message in messages]
    if result and result[0].get('role')=='system':
        result[0]['content']+=instruction
    else:result.insert(0,{'role':'system','content':instruction.strip()})
    return result

class MemoryResponseSession:
    """Memory adapter sharing the native structured-output contract."""
    def __init__(self,session):self.session=session
    def __getattr__(self,name):return getattr(self.session,name)
    def ask(self,messages,response_schema=None):
        return self.session.ask(with_response_format(messages,response_schema),response_schema=response_schema)
    def count_tokens(self,messages,response_schema=None):
        return self.session.count_tokens(with_response_format(messages,response_schema))
