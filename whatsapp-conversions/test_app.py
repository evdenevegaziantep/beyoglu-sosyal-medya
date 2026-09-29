#!/usr/bin/env python3
import hashlib,hmac,importlib,os,tempfile,unittest
TMP=tempfile.NamedTemporaryFile(suffix='.sqlite3',delete=False);TMP.close()
os.environ.update({'WEBHOOK_VERIFY_TOKEN':'verify-test','META_APP_SECRET':'secret-test','ADMIN_KEY':'admin-test','PII_HASH_SALT':'salt-test','DB_PATH':TMP.name,'ALLOW_UNSIGNED_WEBHOOKS':'false'})
appmod=importlib.import_module('app')

def signed(client,payload):
 import json
 raw=json.dumps(payload,separators=(',',':')).encode();sig='sha256='+hmac.new(b'secret-test',raw,hashlib.sha256).hexdigest()
 return client.post('/webhook',data=raw,headers={'Content-Type':'application/json','X-Hub-Signature-256':sig})
class TestWebhook(unittest.TestCase):
 def setUp(self):self.c=appmod.app.test_client()
 def test_verify(self):
  r=self.c.get('/webhook?hub.mode=subscribe&hub.verify_token=verify-test&hub.challenge=123');self.assertEqual(r.status_code,200);self.assertEqual(r.text,'123')
 def test_bad_signature(self):self.assertEqual(self.c.post('/webhook',json={}).status_code,401)
 def test_ctwa_and_crm(self):
  p={'entry':[{'changes':[{'value':{'messages':[{'from':'905461111111','timestamp':'1780000000','referral':{'ctwa_clid':'click-abc'}}]}}]}]}
  r=signed(self.c,p);self.assertEqual(r.status_code,200);self.assertEqual(r.json['processed'],1)
  rows=self.c.get('/admin/leads',headers={'X-Admin-Key':'admin-test'}).json['data'];self.assertEqual(len(rows),1);lid=rows[0]['id']
  q=self.c.post(f'/admin/leads/{lid}/qualified',headers={'X-Admin-Key':'admin-test'});self.assertEqual(q.status_code,200);self.assertEqual(q.json['meta_status'],'pending_configuration')
  s=self.c.get('/admin/summary',headers={'X-Admin-Key':'admin-test'}).json;self.assertEqual(s['leads']['qualified'],1)
if __name__=='__main__':unittest.main()
