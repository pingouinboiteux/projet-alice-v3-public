"""Candidate: bounded link observations, bound to the caller's explicit page URL.

Only visible anchor labels and literal hrefs are observed. No clicks, guessed
URLs, event handlers, form submissions or model-written selectors are executed.
"""
import hashlib
import json
import math
import time
from urllib.parse import urljoin
from pathlib import Path
import sys

# URL contracts remain in the laboratory until their own migration.
_scripts = str(Path(__file__).resolve().parents[2] / 'laboratoire' / 'scripts')
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from public_navigation import canonical_url
from public_resources import origin

MAX_LINKS=100
LINKS_JS=r"""expected => {
  if(location.href !== expected) throw new Error('link_scope_changed');
  const links=[];let nodes=0,truncated=false;
  function visible(e) {
    let depth=0;
    for(let p=e;p;p=p.parentElement) {
      if(++depth>256) {truncated=true;return false;}
      if(p.hidden || p.getAttribute('aria-hidden')==='true' || p.isContentEditable ||
         ['FORM','INPUT','TEXTAREA','SELECT'].includes(p.tagName)) return false;
      const s=getComputedStyle(p);
      if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0) return false;
    }
    return Array.from(e.getClientRects()).some(r=>r.width>0&&r.height>0);
  }
  if(document.body) {
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_ELEMENT);
    let e;
    while((e=walker.nextNode())) {
      if(++nodes>5000) {truncated=true;break;}
      if(e.tagName!=='A'||!e.hasAttribute('href')||!visible(e)) continue;
      const href=e.getAttribute('href');
      if(href.length>2048) {truncated=true;continue;}
      const label=e.innerText.replace(/\s+/g,' ').trim();
      // Observe long card captions completely, even when they are too long
      // for a named-link request. They must not hide unrelated short links.
      if(label.length>1000) {truncated=true;continue;}
      if(!label) continue;
      if(links.length>=100) {truncated=true;break;}
      links.push({label,href,...(e.hasAttribute('download')?{download:true}:{})});
    }
  }
  return {url:location.href,links,truncated};
}"""

def _validated(value,expected):
    if type(value) is not dict or set(value)!={'url','links','truncated'}:
        raise ValueError('invalid_link_snapshot')
    if value['url']!=expected or type(value['truncated']) is not bool:
        raise ValueError('link_scope_changed')
    if type(value['links']) is not list or len(value['links'])>MAX_LINKS:
        raise ValueError('link_budget_exceeded')
    for link in value['links']:
        if type(link) is not dict or set(link) not in ({'label','href'},{'label','href','download'}):
            raise ValueError('invalid_link')
        if 'download' in link and link['download'] is not True:raise ValueError('invalid_link')
        if any(type(link[k]) is not str or len(link[k])>limit
               for k,limit in [('label',1000),('href',2048)]) or not link['label'].strip():
            raise ValueError('invalid_link_values')
    return value

def _revision(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':')).encode()).hexdigest()

def observe_links(page,guard,*,expected_url,clock=time.monotonic):
    canonical_url(expected_url);guard()
    if page.url!=expected_url:raise ValueError('link_scope_changed')
    now=clock()
    if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('invalid_link_clock')
    value=_validated(page.evaluate(LINKS_JS,expected_url),expected_url)
    guard()
    if page.url!=expected_url:raise ValueError('link_scope_changed')
    return {**value,'revision':_revision(value),'observed_at':now}

def links_current(page,guard,snapshot,*,expected_url,clock=time.monotonic):
    guard()
    try:
        if type(snapshot) is not dict or set(snapshot)!={'url','links','truncated','revision','observed_at'}:return False
        stamp=snapshot['observed_at'];now=clock()
        if any(type(n) not in (int,float) or not math.isfinite(n) for n in (stamp,now)):return False
        if not 0<=now-stamp<=10:return False
        value=_validated({k:snapshot[k] for k in ('url','links','truncated')},expected_url)
        if _revision(value)!=snapshot['revision']:return False
    except (ValueError,TypeError,KeyError):return False
    return observe_links(page,guard,expected_url=expected_url,clock=clock)['revision']==snapshot['revision']

def select_link(snapshot,label):
    if type(label) is not str or not label.strip() or len(label)>200:
        raise ValueError('explicit_link_label_required')
    value=_validated({k:snapshot[k] for k in ('url','links','truncated')},snapshot['url'])
    # An unseen duplicate beyond the budget must not silently select a link.
    if value['truncated']:raise ValueError('incomplete_link_inventory')
    key=lambda s:' '.join(s.split()).casefold()
    matches=[link for link in value['links'] if key(link['label'])==key(label)]
    if len(matches)!=1:raise ValueError('link_missing_or_ambiguous')
    if matches[0].get('download'):raise ValueError('download_link_refused')
    href=matches[0]['href'].strip()
    if href.startswith('#') or any(ord(c)<32 for c in href):raise ValueError('unsupported_link')
    target=canonical_url(urljoin(value['url'],href))
    if origin(target)!=origin(value['url']):raise ValueError('cross_origin_link_refused')
    if target==canonical_url(value['url']):raise ValueError('same_page_link')
    return target
