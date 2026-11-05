"""Constrain generated source references to the controller's actual source set."""
import copy

def bind_references(schema,field,identities):
    result=copy.deepcopy(schema)
    values=list(dict.fromkeys(identities))
    if not all(isinstance(value,str) and value for value in values):raise ValueError('Invalid source identity')
    array=result['properties'][field]
    array['items']={'type':'string',**({'enum':values} if values else {})}
    if not values:array['maxItems']=0
    return result
