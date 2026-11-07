"""Read-only rendered DOM for an isolated page bound to an explicit URL.

No network, image capture, page mutation or action dispatch belongs here. The
caller owns browser isolation and process/FPS/RAM guards. This is rendered text,
not pixel vision: overlap, clipping, pseudo-elements, canvas and frames are not
interpreted. Geometry is in CSS pixels relative to the current viewport.
"""
import hashlib
import json
import math
import time
from pathlib import Path
import sys

# The policy remains in the laboratory until its own component migration.
# Use its historical module name, avoiding the two "laboratoire" directories.
_scripts = str(Path(__file__).resolve().parents[2] / 'laboratoire' / 'scripts')
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from action_policy import validate_url

MAX_NODES=5000
MAX_BLOCKS=200
MAX_TEXT=20000

OBSERVE_RENDERED=r"""expectedUrl => {
  if (location.href !== expectedUrl) throw new Error('rendered_scope_changed');
  const limits={nodes:5000,blocks:200,text:20000};
  const entries=[], byElement=new Map();
  let visited=0, collected=0, truncated=false, frame=false, canvas=false, shadow=false;
  const ignored=new Set(['SCRIPT','STYLE','TEMPLATE','NOSCRIPT','FORM','INPUT','TEXTAREA','SELECT','OPTION']);
  function shown(element) {
    let depth=0;
    for (let e=element; e; e=e.parentElement) {
      if (++depth>256) {truncated=true;return false;}
      if (ignored.has(e.tagName) || e.hidden || e.getAttribute('aria-hidden')==='true' ||
          e.isContentEditable || ['textbox','searchbox','combobox'].includes(e.getAttribute('role'))) return false;
      const style=getComputedStyle(e);
      if (style.display==='none' || style.visibility==='hidden' || style.visibility==='collapse' || Number(style.opacity)===0) return false;
    }
    return true;
  }
  const root=document.body;
  if (root) {
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
    let node;
    while ((node=walker.nextNode())) {
      if (++visited>limits.nodes) {truncated=true;break;}
      if (node.nodeType===Node.ELEMENT_NODE) {
        frame=frame||node.tagName==='IFRAME'||node.tagName==='FRAME';
        canvas=canvas||node.tagName==='CANVAS';shadow=shadow||Boolean(node.shadowRoot);
        continue;
      }
      const raw=node.textContent;
      if (raw.length>limits.text) truncated=true;
      let text=raw.slice(0,limits.text).replace(/\s+/g,' ').trim();
      if (!text || !node.parentElement || !shown(node.parentElement)) continue;
      const range=document.createRange();range.selectNodeContents(node);
      const rectangles=Array.from(range.getClientRects());
      if (!rectangles.some(r=>r.width>0 && r.height>0)) continue;
      const element=node.parentElement.closest('tr,p,h1,h2,h3,h4,h5,h6,li,dt,dd,pre,blockquote') ||
                    node.parentElement.closest('button,a,div,body') || node.parentElement;
      let entry=byElement.get(element),newBlock=false;
      if (!entry) {
        if (entries.length>=limits.blocks) {truncated=true;break;}
        const tag=element.tagName.toLowerCase();
        const role=tag==='tr'?'row':/^h[1-6]$/.test(tag)?'heading':tag==='li'?'listitem':
                   tag==='button'?'button':tag==='a'?'link':tag==='p'?'paragraph':'text';
        entry={element,role,parts:[],lastCell:null};entries.push(entry);byElement.set(element,entry);newBlock=true;
      }
      const cell=entry.role==='row'?node.parentElement.closest('td,th'):null;
      const separator=entry.parts.length?(cell && cell!==entry.lastCell?' | ':' '):'';
      const overhead=separator.length+(newBlock && entries.length>1?1:0);
      const available=limits.text-collected-overhead;
      if (available<=0) {truncated=true;if(newBlock) entries.pop();break;}
      if (text.length>available) {text=text.slice(0,available);truncated=true;}
      entry.parts.push(separator+text);entry.lastCell=cell;
      collected+=overhead+text.length;
      if (collected>=limits.text) {truncated=true;break;}
    }
  }
  let used=0;
  const blocks=[];
  for (const entry of entries) {
    let text=entry.parts.join('');
    const available=limits.text-used-(blocks.length?1:0);
    if (available<=0) {truncated=true;break;}
    if (text.length>available) {text=text.slice(0,available);truncated=true;}
    const rect=entry.element.getBoundingClientRect();
    const rounded=n=>Math.round(n*1000)/1000;
    const bounds={x:rounded(rect.x),y:rounded(rect.y),width:rounded(rect.width),height:rounded(rect.height)};
    blocks.push({text,role:entry.role,bounds,in_viewport:rect.bottom>0&&rect.right>0&&rect.top<innerHeight&&rect.left<innerWidth});
    used+=text.length+(blocks.length>1?1:0);
    if (used>=limits.text) {if(entries.length>blocks.length) truncated=true;break;}
  }
  const limitations=['occlusion_and_complex_clipping_not_resolved','pseudo_elements_and_images_not_read'];
  if(frame) limitations.push('frames_not_read');
  if(canvas) limitations.push('canvas_not_read');
  if(shadow) limitations.push('shadow_dom_not_read');
  return {url:location.href,text:blocks.map(b=>b.text).join('\n'),blocks,truncated,limitations};
}"""

