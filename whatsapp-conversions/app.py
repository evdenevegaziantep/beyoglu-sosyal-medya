#!/usr/bin/env python3
"""Beyoğlu Nakliyat — Click-to-WhatsApp conversion webhook.

Receives WhatsApp Cloud API webhooks, stores no raw message text, captures ctwa_clid,
and reports qualified lead / booking outcomes to Meta Conversions API.
Secrets are read only from environment variables and are never logged.
"""
from __future__ import annotations
import hashlib, hmac, json, os, sqlite3, time, urllib.error, urllib.request
from pathlib import Path
from flask import Flask, jsonify, request

GRAPH_VERSION=os.getenv('GRAPH_VERSION','v26.0')
VERIFY_TOKEN=os.getenv('WEBHOOK_VERIFY_TOKEN','')
APP_SECRET=os.getenv('META_APP_SECRET','')
ADMIN_KEY=os.getenv('ADMIN_KEY','')
CAPI_TOKEN=os.getenv('CAPI_ACCESS_TOKEN','')
DATASET_ID=os.getenv('META_DATASET_ID','')
HASH_SALT=os.getenv('PII_HASH_SALT','')
DB_PATH=Path(os.getenv('DB_PATH','/var/data/whatsapp-conversions.sqlite3'))
app=Flask(__name__)

