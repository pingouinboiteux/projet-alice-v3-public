"""Reference the current exchange once, keeping its identity and recording date."""

TURN_CONTINUITY=('Les repliques precedentes ont deja ete dites a la personne. '
    'Reponds au dernier message et conserve ce qui est deja acquis. '
    'Evite de recommencer la meme explication ou de reposer une question deja '
    'posee sans nouvel element qui le justifie. Une question restee sans reponse '
    'ne doit pas etre reposee automatiquement au tour suivant. '
    'Si la personne demande une repetition, une citation, une confirmation ou '
    'un rappel, donne bien les informations demandees, meme deja mentionnees.')
def compact_recent_archives(archives,history,current_episode_id):
    history=list(history)
    kept=[]
    for archive in archives:
        messages=archive.get('messages')
        starts=[start for start in range(max(0,len(history)-len(messages)+1))
            if history[start:start+len(messages)]==messages] if messages else []
        if archive.get('id')==current_episode_id and starts:
            reference={key:value for key,value in archive.items() if key not in {'messages','paroles_de_la_personne'}}
            reference['echange_deja_present_dans_historique_recent']={
                'premier_message':starts[-1]+1,'nombre_messages':len(messages)}
            kept.append(reference)
        else:kept.append(archive)
    return kept