def _expected_url(value):
    if type(value) is not str:raise ValueError('explicit_rendered_url_required')
    if value!='about:blank':validate_url(value)
    return value


def _validate(value,expected_url='about:blank'):
    _expected_url(expected_url)
    if type(value) is not dict or set(value)!={'url','text','blocks','truncated','limitations'}:
        raise ValueError('invalid_rendered_snapshot')
    if value['url']!=expected_url or type(value['text']) is not str or len(value['text'])>MAX_TEXT:
        raise ValueError('invalid_rendered_scope_or_text')
    if type(value['truncated']) is not bool or type(value['blocks']) is not list or len(value['blocks'])>MAX_BLOCKS:
        raise ValueError('invalid_rendered_budget')
    limitations=value['limitations']
    if (type(limitations) is not list or len(limitations)>8 or
            any(type(item) is not str or len(item)>100 for item in limitations)):
        raise ValueError('invalid_rendered_limitations')
    for block in value['blocks']:
        if type(block) is not dict or set(block)!={'text','role','bounds','in_viewport'}:
            raise ValueError('invalid_rendered_block')
        if (type(block['text']) is not str or not block['text'] or len(block['text'])>MAX_TEXT or
                block['role'] not in ('row','heading','listitem','button','link','paragraph','text') or
                type(block['in_viewport']) is not bool):
            raise ValueError('invalid_rendered_block_values')
        bounds=block['bounds']
        if type(bounds) is not dict or set(bounds)!={'x','y','width','height'}:
            raise ValueError('invalid_rendered_bounds')
        if any(type(n) not in (int,float) or not math.isfinite(n) for n in bounds.values()):
            raise ValueError('invalid_rendered_geometry')
        if bounds['width']<0 or bounds['height']<0:
            raise ValueError('invalid_rendered_geometry')
    if '\n'.join(block['text'] for block in value['blocks'])!=value['text']:
        raise ValueError('rendered_text_mismatch')
    return value

def _revision(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def observe_page(page,guard,clock=time.monotonic,*,expected_url='about:blank'):
    """Return a bounded snapshot of rendered text; all guard failures propagate."""
    if not callable(guard):raise TypeError('active_guard_required')
    guard()
    _expected_url(expected_url)
    if page.url!=expected_url:raise ValueError('rendered_scope_changed')
    observed_at=clock()
    if type(observed_at) not in (int,float) or not math.isfinite(observed_at):
        raise ValueError('invalid_observation_clock')
    value=page.evaluate(OBSERVE_RENDERED,expected_url)
    guard()
    if page.url!=expected_url:raise ValueError('rendered_scope_changed')
    value=_validate(value,expected_url)
    return {**value,'revision':_revision(value),'observed_at':observed_at}

def check_snapshot(page,guard,snapshot,max_age=2,clock=time.monotonic,*,expected_url='about:blank'):
    """Return False for expired, modified or malformed snapshots; propagate guards.

    A successful check returns True after a fresh DOM observation. It cannot
    guarantee the page will remain unchanged after the check; no action executes.
    """
    guard()
    try:
        _expected_url(expected_url)
        if type(max_age) not in (int,float) or not math.isfinite(max_age) or max_age<=0:
            return False
        if type(snapshot) is not dict or set(snapshot)!={'url','text','blocks','truncated','limitations','revision','observed_at'}:
            return False
        stamp=snapshot['observed_at'];now=clock()
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=max_age:
            return False
        original={k:v for k,v in snapshot.items() if k not in ('revision','observed_at')}
        if _revision(_validate(original,expected_url))!=snapshot['revision']:return False
    except (ValueError,TypeError,KeyError):return False
    fresh=observe_page(page,guard,clock,expected_url=expected_url)
    return fresh['revision']==snapshot['revision'] and 0<=clock()-stamp<=max_age
