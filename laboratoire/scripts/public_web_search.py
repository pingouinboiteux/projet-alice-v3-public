"""Bounded public search, observed results only, page evidence before answering."""
import time

from public_navigation import canonical_url
from public_resources import origin
from public_goal_navigation import read_goal
from public_search_bing import search_public
from web_source_selection import rank_results, compare_evidence

MAX_SECONDS = 120


def validate_results(items):
    if type(items) is not list or len(items) > 8:
        raise ValueError('invalid_search_results')
    seen_ids, seen_urls, result = set(), set(), []
    for item in items:
        if type(item) is not dict or set(item) != {'id', 'title', 'url'}:
            raise ValueError('invalid_search_result')
        if any(type(item[k]) is not str or not item[k].strip() or len(item[k]) > n
               for k, n in [('id', 20), ('title', 300), ('url', 2048)]):
            raise ValueError('invalid_search_fields')
        url = canonical_url(item['url'])
        if item['id'] in seen_ids:
            raise ValueError('duplicate_search_id')
        seen_ids.add(item['id'])
        if url not in seen_urls:
            result.append({**item, 'url': url})
            seen_urls.add(url)
    return result


def read_search(session, question, *, source='text', provider=search_public,
                reader=read_goal, cancelled=lambda: False, clock=time.monotonic):
    if source not in ('text', 'voice'):
        raise ValueError('local_search_required')
    if type(question) is not str or not question.strip() or len(question) > 500:
        raise ValueError('explicit_search_question_required')
    deadline = clock() + MAX_SECONDS
    evidence, attempts = [], []

    def guard():
        session.check()
        if cancelled():
            raise ValueError('search_cancelled')
        if clock() >= deadline:
            raise TimeoutError('search_deadline')

    def reader_cancelled():
        guard()
        return False

    def result(status, reply, **extra):
        return {'status': status, 'reply': reply, 'partial': True,
                'sources': [item['url'] for item in evidence], 'attempts': attempts, **extra}

    try:
        guard()
        try:
            provided = provider(question, guard, deadline=deadline)
        except (RuntimeError, OSError):
            guard()
            return result('failed', 'Le moteur de recherche est indisponible pour cette demande. '
                          'Je n ai pas pu consulter de sources et je ne confirme aucune reponse.')
        items = validate_results(provided)
        guard()
        if not items:
            return result('missing', 'Le moteur ne fournit pas de resultat exploitable pour cette recherche.')
        chosen = rank_results(session, question, items)
        guard()
        for item in chosen:
            guard()
            try:
                page = reader(session, item['url'], question, source=source,
                              cancelled=reader_cancelled, max_pages=2)
                guard()
                if page['status'] not in ('found', 'ambiguous'):
                    attempts.append({'url': item['url'], 'status': page['status'],
                                     'visited': page.get('visited', [])})
                    continue
                # The reader verifies provenance in the observed page. Keep the
                # structured quotes, never parse them back from spoken prose.
                quotes = page.get('evidence')
                if (type(quotes) is not list or not 1 <= len(quotes) <= 3 or
                    any(type(q) is not str or not q.strip() or len(q) > 500 for q in quotes)):
                    raise ValueError('invalid_page_evidence')
                url = canonical_url(page['url'])
                if origin(url) != origin(item['url']):
                    raise ValueError('source_origin_changed')
                evidence.append({'url': url, 'quotes': quotes, 'status': page['status']})
                attempts.append({'url': item['url'], 'status': page['status'],
                                 'visited': page.get('visited', [])})
            except (ValueError, RuntimeError, OSError) as error:
                guard()  # Never swallow stop/FPS/RAM/deadline as a site failure.
                attempts.append({'url': item['url'], 'status': 'failed', 'error_type': type(error).__name__})
        guard()
        if not evidence:
            return result('missing', 'Je n ai pas pu verifier la reponse dans les pages consultees. '
                          'Les resultats du moteur seuls ne suffisent pas pour conclure.')
        relation = 'single'
        if len(evidence) > 1:
            try:
                relation = compare_evidence(session, question, evidence)
            except (ValueError, TypeError, KeyError):
                relation = 'inconclusive'
            guard()
        ambiguous = relation in ('conflicting', 'inconclusive') or any(
            item['status'] == 'ambiguous' for item in evidence)
        if ambiguous:
            prefix = ('Les extraits sont contradictoires ou ne permettent pas de trancher. '
                      'Je te donne les sources sans choisir arbitrairement.\n')
        elif len(evidence) == 1:
            prefix = 'J ai trouve cet extrait dans une seule source ; il n est pas recoupe.\n'
        else:
            prefix = 'Voici les extraits verifies dans les pages consultees.\n'
        body = '\n'.join('Source '+str(i+1)+' : '+item['url']+'\n'+
            '\n'.join('« '+q+' »' for q in item['quotes']) for i, item in enumerate(evidence))
        if any(a['status'] not in ('found', 'ambiguous') for a in attempts):
            body += '\nCertaines pages n ont pas permis de verifier une reponse.'
        return result('ambiguous' if ambiguous else 'found', prefix + body,
                      evidence=evidence, relation=relation)
    except TimeoutError:
        session.check()
        if cancelled():
            raise ValueError('search_cancelled')
        return result('limit', 'Le delai de recherche est atteint. Je m arrete sans confirmer de reponse.')
