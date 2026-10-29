"""Rebuildable FTS5 and corpus-derived latent semantic search; no model key required."""
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from collections import Counter

from learning import terms
from research_sources import normalize_id

MAX_CHUNKS = 2000
MAX_FILE_BYTES = 5_000_000
MAX_TEXT_CHARS = 500_000


def within(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('资料路径超出仓库')
    return path


def documents(root, config, stats=None):
    root = Path(root).resolve()
    stats = stats if stats is not None else {}
    stats.setdefault('skipped_files', 0)
    stats.setdefault('truncated_files', 0)
    paths = config.get('paths', {})
    scanned = 0
    for name, default in [('notes_dir', 'Notes'), ('papers_dir', 'Papers'), ('pdfs_dir', 'pdfs')]:
        folder = within(root, paths.get(name, default))
        if not folder.is_dir():
            continue
        # os.walk never follows directory symlinks and bounds scanning independently of hits.
        for directory, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not (Path(directory) / name).is_symlink())
            for filename in sorted(files):
                scanned += 1
                if scanned > 5000:
                    stats['scan_truncated'] = True
                    return
                path = Path(directory) / filename
                if path.suffix.lower() not in {'.md', '.txt', '.pdf'}:
                    continue
                if not path.is_file() or not path.resolve().is_relative_to(folder) or path.stat().st_size > MAX_FILE_BYTES:
                    stats['skipped_files'] += 1
                    continue
                text = ''
                try:
                    if path.suffix.lower() in {'.md', '.txt'}:
                        with path.open(encoding='utf-8', errors='replace') as stream:
                            text = stream.read(MAX_TEXT_CHARS + 1)
                    else:
                        try:
                            from pypdf import PdfReader
                            from pypdf.errors import PyPdfError
                        except ImportError:
                            stats['skipped_files'] += 1
                            continue
                        try:
                            pdf = PdfReader(path)
                            if len(pdf.pages) > 100:
                                stats['truncated_files'] += 1
                            text = '\n'.join((page.extract_text() or '')[:20000] for page in pdf.pages[:100])
                        except PyPdfError:
                            stats['skipped_files'] += 1
                            continue
                except (OSError, ValueError):
                    stats['skipped_files'] += 1
                    continue
                if len(text) > MAX_TEXT_CHARS:
                    stats['truncated_files'] += 1
                text = text[:MAX_TEXT_CHARS]
                if text.strip():
                    yield (path.relative_to(root).as_posix(), normalize_id(path.stem) or '', '', text)

    # Full text is irreplaceable evidence; index it before rebuildable abstracts.
    db = within(root, config.get('storage', {}).get('sqlite', {}).get('path', 'data/arxiv.db'))
    if db.is_file():
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute('SELECT arxiv_id,title,summary,category FROM papers ORDER BY arxiv_id LIMIT 3000'):
                paper_id = str(row['arxiv_id'])
                yield ('arxiv:' + paper_id, paper_id, row['category'] or '', str(row['title'] or '') + '\n' + str(row['summary'] or ''))


def _build(root, config, target):
    with sqlite3.connect(target) as conn:
        conn.executescript('CREATE VIRTUAL TABLE chunks USING fts5(path UNINDEXED,paper_id UNINDEXED,category UNINDEXED,line UNINDEXED,text,tokens); CREATE TABLE semantic(key TEXT PRIMARY KEY,value TEXT);')
        counters = []
        stats = {}
        source_count = 0
        for path, paper_id, category, text in documents(root, config, stats):
            source_count += 1
            for start in range(0, len(text), 1500):
                chunk = text[start:start + 1500]
                if not chunk.strip():
                    continue
                words = terms(chunk)
                line = text.count('\n', 0, start) + 1
                conn.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)', (path, paper_id, category, line, chunk, ' '.join(words)))
                counters.append(Counter(words))
                if len(counters) >= MAX_CHUNKS:
                    break
            if len(counters) >= MAX_CHUNKS:
                break
        mode = 'fts'
        try:
            import numpy as np
            counts = Counter(t for counter in counters for t in counter)
            vocab = sorted(counts, key=lambda t: (-counts[t], t))[:4000]
            if len(vocab) >= 3 and len(counters) >= 3:
                idf = np.array([math.log((1 + len(counters)) / (1 + counts[t])) + 1 for t in vocab])
                matrix = np.array([[math.log1p(c[t]) for t in vocab] for c in counters]) * idf
                # Bounded randomized SVD: deterministic, at most 32 latent dimensions.
                width = min(32, len(counters), len(vocab))
                projection = np.random.default_rng(0).normal(size=(len(vocab), min(width + 8, len(vocab))))
                q, _ = np.linalg.qr(matrix @ projection)
                _, _, vt = np.linalg.svd(q.T @ matrix, full_matrices=False)
                axes = vt[:width].T
                vectors = matrix @ axes
                vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
                for key, value in [('vocab', vocab), ('idf', idf.tolist()), ('axes', axes.tolist()), ('vectors', vectors.tolist())]:
                    conn.execute('INSERT INTO semantic VALUES(?,?)', (key, json.dumps(value)))
                mode = 'fts+lsa'
        except ImportError:
            pass
        return {'chunks': len(counters), 'documents': source_count, 'mode': mode, 'limit': MAX_CHUNKS,
                'truncated': len(counters) >= MAX_CHUNKS, 'max_file_bytes': MAX_FILE_BYTES,
                'max_text_chars': MAX_TEXT_CHARS, **stats}


