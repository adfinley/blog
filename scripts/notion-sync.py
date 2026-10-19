#!/usr/bin/env python3
"""Sync a Notion database to Hugo markdown. Downloads images, reads EXIF, strips metadata."""
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

try:  # lets Pillow open HEIC photos (e.g. dragged from Apple Photos)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

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
    """Return (display line, date of capture) from the photo's EXIF."""
    try:
        ex = img.getexif()
        sub = ex.get_ifd(0x8769)
    except Exception:
        return '', ''
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
    raw = str(sub.get(0x9003) or ex.get(0x0132) or '')
    try:
        dt = datetime.strptime(raw[:19], '%Y:%m:%d %H:%M:%S')
        date = f'{dt:%B} {dt.day}, {dt.year}'
    except ValueError:
        date = ''
    return ' · '.join(p for p in parts if p), date


def save_image(url, block_id, slug, caption):
    """Download once, save a metadata-free JPEG, keep EXIF text, date and size in a sidecar json."""
    folder = Path(IMAGE_DIR) / slug
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(block_id.encode()).hexdigest()[:10]
    jpg, side = folder / f'{name}.jpg', folder / f'{name}.json'
    if not side.exists() or 'date' not in json.loads(side.read_text()):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        exif, date = read_exif(img)
        icc = img.info.get('icc_profile')
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((2400, 2400))
        # No exif= argument, so GPS and all other metadata are dropped from the published file.
        img.save(jpg, 'JPEG', quality=90, icc_profile=icc)
        w, h = img.size
        side.write_text(json.dumps({'w': w, 'h': h, 'exif': exif, 'date': date}))
    meta = json.loads(side.read_text())
    meta['exif'] = meta.get('exif') or caption  # real EXIF wins; otherwise the current Notion caption
    meta['alt'] = caption
    meta['src'] = f'/images/{slug}/{name}.jpg'
    return meta


def save_video(url, block_id, slug):
    """Download an uploaded video next to the post's images and return a shortcode that plays it."""
    folder = Path(IMAGE_DIR) / slug
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(block_id.encode()).hexdigest()[:10]
    path = folder / (name + (Path(urlparse(url).path).suffix.lower() or '.mp4'))
    if not path.exists():
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            if int(r.headers.get('Content-Length', 0)) > 90 * 1024 * 1024:
                raise ValueError('video is over 90 MB (GitHub rejects files over 100 MB)')
            with open(path, 'wb') as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    return '{{< video src="images/' + slug + '/' + path.name + '" >}}\n'


def video_markdown(url):
    m = re.search(r'(?:youtu\.be/|v=|embed/|shorts/)([\w-]{11})', url)
    if 'youtu' in url and m:
        return '{{< youtube ' + m.group(1) + ' >}}\n'
    m = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
    if m:
        return '{{< vimeo ' + m.group(1) + ' >}}\n'
    return f'[{url}]({url})\n'


def notion_to_markdown(blocks, slug, images, gallery=True):
    """Images at the top of the page become the featured gallery; later images stay inline, in order."""
    md, leading = [], gallery
    for block in blocks:
        t = block['type']
        rt = lambda: rich_text_to_markdown(block[t]['rich_text'])
        if t == 'paragraph' and not rt().strip():
            continue
        if t == 'image':
            url = block['image'].get('file', {}).get('url') or block['image'].get('external', {}).get('url')
            if not url:
                continue
            caption = rich_text_to_markdown(block['image'].get('caption', []))
            try:
                im = save_image(url, block['id'], slug, caption)
            except Exception as e:
                print(f'⚠ Skipped an image in {slug}: {e}')
                continue
            if leading:
                images.append(im)
            else:
                md.append(f'![{caption or "Image"}]({im["src"]})\n')
            continue
        leading = False
        if t == 'paragraph': md.append(f'{rt()}\n')
        elif t == 'heading_1': md.append(f'## {rt()}\n')
        elif t == 'heading_2': md.append(f'### {rt()}\n')
        elif t == 'heading_3': md.append(f'#### {rt()}\n')
        elif t == 'bulleted_list_item': md.append(f'- {rt()}\n')
        elif t == 'numbered_list_item': md.append(f'1. {rt()}\n')
        elif t == 'code': md.append(f'```{block[t]["language"]}\n{rt()}\n```\n')
        elif t == 'quote': md.append(f'> {rt()}\n')
        elif t == 'divider': md.append('---\n')
        elif t == 'column_list':  # Notion columns: fetch each column's blocks, render side by side
            cols = []
            for col in get_page_content(block['id']):
                inner = notion_to_markdown(get_page_content(col['id']), slug, images, gallery=False).strip()
                cols.append(f'<div class="col">\n\n{inner}\n\n</div>')
            md.append('<div class="cols">\n' + '\n'.join(cols) + '\n</div>\n')
        elif t in ('video', 'embed', 'bookmark', 'link_preview'):
            d = block[t]
            url = d.get('url') or d.get('external', {}).get('url') or d.get('file', {}).get('url') or ''
            if d.get('type') == 'file' and url:  # uploaded video: keep a copy, Notion links expire
                try:
                    md.append(save_video(url, block['id'], slug))
                except Exception as e:
                    print(f'⚠ Skipped a video in {slug}: {e}')
            elif url:
                md.append(video_markdown(url))
        else:
            print(f'⚠ Skipped an unsupported "{t}" block in {slug}')
    return '\n'.join(md)


def plain(prop, kind):
    items = (prop or {}).get(kind) or []
    return items[0]['plain_text'] if items else ''


def extract_properties(page):
    p = page['properties']
    title = plain(p.get('Name') or p.get('Title'), 'title')
    date_prop = p.get('Published Date') or p.get('Date')
    date = date_prop['date']['start'] if date_prop and date_prop.get('date') else datetime.now().isoformat()
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or 'post-' + page['id'].replace('-', '')[:8]
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
    """Return (indexes of the photos shown on the list page in grid order, grid name).
    Gallery types adapt to the orientation of the first three photos."""
    n = len(images)
    if 'gallery' not in ftype.lower() or n < 2:
        return list(range(min(1, n))), 'single'
    idx = list(range(min(3, n)))
    if len(idx) == 2:
        return idx, 'pair'
    port = [i for i in idx if images[i]['w'] < images[i]['h']]
    land = [i for i in idx if i not in port]
    if len(port) == 3:
        return idx, 'columns'
    if len(port) == 2:
        if idx[1] in land:           # portrait, landscape, portrait
            return idx, 'columns'
        return port + land, 'split'  # two portraits tall-left + cropped top-right, landscape bottom-right
    if len(port) == 1:
        return [land[0], port[0], land[1]], 'mixed'
    return idx, 'split'              # three landscapes


def create_hugo_post(props, content, images):
    fm = dict(props)
    slug = fm.pop('slug')
    fm['draft'] = False
    fm['images'] = images
    fm['feature'], fm['grid'] = pick_feature(images, props['feature_type'])
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
