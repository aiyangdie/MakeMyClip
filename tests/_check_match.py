import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db as dbmod, config
db = dbmod.ProjectDB(str(config.DB_DIR / '_stage3_e2e.db'))
res = db.get_match_results()
for sb in db.get_storyboards():
    r = res.get(str(sb['id']), {})
    if '三色温' in sb['name']:
        print(sb['name'], '->', r.get('status'), '|', r.get('reason'))
        print('补拍建议:', r.get('advice'))
print()
print('三色灯素材片段的 cue:')
for c in db.get_clips():
    a = db.get_asset(c['asset_id'])
    if a and '7530' in a['filename']:
        cues = [l['code'] for l in json.loads(c['vision_labels'] or '[]')]
        print(' 片段', c['id'], '%.1f-%.1fs' % (c['start_ms']/1000, c['end_ms']/1000), 'cue=', cues)
