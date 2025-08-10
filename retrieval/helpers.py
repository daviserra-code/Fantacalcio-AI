def dump_chroma_texts_ids(collection):
  texts, ids = [], []
  offset, step = 0, 200
  while True:
      batch = collection.get(limit=step, offset=offset, include=["documents"])
      if not batch or not batch.get("ids"):
          break
      ids.extend(batch["ids"])
      texts.extend(batch["documents"])
      offset += step
      if len(batch["ids"]) < step:
          break
  return texts, ids