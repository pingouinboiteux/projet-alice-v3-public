"""The installed V5 conversation; tests require explicit isolated storage."""
import json
from pathlib import Path
ROOT=(Path(__file__).resolve().parents[2] / 'laboratoire')
def is_memory_control(text):
    """Memory management belongs to the controller, not conversational history."""
    # Natural language is classified once by the local action router. A verb
    # such as "supprime" may concern a workshop file, not personal memories.
    return text.strip() in {'/memoire','/oublier-tout'}

def create_memory(session,user_id='proprietaire',database=None,search=None,backend=None):
    if backend is None:
        config=ROOT/'config/memory_backend.json'
        backend=json.loads(config.read_text(encoding='utf-8'))['backend']
    if backend=='v5_context':
        from .v5_context_memory import V5Conversation as Conversation
        personal=user_id=='proprietaire' and database is None
        if not personal and (not user_id.startswith('validation_') or database is None):
            raise ValueError('Validation memory requires an explicit isolated database')
        if personal:
            database=ROOT/'data/episodic/proprietaire.db'
            database.parent.mkdir(parents=True,exist_ok=True)
        return Conversation(session,user_id,database,search,allow_personal=personal)
    raise ValueError('Unknown memory backend')
