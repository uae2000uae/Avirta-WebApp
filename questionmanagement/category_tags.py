"""Category filter tags for the create-room pickers.

Tags live in contents/category_tags.json (see its "_about" note) and are
managed from the admin pages: Question Bank (tag list + per-category tags),
Edit Category, the AI generator's "New category" and Bulk import. A category
can have several tags. Categories with no entry get the "other" tag in the
pickers so new categories always stay reachable from the filter.

The file is synced to GitHub with the rest of the runtime data
(contents/admin_controls/github_sync.py, SYNC_GLOBS).
"""
import json
import os
import re
import threading

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "contents", "category_tags.json")
_LOCK = threading.Lock()

OTHER = {"en": "Other", "ar": "أخرى", "group": "topic"}
GROUPS = ("language", "topic")
GROUP_LABELS = {"language": ("Language", "اللغة"), "topic": ("Topic", "الموضوع")}
_ABOUT = ("Filter tags for the create-room category pickers. 'tags' defines each tag "
          "(English and Arabic label, and its group: tags in the same group widen the "
          "filter, different groups narrow it). 'categories' maps a category id (the "
          "question file name) to its tags; a category may have several. Categories "
          "missing here are shown under 'Other'. Managed from Admin > Question Bank.")


# ------------------------------------------------------------------ storage
def load_store(path=None):
    """The whole file as {"tags": {...}, "categories": {...}} (never raises)."""
    try:
        with open(path or _PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    tags = data.get("tags") if isinstance(data.get("tags"), dict) else {}
    cats = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    return {"tags": tags, "categories": cats}


def _dump(store):
    """One tag / category per line, so GitHub diffs stay readable."""
    def line(obj):
        return json.dumps(obj, ensure_ascii=False)
    tags = ",\n".join(f"    {line(k)}: {line(v)}" for k, v in store["tags"].items())
    cats = ",\n".join(f"    {line(k)}: {line(v)}" for k, v in store["categories"].items())
    return ("{\n"
            f'  "_about": {line(_ABOUT)},\n'
            f'  "tags": {{\n{tags}\n  }},\n'
            f'  "categories": {{\n{cats}\n  }}\n'
            "}\n")


def save_store(store, path=None):
    path = path or _PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_dump(store))
    os.replace(tmp, path)


def _update(fn, path=None):
    """Read, change and write the file under a lock. Returns fn's result."""
    with _LOCK:
        store = load_store(path)
        result = fn(store)
        save_store(store, path)
        return result


# ------------------------------------------------------------------ reading
def all_tags(path=None):
    """Every defined tag in display order: language tags first, then topics."""
    defs = load_store(path)["tags"]
    out = []
    for gid in GROUPS:
        out += [{"id": tid, "en": d.get("en", tid), "ar": d.get("ar", ""), "group": gid}
                for tid, d in defs.items() if d.get("group", "topic") == gid]
    return out


def tags_by_group(path=None):
    """[{"id", "en", "ar", "tags": [...]}] for building tag pickers."""
    tags = all_tags(path)
    return [{"id": g, "en": GROUP_LABELS[g][0], "ar": GROUP_LABELS[g][1],
             "tags": [t for t in tags if t["group"] == g]} for g in GROUPS]


def category_tag_map(path=None):
    """{category_id: [tag ids]} for tagged categories (unknown tags dropped)."""
    store = load_store(path)
    return {cid: [t for t in tags if t in store["tags"]]
            for cid, tags in store["categories"].items()}


def category_tag_filters(category_ids, path=None):
    """Tag data for a create-room picker showing `category_ids`.

    Returns (groups, tags_by_category):
      groups           -- [{"id", "tags": [{"id", "en", "ar"}]}] in display
                          order, only tags used by at least one category shown
      tags_by_category -- {category_id: [tag ids]} for every id given
    """
    store = load_store(path)
    defs, mapping = store["tags"], store["categories"]
    tags_by_category = {}
    used = set()
    for cid in category_ids:
        tags = [t for t in (mapping.get(cid) or []) if t in defs]
        if not tags:
            tags = ["other"]
        tags_by_category[cid] = tags
        used.update(tags)

    defs = dict(defs)
    if "other" in used:
        defs["other"] = OTHER

    groups = []
    for gid in GROUPS:
        items = [{"id": tid, "en": d.get("en", tid), "ar": d.get("ar", "")}
                 for tid, d in defs.items()
                 if tid in used and d.get("group", "topic") == gid]
        if items:
            groups.append({"id": gid, "tags": items})
    return groups, tags_by_category


# ------------------------------------------------------------------ editing
def set_category_tags(category_id, tag_ids, path=None):
    """Replace a category's tags. Unknown ids are ignored; none = untagged."""
    if not category_id:
        return []

    def change(store):
        clean = []
        for t in tag_ids or []:
            if t in store["tags"] and t not in clean:
                clean.append(t)
        if clean:
            store["categories"][category_id] = clean
        else:
            store["categories"].pop(category_id, None)
        return clean
    return _update(change, path)


def rename_category(old_id, new_id, path=None):
    """Move tags when a category id changes."""
    if not old_id or not new_id or old_id == new_id:
        return

    def change(store):
        tags = store["categories"].pop(old_id, None)
        if tags and new_id not in store["categories"]:
            store["categories"][new_id] = tags
    _update(change, path)


def remove_category(category_id, path=None):
    _update(lambda store: store["categories"].pop(category_id, None), path)


def slugify(text):
    slug = re.sub(r"[^\w]+", "_", (text or "").strip().lower(), flags=re.UNICODE).strip("_")
    return slug[:40]


def save_tag(en, ar, group, tag_id=None, path=None):
    """Add a tag (tag_id None) or update one. Returns (ok, message, tag_id)."""
    en, ar = (en or "").strip(), (ar or "").strip()
    group = group if group in GROUPS else "topic"
    if not en or not ar:
        return False, "A tag needs an English and an Arabic name.", None

    def change(store):
        tid = tag_id or slugify(en)
        if not tid:
            return False, "Use letters or numbers in the English name.", None
        if tag_id is None and tid in store["tags"]:
            return False, f"A tag called '{store['tags'][tid].get('en', tid)}' already exists.", None
        if tag_id is not None and tag_id not in store["tags"]:
            return False, "That tag no longer exists.", None
        store["tags"][tid] = {"en": en, "ar": ar, "group": group}
        return True, ("Tag updated." if tag_id else f"Tag '{en}' added."), tid
    return _update(change, path)


def delete_tag(tag_id, path=None):
    """Delete a tag and take it off every category. Returns how many lost it."""
    def change(store):
        store["tags"].pop(tag_id, None)
        hit = 0
        for cid in list(store["categories"]):
            tags = store["categories"][cid]
            if tag_id in tags:
                hit += 1
                tags = [t for t in tags if t != tag_id]
                if tags:
                    store["categories"][cid] = tags
                else:
                    store["categories"].pop(cid)
        return hit
    return _update(change, path)
