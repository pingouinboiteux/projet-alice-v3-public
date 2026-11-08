"""Non-configurable runtime restrictions for the protected autonomy perimeter."""
CODE_REFUSAL = ('Execution de code desactivee sur le PC dans le mode protege. '
                'Alice peut preparer du texte, mais aucun terminal, script, installation '
                'ou agent de programmation ne sera lance. Les essais de code exigent '
                'un environnement Windows separe et verifie.')
BROWSER_REFUSAL = ('Ouverture dans le navigateur personnel desactivee dans le mode protege. '
                   'Demande plutot une recherche Internet : Alice utilise son navigateur isole '
                   'sans tes comptes personnels.')


def require_standard_user():
    import sys
    if sys.platform == 'win32':
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            raise PermissionError('Alice protegee doit etre lancee sans droits administrateur.')
