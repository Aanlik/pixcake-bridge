# coding: utf-8
import subprocess,time,json,secrets,hashlib
from pathlib import Path
import httpx
from PIL import Image
root=Path.cwd();(root/'outputs/verification').mkdir(parents=True,exist_ok=True);f=root/'work/nas-folder-fixture';shoot=f/'Camera/关联测试';shoot.mkdir(parents=True,exist_ok=True)
for i in range(100): Image.new('RGB',(64,48),(i,80,160)).save(shoot/f'DSC{i:05}.JPG')
if not (f/'Camera/outside').is_symlink(): (f/'Camera/outside').symlink_to('/data')
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in shoot.iterdir()}
name='pixcake-folder-picpeak'
subprocess.run(['docker','run','--platform','linux/amd64','-d','--name',name,'-p','127.0.0.1:19309:3000','-e','NO_EMAIL_MODE=true','-e','EXTERNAL_MEDIA_ROOT=/external-media','-e','EXTERNAL_MEDIA_WATCH_POLLING=true','-e','EXTERNAL_MEDIA_WATCH_RECONCILE_INTERVAL_MS=1000','-e','EXTERNAL_MEDIA_WATCH_SWEEP_INTERVAL_MS=2000','-e','EXTERNAL_MEDIA_WATCH_POLL_INTERVAL_MS=1000','-v','pixcake-folder-test-data:/data','-v',str(f)+':/external-media:ro','picpeak-zh:3.134.1-zh.5'],check=True,stdout=subprocess.DEVNULL)
p=httpx.Client(base_url='http://127.0.0.1:19309',timeout=90)
for _ in range(60):
 try:
  if p.get('/health').status_code==200:break
 except httpx.HTTPError:pass
 time.sleep(1)
token=subprocess.check_output(['docker','exec',name,'cat','/data/db/SETUP_TOKEN'],text=True).strip()
password='FixtureA9!'+secrets.token_hex(16)
r=p.post('/api/setup/admin',json={'token':token,'username':'fixture','email':'fixture@example.com','password':password});assert r.status_code==201,r.text
r=p.post('/api/admin/events',json={'event_name':'NAS 文件夹关联测试','event_type':'other','event_date':'2026-10-08','customer_name':'测试客户','require_password':False});assert r.status_code in (200,201),r.text
eid=r.json()['id'];slug=r.json()['slug']
r=p.get('/api/admin/external-media/list',params={'path':'Camera'});assert r.status_code==200 and [x['name'] for x in r.json()['entries']]==['关联测试'],r.text
assert p.get('/api/admin/external-media/list',params={'path':'../data'}).status_code==400
assert p.get('/api/admin/external-media/list',params={'path':'Camera/outside'}).status_code==400
url=f'/api/admin/external-media/events/{eid}/import-external'
r=p.post(url,json={'external_path':'Camera/关联测试','recursive':True});assert r.status_code==200 and r.json()['imported']==100,r.text
r=p.put(f'/api/admin/events/{eid}',json={'external_watch':True});assert r.status_code==200,r.text
ids={x['id'] for x in p.get(f'/api/admin/events/{eid}/photos',params={'limit':200}).json()['photos']}
r=p.post(url,json={'external_path':'Camera/关联测试','recursive':True});assert r.status_code==200 and r.json()['imported']==0 and r.json()['skipped']==100,r.text
Image.new('RGB',(64,48),(120,20,60)).save(shoot/'追加.JPG')
for _ in range(45):
 d=p.get(f'/api/admin/events/{eid}/photos',params={'limit':200}).json()['photos']
 if len(d)==101:break
 time.sleep(1)
assert len(d)==101 and ids.issubset({x['id'] for x in d}),len(d)
res=subprocess.run(['docker','exec',name,'sh','-c','touch /external-media/Camera/关联测试/readonly-test'],capture_output=True);assert res.returncode!=0 and b'Read-only file system' in res.stderr
assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in shoot.iterdir() if p.name in before}
(root/'work/nas-folder-private.json').write_text(json.dumps({'password':password,'event_id':eid}));(root/'work/nas-folder-private.json').chmod(0o600)
result={'image':'picpeak-zh:3.134.1-zh.5','initial_import':100,'repeat_import':0,'automatic_added':1,'existing_photo_ids_preserved':100,'original_sha256_unchanged':100,'readonly_write_rejected':True,'traversal_and_symlink_rejected':True}
(root/'outputs/verification/nas-folder-container.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
