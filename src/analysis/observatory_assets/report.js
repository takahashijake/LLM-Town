'use strict';
(() => {
  const data = JSON.parse(document.getElementById('observatory-data').textContent);
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => {const n=document.createElement(tag); if(text !== undefined)n.textContent=String(text); if(cls)n.className=cls; return n;};
  const empty = id => $(id).replaceChildren();
  const json = value => el('pre', JSON.stringify(value,null,2));
  const badge = (text, cls) => el('span',text,'badge '+cls);
  const options = (id, values) => {empty(id); values.forEach(([value,label])=>{const n=el('option',label);n.value=value;$(id).append(n);});};
  let scenario, cp, page=0;
  const views = ['overview','timeline','entities','causes','comparison','assurance'];
  function showView(){const id=views.includes(location.hash.slice(1))?location.hash.slice(1):'overview';
    views.forEach(v=>$(v).classList.toggle('view-hidden',v!==id));
    document.querySelectorAll('nav a').forEach(a=>{if(a.hash==='#'+id)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  }
  window.addEventListener('hashchange',showView);
  const reference = ref => ref.type+': '+ref.id;
  const match = (e,id) => Object.entries(e.fields).some(([k,v]) =>
    (k==='id'||k.endsWith('_id')||k.endsWith('_ids')||k==='location') && (v===id || (Array.isArray(v)&&v.includes(id))));
  const eventNode = e => {const n=el('article',undefined,'record'); n.append(el('strong',(e.day===null?'Undated':'Day '+e.day)+(e.hour===null?'':' · '+e.hour+':00')+' / '+e.source));n.append(el('p',e.authority_id || e.id));const d=el('details');d.append(el('summary','Source: '+e.source_path),json(e.fields));n.append(d);return n;};
  function timeline(){empty('events');const kind=$('category').value, day=$('day').value, id=$('event-id').value;
    const rows=cp.events.filter(e=>(!kind||e.source===kind)&&(day===''||e.day===Number(day))&&(!id||match(e,id)));
    page=Math.max(0,Math.min(page,Math.max(0,Math.ceil(rows.length/20)-1)));
    rows.slice(page*20,page*20+20).forEach(e=>$('events').append(eventNode(e)));
    if(!rows.length)$('events').append(el('p','No matching saved records. Absence is not proof that an event never occurred.'));
    $('page-info').textContent=rows.length+' records · Page '+(page+1)+' of '+Math.max(1,Math.ceil(rows.length/20));
    $('previous').disabled=page===0;$('next').disabled=(page+1)*20>=rows.length;
  }
  function entities(){empty('entity-list');empty('entity-detail');const rows=cp.entities.filter(e=>(!$('entity-type').value||e.type===$('entity-type').value)&&e.id.includes($('entity-search').value));
    rows.forEach(e=>{const b=el('button',e.type+' / '+e.id);b.onclick=()=>showEntity(e);$('entity-list').append(b);});
    if(rows.length)showEntity(rows[0]);else $('entity-detail').append(el('p','No matching entities.'));
  }
  function showEntity(e){empty('entity-detail');$('entity-detail').append(el('h3',e.id),badge(e.evidence,'associated'),el('p','Source: '+e.source_path),json(e.fields));
    const related=cp.events.filter(r=>match(r,e.id));$('entity-detail').append(el('p',related.length+' exact-ID event associations.'));
    const d=el('details');d.append(el('summary','Inspect first 50 associated events'));related.slice(0,50).forEach(r=>d.append(eventNode(r)));$('entity-detail').append(d);
  }
  function trace(){empty('trace-detail');const t=cp.traces[Number($('trace').value)];if(!t){$('trace-detail').append(el('p','No selected causal investigation at this checkpoint. Timeline associations remain available.'));return;}
    $('trace-detail').append(el('p','Root: '+reference(t.root)+' · '+(t.truncated?'Bounded / truncated':'Within requested bounds')));
    t.edges.forEach(e=>{const n=el('article',undefined,'record');n.append(badge('Verified dependency','verified'),el('strong',e.relationship),el('p',reference(e.source)+' → '+reference(e.target)),el('p',e.contract));$('trace-detail').append(n);});
    t.associations.forEach(a=>$('trace-detail').append(badge('Association only','associated'),el('p',reference(a.source)+' ↔ '+reference(a.target)+' / '+a.code)));
    t.unresolved.forEach(u=>$('trace-detail').append(badge('Unresolved','unresolved'),el('p',reference(u.ref)+' / '+u.code)));
    const d=el('details');d.append(el('summary','Evidence nodes, ownership and project audits'),json({nodes:t.nodes,ownership:t.ownership,project_audits:t.project_audits}));$('trace-detail').append(d);
  }
  function diff(){empty('diff');const a=scenario.checkpoints[Number($('before').value)], b=scenario.checkpoints[Number($('after').value)];
    const table=el('table'),head=el('tr');['Metric','Before','After','Change'].forEach(v=>head.append(el('th',v)));table.append(head);
    Object.keys(a.metrics).forEach(k=>{const x=a.metrics[k].value,y=b.metrics[k].value,r=el('tr');[k.replaceAll('_',' '),x===null?'Unknown':x,y===null?'Unknown':y,x===null||y===null?'Unknown':y-x].forEach(v=>r.append(el('td',v)));table.append(r);});
    const wrap=el('div',undefined,'table-wrap');wrap.append(table);$('diff').append(wrap);
    const keyed=p=>new Map(p.entities.map(e=>[e.type+'|'+e.id,e]));const x=keyed(a),y=keyed(b);let changes=0;
    y.forEach((e,k)=>{if(!x.has(k)||JSON.stringify(x.get(k))!==JSON.stringify(e)){changes++;const d=el('details');d.append(el('summary',(!x.has(k)?'Added: ':'Changed: ')+e.type+' / '+e.id),json({before:x.get(k)||null,after:e}));$('diff').append(d);}});
    x.forEach((e,k)=>{if(!y.has(k)){changes++;$('diff').append(el('p','Removed: '+e.type+' / '+e.id));}});if(!changes)$('diff').append(el('p','No public entity state changes.'));
  }
  function checkpoint(){cp=scenario.checkpoints[Number($('checkpoint').value)];page=0;empty('milestones');scenario.checkpoints.forEach((state,index)=>{const b=el('button',state.label.replaceAll('_',' ')+' · '+state.day);b.setAttribute('aria-pressed',String(state===cp));b.onclick=()=>{$('checkpoint').value=String(index);checkpoint();};$('milestones').append(b);});$('checkpoint-info').textContent='Day '+cp.day+' · '+cp.entities.length+' entities · '+cp.events.length+' records';empty('metrics');
    Object.entries(cp.metrics).forEach(([key,m])=>{const n=el('div',undefined,'card'),d=el('details');n.append(el('strong',m.value===null?'Unknown':m.value));d.append(el('summary',key.replaceAll('_',' ')),el('p',m.definition),el('p','Source: '+m.source));n.append(d);$('metrics').append(n);});
    empty('uncertainties');cp.uncertainties.forEach(u=>$('uncertainties').append(badge(u,'unresolved')));
    options('category',[['','All categories'],...Array.from(new Set(cp.events.map(e=>e.source))).sort().map(v=>[v,v])]);
    options('entity-type',[['','All entities'],...Array.from(new Set(cp.entities.map(e=>e.type))).sort().map(v=>[v,v])]);
    options('trace',cp.traces.map((t,i)=>[i,reference(t.root)]));timeline();entities();trace();
  }
  function chooseScenario(){scenario=data.scenarios[Number($('scenario').value)];$('scenario-description').textContent=scenario.description;
    const values=scenario.checkpoints.map((p,i)=>[i,p.label+' · Day '+p.day]);['checkpoint','before','after'].forEach(id=>options(id,values));$('checkpoint').value=String(values.length-1);$('after').value=String(values.length-1);
    empty('verification');$('verification').append(badge('Scenario gates: '+scenario.verification.status,scenario.verification.status==='PASS'?'verified':'associated'),json(scenario.verification),el('p','Public package fingerprint: '+data.fingerprint),el('p','Repository revision: '+data.revision));checkpoint();diff();
  }
  options('scenario',data.scenarios.map((s,i)=>[i,s.title]));$('scenario').onchange=chooseScenario;$('checkpoint').onchange=checkpoint;
  ['category','day','event-id'].forEach(id=>$(id).oninput=()=>{page=0;timeline();});['entity-type','entity-search'].forEach(id=>$(id).oninput=entities);
  $('previous').onclick=()=>{page--;timeline();};$('next').onclick=()=>{page++;timeline();};$('trace').onchange=trace;['before','after'].forEach(id=>$(id).onchange=diff);chooseScenario();showView();
})();
