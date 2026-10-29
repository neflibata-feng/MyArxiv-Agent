"""Rebuildable FTS5 and corpus-derived latent semantic search; no model key required."""
import json
import math
from pathlib import Path
import sqlite3
from collections import Counter

from learning import terms
from research_sources import normalize_id


def within(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('资料路径超出仓库')
    return path


def documents(root, config):
    db = within(root, config.get('storage', {}).get('sqlite', {}).get('path', 'data/arxiv.db'))
    if db.is_file():
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute('SELECT arxiv_id,title,summary,category FROM papers ORDER BY arxiv_id LIMIT 3000'):
                yield ('arxiv:' + row['arxiv_id'], row['arxiv_id'], row['category'], row['title'] + '\n' + row['summary'])
    paths = config.get('paths', {})
    for name, default in [('notes_dir', 'Notes'), ('papers_dir', 'Papers'), ('pdfs_dir', 'pdfs')]:
        folder = within(root, paths.get(name, default))
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or not path.resolve().is_relative_to(folder) or path.stat().st_size > 5_000_000:
                continue
            text = ''
            if path.suffix.lower() in {'.md', '.txt'}:
                text = path.read_text(encoding='utf-8', errors='replace')[:500_000]
            elif path.suffix.lower() == '.pdf':
                try:
                    from pypdf import PdfReader
                    pdf = PdfReader(path)
                    text = '\n'.join((page.extract_text() or '')[:20000] for page in pdf.pages[:100])[:500_000]
                except (ImportError, OSError, ValueError):
                    continue
            if text.strip():
                yield (path.relative_to(root).as_posix(), normalize_id(path.stem) or '', '', text)


def build(root, config, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        conn.executescript('DROP TABLE IF EXISTS chunks; DROP TABLE IF EXISTS semantic; CREATE VIRTUAL TABLE chunks USING fts5(path UNINDEXED,paper_id UNINDEXED,category UNINDEXED,line UNINDEXED,text); CREATE TABLE semantic(key TEXT PRIMARY KEY,value TEXT);')
        counters = []
        for path, paper_id, category, text in documents(root, config):
            offset = 0
            for start in range(0, len(text), 1500):
                chunk = text[start:start + 1500]
                if not chunk.strip():
                    continue
                line = text.count('\n', 0, start) + 1
                conn.execute('INSERT INTO chunks VALUES(?,?,?,?,?)', (path, paper_id, category, line, chunk))
                counters.append(Counter(terms(chunk)))
                offset += 1
                if len(counters) >= 2000:
                    break
            if len(counters) >= 2000:
                break
        mode = 'fts'
        try:
            import numpy as np
            counts = Counter(t for counter in counters for t in counter)
            vocab = sorted(counts, key=lambda t: (-counts[t], t))[:4000]
            if len(vocab) >= 3 and len(counters) >= 3:
                idf = np.array([math.log((1 + len(counters)) / (1 + counts[t])) + 1 for t in vocab])
                matrix = np.array([[math.log1p(c[t]) for t in vocab] for c in counters]) * idf
                # Bounded randomized SVD: deterministic across rebuilds, at most 32 dimensions.
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
        return {'chunks': len(counters), 'mode': mode, 'limit': 2000, 'truncated': len(counters) >= 2000}


def search(target, query, category='', path_prefix=''):
    words = list(dict.fromkeys(terms(query)))[:30]
    if not words:
        return []
    with sqlite3.connect(target) as conn:
        conn.row_factory = sqlite3.Row
        fts = ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)
        lexical = conn.execute('SELECT rowid FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT 100', (fts,)).fetchall()
        scores = {row['rowid']: 1 / (60 + i) for i, row in enumerate(lexical, 1)}
        try:
            import numpy as np
            values = {row['key']: json.loads(row['value']) for row in conn.execute('SELECT * FROM semantic')}
            if values:
                vector = np.array([math.log1p(words.count(t)) for t in values['vocab']]) * values['idf']
                vector = vector @ np.array(values['axes'])
                norm = np.linalg.norm(vector)
                if norm:
                    similarities = np.array(values['vectors']) @ (vector / norm)
                    for i, row in enumerate(np.argsort(-similarities)[:100], 1):
                        if similarities[row] > 0.05:
                            scores[int(row) + 1] = scores.get(int(row) + 1, 0) + 1 / (60 + i)
        except ImportError:
            pass
        results = []
        for rowid in sorted(scores, key=lambda key: (-scores[key], key)):
            row = dict(conn.execute('SELECT rowid,* FROM chunks WHERE rowid=?', (rowid,)).fetchone())
            if category and row['category'] != category:
                continue
            if path_prefix and not row['path'].startswith(path_prefix):
                continue
            text = row.pop('text')
            at = min((text.lower().find(w) for w in words if w in text.lower()), default=0)
            start = max(0, at - 80)
            row.update(snippet=text[start:start + 600], line=int(row['line']) + text.count('\n', 0, start), score=round(scores[rowid], 6), arxiv_id=row.pop('paper_id'))
            results.append(row)
            if len(results) == 10:
                break
        return results