def db():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH);c.row_factory=sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS leads(
      id TEXT PRIMARY KEY, ctwa_clid TEXT NOT NULL, wa_id_hash TEXT,
      first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'message', message_count INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL,
      event_name TEXT NOT NULL, event_time INTEGER NOT NULL,
      currency TEXT, value REAL, meta_status TEXT NOT NULL,
      meta_response TEXT, UNIQUE(lead_id,event_name,event_time)
    );
    ''');return c

def safe_hash(value:str)->str:
    return hmac.new((HASH_SALT or 'configure-a-private-salt').encode(),value.encode(),hashlib.sha256).hexdigest()

def lead_id(click_id:str)->str:return hashlib.sha256(click_id.encode()).hexdigest()[:20]

def valid_signature(raw:bytes)->bool:
    if not APP_SECRET:return os.getenv('ALLOW_UNSIGNED_WEBHOOKS','false').lower()=='true'
    got=request.headers.get('X-Hub-Signature-256','')
    want='sha256='+hmac.new(APP_SECRET.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(got,want)

def upsert_lead(click_id:str,wa_id:str='',timestamp:int|None=None)->str:
    now=timestamp or int(time.time());lid=lead_id(click_id);c=db()
    c.execute('''INSERT INTO leads(id,ctwa_clid,wa_id_hash,first_seen,last_seen,status,message_count)
      VALUES(?,?,?,?,?,'message',1)
      ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,
      message_count=leads.message_count+1,
      wa_id_hash=COALESCE(excluded.wa_id_hash,leads.wa_id_hash)''',
      (lid,click_id,safe_hash(wa_id) if wa_id else None,now,now));c.commit();c.close();return lid

def report_event(lid:str,event_name:str,event_time:int|None=None,value:float|None=None,currency='TRY')->dict:
    c=db();lead=c.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone()
    if not lead:c.close();raise KeyError('lead not found')
    event_time=event_time or int(time.time())
    payload={'data':[{'event_name':event_name,'event_time':event_time,
      'action_source':'business_messaging','messaging_channel':'whatsapp',
      'user_data':{'ctwa_clid':lead['ctwa_clid']},
      'messaging_outcome_data':{'outcome_type':'manual_business_status'}}]}
    if value is not None:payload['data'][0]['custom_data']={'currency':currency,'value':float(value)}
    status='pending_configuration';response=''
    if DATASET_ID and CAPI_TOKEN:
      req=urllib.request.Request(
        f'https://graph.facebook.com/{GRAPH_VERSION}/{DATASET_ID}/events',
        data=json.dumps(payload).encode(),method='POST',
        headers={'Content-Type':'application/json','Authorization':'Bearer '+CAPI_TOKEN})
      try:
        with urllib.request.urlopen(req,timeout=60) as r:
          result=json.load(r);status='sent';response=json.dumps({'events_received':result.get('events_received'),'fbtrace_id':result.get('fbtrace_id')})
      except urllib.error.HTTPError as exc:
        status='error';response=f'HTTP {exc.code}'
      except Exception as exc:
        status='error';response=type(exc).__name__
    c.execute('INSERT OR IGNORE INTO events(lead_id,event_name,event_time,currency,value,meta_status,meta_response) VALUES(?,?,?,?,?,?,?)',(lid,event_name,event_time,currency,value,status,response))
    new_status={'LeadSubmitted':'lead','QualifiedLead':'qualified','Purchase':'booked'}.get(event_name)
    if new_status:c.execute('UPDATE leads SET status=? WHERE id=?',(new_status,lid))
    c.commit();c.close();return {'lead_id':lid,'event_name':event_name,'meta_status':status}

@app.get('/health')
def health():return jsonify({'ok':True,'dataset_configured':bool(DATASET_ID and CAPI_TOKEN)})

@app.get('/webhook')
def verify():
    if request.args.get('hub.mode')=='subscribe' and VERIFY_TOKEN and hmac.compare_digest(request.args.get('hub.verify_token',''),VERIFY_TOKEN):
      return request.args.get('hub.challenge',''),200,{'Content-Type':'text/plain'}
    return 'forbidden',403

@app.post('/webhook')
def webhook():
    raw=request.get_data(cache=True)
    if not valid_signature(raw):return jsonify({'error':'invalid signature'}),401
    body=request.get_json(silent=True) or {};processed=0
    for entry in body.get('entry',[]):
      for change in entry.get('changes',[]):
        value=change.get('value') or {}
        for msg in value.get('messages') or []:
          ref=msg.get('referral') or {};click=ref.get('ctwa_clid')
          if click:
            lid=upsert_lead(click,msg.get('from',''),int(msg.get('timestamp') or time.time()));processed+=1
            # A complete address/date/route qualification is marked later by the business.
        for ev in value.get('automatic_events') or []:
          click=ev.get('ctwa_clid');name=ev.get('event_name')
          if click and name:
            lid=upsert_lead(click,'',int(ev.get('timestamp') or time.time()));custom=ev.get('custom_data') or {}
            report_event(lid,name,int(ev.get('timestamp') or time.time()),custom.get('value'),custom.get('currency','TRY'));processed+=1
    return jsonify({'received':True,'processed':processed})

def admin_ok()->bool:return bool(ADMIN_KEY) and hmac.compare_digest(request.headers.get('X-Admin-Key',''),ADMIN_KEY)

@app.get('/admin/leads')
def leads():
    if not admin_ok():return jsonify({'error':'forbidden'}),403
    c=db();rows=c.execute('SELECT id,first_seen,last_seen,status,message_count FROM leads ORDER BY last_seen DESC LIMIT 100').fetchall();c.close()
    return jsonify({'data':[dict(r) for r in rows]})

@app.post('/admin/leads/<lid>/qualified')
def qualified(lid):
    if not admin_ok():return jsonify({'error':'forbidden'}),403
    try:return jsonify(report_event(lid,'QualifiedLead'))
    except KeyError:return jsonify({'error':'not found'}),404

@app.post('/admin/leads/<lid>/booked')
def booked(lid):
    if not admin_ok():return jsonify({'error':'forbidden'}),403
    value=request.get_json(silent=True) or {};amount=value.get('value')
    try:return jsonify(report_event(lid,'Purchase',value=float(amount) if amount is not None else None))
    except KeyError:return jsonify({'error':'not found'}),404

@app.get('/admin/summary')
def summary():
    if not admin_ok():return jsonify({'error':'forbidden'}),403
    c=db();rows=c.execute('SELECT status,COUNT(*) n FROM leads GROUP BY status').fetchall();ev=c.execute('SELECT meta_status,COUNT(*) n FROM events GROUP BY meta_status').fetchall();c.close()
    return jsonify({'leads':{r['status']:r['n'] for r in rows},'events':{r['meta_status']:r['n'] for r in ev}})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))
