
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("chroma_query")

def main():
    print("=== CHROMA DB LATEST RECORDS QUERY ===")
    
    # Initialize KnowledgeManager
    km = KnowledgeManager()
    
    # Get collection info
    try:
        count = km.collection.count()
        print(f"Total documents in collection: {count}")
        
        if count == 0:
            print("No documents found in the collection.")
            return
            
        # Get all documents with metadata to find latest
        print("\n=== QUERYING LATEST RECORDS ===")
        
        # Get recent documents (limit to 50 for performance)
        limit = min(50, count)
        results = km.collection.get(
            limit=limit,
            include=["documents", "metadatas", "ids"]
        )
        
        # Extract and sort by creation/modification time
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        ids = results.get("ids", [])
        
        if not documents:
            print("No documents retrieved.")
            return
            
        # Combine data and sort by timestamp fields
        records = []
        for i in range(len(documents)):
            doc = documents[i]
            meta = metadatas[i] if i < len(metadatas) else {}
            doc_id = ids[i] if i < len(ids) else f"unknown_{i}"
            
            # Look for timestamp fields in metadata
            timestamp = None
            for time_field in ['created_at', 'updated_at', 'date', 'timestamp', 'ingested_at']:
                if time_field in meta and meta[time_field]:
                    timestamp = meta[time_field]
                    break
            
            records.append({
                'id': doc_id,
                'document': doc[:200] + "..." if len(doc) > 200 else doc,
                'metadata': meta,
                'timestamp': timestamp,
                'full_doc': doc
            })
        
        # Sort by timestamp (most recent first)
        records_with_time = [r for r in records if r['timestamp']]
        records_without_time = [r for r in records if not r['timestamp']]
        
        if records_with_time:
            try:
                records_with_time.sort(key=lambda x: x['timestamp'], reverse=True)
            except:
                # If sorting fails, just keep original order
                pass
        
        # Show latest 10 records
        print(f"\n=== LATEST 10 RECORDS (from {len(records)} total) ===")
        
        latest_records = records_with_time[:10] if records_with_time else records[:10]
        
        for i, record in enumerate(latest_records, 1):
            print(f"\n--- Record {i} ---")
            print(f"ID: {record['id']}")
            print(f"Timestamp: {record['timestamp'] or 'Not available'}")
            print(f"Document preview: {record['document']}")
            
            # Show relevant metadata
            meta = record['metadata']
            interesting_fields = ['player', 'team', 'season', 'type', 'source', 'title']
            meta_info = []
            for field in interesting_fields:
                if field in meta and meta[field]:
                    meta_info.append(f"{field}: {meta[field]}")
            
            if meta_info:
                print(f"Metadata: {', '.join(meta_info)}")
            
            print("-" * 50)
        
        # Show summary by type/source
        print(f"\n=== SUMMARY BY DOCUMENT TYPE ===")
        type_counts = {}
        source_counts = {}
        
        for record in records:
            meta = record['metadata']
            doc_type = meta.get('type', 'unknown')
            source = meta.get('source', 'unknown')
            
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1
        
        print("Document types:")
        for doc_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {doc_type}: {count}")
            
        print("\nSources:")
        for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {source}: {count}")
            
        # Check for very recent records (last 24 hours)
        print(f"\n=== RECENT ACTIVITY CHECK ===")
        now = datetime.now()
        recent_count = 0
        
        for record in records:
            timestamp = record['timestamp']
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        # Try different timestamp formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
                            try:
                                ts = datetime.strptime(timestamp.split('.')[0], fmt)
                                if (now - ts).total_seconds() < 86400:  # 24 hours
                                    recent_count += 1
                                break
                            except:
                                continue
                except:
                    pass
        
        print(f"Records from last 24 hours: {recent_count}")
        
    except Exception as e:
        log.error(f"Error querying ChromaDB: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
