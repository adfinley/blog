#!/usr/bin/env python3
"""Sync a Notion database to Hugo markdown. Downloads images, reads EXIF, strips metadata."""
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageOps

NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')
OUTPUT_DIR = 'content/posts'
IMAGE_DIR = 'static/images'
NOTION_API = 'https://api.notion.com/v1'
HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json',
}


def query_database():
    url = f'{NOTION_API}/databases/{DATABASE_ID}/query'
    data = {
        'filter': {'property': 'Status', 'status': {'equals': 'Published'}},
        'sorts': [{'property': 'Published Date', 'direction': 'descending'}],
    }
    response = requests.post(url, headers=HEADERS, json=data)
    if not response.ok:
        print(f'Notion said: {response.text}')
    response.raise_for_status()
    return response.json()['results']


def get_page_content(page_id):
    response = requests.get(f'{NOTION_API}/blocks/{page_id}/children?page_size=100', headers=HEADERS)
    response.raise_for_status()
    return response.json()['results']


def rich_text_to_markdown(rich_text):
    out = []
    for t in rich_text or []:
        text, a = t['plain_text'], t['annotations']
        if a['bold']: text = f'**{text}**'
        if a['italic']: text = f'*{text}*'
        if a['code']: text = f'`{text}`'
        if a['strikethrough']: text = f'~~{text}~~'
        if t.get('href'): text = f'[{text}]({t["href"]})'
        out.append(text)
    return ''.join(out)


def read_exif(img):
    """Return a display line like 'Fujifilm X-T5 · lens · 33mm · f/1.4 · 1/1000s · ISO 800'."""
    try:
        ex = img.getexif()
        sub = ex.get_ifd(0x8769)
    except Exception:
        return ''
    make, model = str(ex.get(0x010F, '')).strip(), str(ex.get(0x0110, '')).strip()
    cam = model if model.lower().startswith(make.lower()) else f'{make.title()} {model}'.strip()
    parts = [cam, str(sub.get(0xA434, '')).strip()]
    try:
        if sub.get(0x920A): parts.append(f'{round(float(sub[0x920A]))}mm')
        if sub.get(0x829D): parts.append(f'f/{float(sub[0x829D]):g}')
        if sub.get(0x829A):
            t = float(sub[0x829A])
            parts.append(f'1/{round(1 / t)}s' if t < 1 else f'{t:g}s')
        if sub.get(0x8827): parts.append(f'ISO {sub[0x8827]}')
    except Exception:
        pass
    return ' · '.join(p for p in parts if p)


def save_image(url, block_id, slug, caption):
    """Download once, save a metadata-free JPEG, keep EXIF text and size in a sidecar json."""
    folder = Path(IMAGE_DIR) / slug
    folder.mkdir(parents=True, exist_ok=True)
    name = block_id.replace('-', '')[:8]
    jpg, side = folder / f'{name}.jpg', folder / f'{name}.json'
    if not side.exists():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        exif = read_exif(img)
        icc = img.info.get('icc_profile')
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((2400, 2400))
        # No exif= argument, so GPS and all other metadata are dropped from the published file.
        img.save(jpg, 'JPEG', quality=90, icc_profile=icc)
        w, h = img.size
        side.write_text(json.dumps({'w': w, 'h': h, 'exif': exif}))
    meta = json.loads(side.read_text())
    meta['exif'] = meta.get('exif') or caption  # real EXIF wins; otherwise the current Notion caption
    meta['alt'] = caption
    meta['src'] = f'/images/{slug}/{name}.jpg'
    return meta