def build(root, config, target):
    """Build to a temporary file and replace only a known index, preserving it on failure."""
    root = Path(root).resolve()
    target = Path(target)
    db = within(root, config.get('storage', {}).get('sqlite', {}).get('path', 'data/arxiv.db'))
    if target.is_symlink() or target.resolve() == db or target.suffix.lower() not in {'.sqlite', '.db'}:
        raise ValueError('索引目标无效或指向论文数据库')
    if target.exists():
        with sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'chunks', 'semantic'} <= names:
                raise ValueError('目标不是研究索引，已停止以避免覆盖数据')
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.research-index-', suffix='.sqlite', dir=target.parent)
    os.close(handle)
    try:
        report = _build(root, config, name)
        os.replace(name, target)
        return report
    finally:
        if os.path.exists(name):
            os.unlink(name)


def search(target, query, category='', path_prefix=''):
    if not isinstance(query, str) or len(query) > 2000 or not isinstance(category, str) or not isinstance(path_prefix, str):
        raise ValueError('检索参数无效或查询过长')
    counts = Counter(terms(query))
    words = list(counts)[:30]
    if not words:
        return []
    with sqlite3.connect(Path(target).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        filters, values = [], []
        if category:
            filters.append('category=?')
            values.append(category)
        if path_prefix:
            filters.append('substr(path,1,length(?))=?')
            values.extend((path_prefix, path_prefix))
        where = (' AND ' + ' AND '.join(filters)) if filters else ''
        allowed = {row['rowid'] for row in conn.execute('SELECT rowid FROM chunks WHERE 1=1' + where, values)}
        if not allowed:
            return []
        fts = ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)
        lexical = conn.execute('SELECT rowid FROM chunks WHERE chunks MATCH ?' + where + ' ORDER BY bm25(chunks) LIMIT 100', [fts] + values).fetchall()
        scores = {row['rowid']: 1 / (60 + i) for i, row in enumerate(lexical, 1)}
        try:
            import numpy as np
            semantic = {row['key']: json.loads(row['value']) for row in conn.execute('SELECT * FROM semantic')}
            if semantic:
                vector = np.array([math.log1p(counts[t]) for t in semantic['vocab']]) * semantic['idf']
                vector = vector @ np.array(semantic['axes'])
                norm = np.linalg.norm(vector)
                if norm:
                    similarities = np.array(semantic['vectors']) @ (vector / norm)
                    ordered = sorted((rowid for rowid in allowed if rowid <= len(similarities) and similarities[rowid - 1] > 0.05), key=lambda rowid: (-similarities[rowid - 1], rowid))[:100]
                    for i, rowid in enumerate(ordered, 1):
                        scores[rowid] = scores.get(rowid, 0) + 1 / (60 + i)
        except ImportError:
            pass
        results = []
        for rowid in sorted(scores, key=lambda key: (-scores[key], key))[:10]:
            row = dict(conn.execute('SELECT rowid,* FROM chunks WHERE rowid=?', (rowid,)).fetchone())
            text = row.pop('text')
            row.pop('tokens', None)
            at = min((text.lower().find(word) for word in words if word in text.lower()), default=0)
            start = max(0, at - 80)
            row.update(snippet=text[start:start + 600], line=int(row['line']) + text.count('\n', 0, start), score=round(scores[rowid], 6), arxiv_id=row.pop('paper_id'))
            results.append(row)
        return results
