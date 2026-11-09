"""Non-configurable runtime restrictions for the protected autonomy perimeter."""
CODE_REFUSAL = ('Execution de code desactivee dans cette voie. '
                'Les missions /faire passent uniquement par la fenetre locale '
                'Alice-Laboratoire et son atelier MXC verifie. Aucun terminal libre '
                'ni installation sur Windows par cette voie.')
BROWSER_REFUSAL = ('Ouverture dans le navigateur personnel desactivee dans le mode protege. '
                   'Demande plutot une recherche Internet : Alice utilise son navigateur isole '
                   'sans tes comptes personnels.')


def require_standard_user():
    import sys
    if sys.platform == 'win32':
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            raise PermissionError('Alice protegee doit etre lancee sans droits administrateur.')