def notion_to_markdown(blocks, slug, images):
    md = []
    for block in blocks:
        t = block['type']
        rt = lambda: rich_text_to_markdown(block[t]['rich_text'])
        if t == 'paragraph':
            if rt().strip(): md.append(f'{rt()}\n')
        elif t == 'heading_1': md.append(f'## {rt()}\n')
        elif t == 'heading_2': md.append(f'### {rt()}\n')
        elif t == 'heading_3': md.append(f'#### {rt()}\n')
        elif t == 'bulleted_list_item': md.append(f'- {rt()}\n')
        elif t == 'numbered_list_item': md.append(f'1. {rt()}\n')
        elif t == 'code': md.append(f'```{block[t]["language"]}\n{rt()}\n```\n')
        elif t == 'quote': md.append(f'> {rt()}\n')
        elif t == 'divider': md.append('---\n')
        elif t == 'image':
            url = block['image'].get('file', {}).get('url') or block['image'].get('external', {}).get('url')
            if url:
                caption = rich_text_to_markdown(block['image'].get('caption', []))
                images.append(save_image(url, block['id'], slug, caption))
    return '\n'.join(md)


def plain(prop, kind):
    items = (prop or {}).get(kind) or []
    return items[0]['plain_text'] if items else ''


def extract_properties(page):
    p = page['properties']
    title = plain(p.get('Name') or p.get('Title'), 'title')
    date_prop = p.get('Published Date') or p.get('Date')
    date = date_prop['date']['start'] if date_prop and date_prop.get('date') else datetime.now().isoformat()
    slug = plain(p.get('Slug'), 'rich_text') or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    tags = [x['name'] for x in (p.get('Tags') or {}).get('multi_select', [])]
    cat = (p.get('Category') or {}).get('select')
    ftype = (p.get('Feature type') or {}).get('select')
    return {
        'title': title, 'date': date, 'slug': slug,
        'description': plain(p.get('Description'), 'rich_text'),
        'location': plain(p.get('Location'), 'rich_text'),
        'tags': tags, 'categories': [cat['name'] if cat else 'Uncategorized'],
        'feature_type': ftype['name'] if ftype else 'Landscape',
        'gallery': bool((p.get('Gallery') or {}).get('checkbox')),
    }


def pick_feature(images, ftype):
    """Indexes of the photos shown on the list page, in grid order."""
    land = [i for i, im in enumerate(images) if im['w'] >= im['h']]
    port = [i for i, im in enumerate(images) if im['w'] < im['h']]
    if ftype == 'Mixed gallery' and port and len(land) >= 2:
        return [land[0], port[0], land[1]]
    if ftype == 'Portrait gallery':
        pick = list(range(min(3, len(images))))
        l = [i for i in pick if i in land]
        if len(pick) == 3 and len(l) == 1:  # one landscape among portraits goes in the middle
            pick.remove(l[0]); pick.insert(1, l[0])
        return pick
    return list(range(min(1, len(images))))


def create_hugo_post(props, content, images):
    fm = dict(props)
    slug = fm.pop('slug')
    fm['draft'] = False
    fm['images'] = images
    fm['feature'] = pick_feature(images, props['feature_type'])
    lines = ['---'] + [f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in fm.items()] + ['---', '']
    path = Path(OUTPUT_DIR) / f'{slug}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + content, encoding='utf-8')
    print(f'✓ Created: {path.name} ({len(images)} images)')


def sync():
    print('🔄 Syncing Notion to Hugo...')
    try:
        pages = query_database()
    except Exception as e:
        print(f'❌ Error querying database: {e}')
        sys.exit(1)
    print(f'Found {len(pages)} published posts')
    errors = 0
    for page in pages:
        try:
            props = extract_properties(page)
            images = []
            content = notion_to_markdown(get_page_content(page['id']), props['slug'], images)
            create_hugo_post(props, content, images)
        except Exception as e:
            print(f'✗ Error processing page: {e}')
            errors += 1
    print(f'✅ Done. Errors: {errors}')
    if errors:
        sys.exit(1)


if __name__ == '__main__':
    if not NOTION_TOKEN or not DATABASE_ID:
        print('❌ NOTION_TOKEN or NOTION_DATABASE_ID not set')
        sys.exit(1)
    sync()
