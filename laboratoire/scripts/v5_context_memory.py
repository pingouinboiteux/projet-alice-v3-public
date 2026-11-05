"""Original Alice storage/search foundations with full contextual source evidence.

No fact extraction or generated summary is installed as permanent truth.
The V5 lexical vocabulary supplements the existing semantic shortlist without
displacing baseline hits. Input budgeting may remove whole hints from the end.
No source is rewritten and no action is issued.
"""
import json
from local_memory_store import _search_tokens
from episodic_memory import Episodes,Reader
from episode_conversation import Conversation
from reviewed_memory_reader import ReviewedReader,RANK


class V5Episodes(Episodes):
    def candidates(self,question,limit=16):
        if type(limit) is not int or not 1<=limit<=24:
            raise ValueError('Invalid candidate limit')
        baseline=super().candidates(question,min(limit,12))
        if len(baseline)>=limit:return baseline
        terms=_search_tokens(question)
        if not terms:return baseline
        ranked=[]
        for row in self.db.execute('SELECT * FROM episodes'):
            source=self._decode(row)
            # Assistant replies are context, never lexical evidence of user facts.
            matches=[]
            for message in source['messages']:
                if message['role']!='user':continue
                for start in range(0,len(message['content']),450):
                    excerpt=message['content'][start:start+600]
                    overlap=len(terms & _search_tokens(excerpt))
                    if overlap:matches.append((overlap,excerpt))
                    if start+600>=len(message['content']):break
            if not matches:continue
            overlap,excerpt=max(matches,key=lambda item:item[0])
            source['search_excerpt']=excerpt
            # Original V5 coverage/overlap ranking, with deterministic recency ties.
            score=4*overlap/len(terms)+overlap
            ranked.append((score,source['date'],source['id'],source))
        found={e['id'] for e in baseline}
        for _,_,identity,source in sorted(ranked,key=lambda item:item[:3],reverse=True):
            if identity not in found:
                baseline.append(source);found.add(identity)
                if len(baseline)>=limit:break
        return baseline


class CarefulMemoryReader(Reader):
    compact_dialogue=True
    progress_dialogue=True
    def __init__(self,session,episodes,query_kind=None):
        super().__init__(session,episodes,query_kind,memory_reasoning=True)


class V5Reader(ReviewedReader):
    reader_type=CarefulMemoryReader
    retained_retrieval=2
    def candidate_sources(self,question):
        candidates=self.episodes.candidates(question,limit=16)
        counter=getattr(self.session,'count_tokens',None)
        if callable(counter):
            # Drop search hints from the end, never crop source evidence. The four
            # optional lexical additions are dropped before baseline candidates.
            while candidates:
                hints=[{'id':e['id'],'date':e['date'],'extrait_incomplet':e['search_excerpt']} for e in candidates]
                messages=[{'role':'system','content':RANK},{'role':'user','content':json.dumps(
                    {'question':question,'indices':hints},ensure_ascii=False)}]
                if counter(messages)<=5500:break
                candidates.pop()
        return candidates


class V5Conversation(Conversation):
    episodes_type=V5Episodes
    reader_type=V5Reader
